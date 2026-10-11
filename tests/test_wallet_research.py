"""Synthetic cash flow and feed boundaries; no live providers."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,wallet_research as w,algorithms,algorithm_worker as worker
W='0x'+'11'*20;T='0x'+'22'*20;POOL='0x'+'33'*20;BH='0x'+'44'*32
def tx(n):return '0x'+format(n,'064x')
def transfer(a,b,q,h=1):return {'address':T,'transactionHash':tx(h),'topics':[w.TRANSFER,'0x'+a[2:].rjust(64,'0'),'0x'+b[2:].rjust(64,'0')],'data':hex(q)}
def event(side,n,q=100,v='1'):return {'account_info':{'account_id':W},'swap_info':{'event_type':side,'token_amount':str(q),'value':v,'transaction_hash':tx(n),'created_at':n}}

class Research(unittest.TestCase):
    @classmethod
    def setUpClass(cls):s.initialize()
    def setUp(self):
        s.write('DELETE FROM wallet_research_state');s.write('DELETE FROM wallet_research_receipts')
    def test_free_service_author_and_immutable_version(self):
        for ident in w.RECIPES:
            f=s.one('SELECT * FROM feeds WHERE id=?',(ident,));self.assertEqual(f['owner'],'rally');self.assertEqual(f['price_raw'],'0')
            self.assertEqual(s.one('SELECT kind FROM accounts WHERE id=?',('rally',))['kind'],'service')
        old=s.one('SELECT * FROM algorithm_versions WHERE id=?',('wallet-reentry-v1',));w.initialize()
        self.assertEqual(old,s.one('SELECT * FROM algorithm_versions WHERE id=?',('wallet-reentry-v1',)))
    def test_delegatecall_does_not_duplicate_money(self):
        f={'type':'CALL','from':W,'to':POOL,'value':'0x64','calls':[{'type':'DELEGATECALL','from':W,'to':POOL,'value':'0x64'}]}
        self.assertEqual(w.native_cash(f,W),-100)
    def test_failed_child_and_refund(self):
        f={'type':'CALL','from':W,'to':POOL,'value':'0x64','calls':[{'type':'CALL','from':POOL,'to':W,'value':'0x14'},{'type':'CALL','from':POOL,'to':W,'value':'0x99','error':'reverted'}]}
        self.assertEqual(w.native_cash(f,W),-80)
    def test_closed_quantities_and_duplicates(self):
        buy=event('BUY',2);c={'token':{'address':T,'symbol':'T','quoteToken':'0x3bd359c1119da7da1d913d1c4d2b7c461115433a'},'swaps':[event('SELL',1),buy,buy,event('SELL',3,v='2'),event('BUY',4)]}
        out=w.cycles([c]);self.assertEqual(len(out),1);self.assertEqual(len(out[0]['trades']),2)
        c['swaps']=[event('BUY',1),event('SELL',2,q=101,v='2')];self.assertEqual(w.cycles([c]),[])
    def test_exact_address_and_stale_feature(self):
        w.save({'asOf':s.now(),'wallets':[{'wallet':W}],'signals':{T:{'wallet_buyers':1,'wallet_reentry':.5,'wallet_exits':0}},'markets':[]})
        self.assertEqual(w.feature_map({T})[T]['wallet_buyers'],1);self.assertEqual(w.feature_map({'T'}),{})
        s.write('UPDATE wallet_research_state SET updated=?',(s.now()-w.TTL-1,));self.assertEqual(w.feature_map({T}),{})
    def test_empty_result_preserves_previous_evidence(self):
        w.save({'asOf':s.now(),'wallets':[{'wallet':W}],'signals':{},'markets':[]})
        with self.assertRaises(ValueError):w.save({'asOf':s.now(),'wallets':[]})
        self.assertEqual(len(w.snapshot()['wallets']),1)
    def test_old_frozen_features_do_not_gain_future_wallet_data(self):
        old=dict.fromkeys(worker.SOCIAL_FEATURES,0);old['recency']=1
        scores,_=algorithms.run('wallet_buyers + recency',[{'id':'old','features':old}]);self.assertEqual(scores[0]['score'],1)
    def test_wallet_feature_changes_real_child_score(self):
        items=[{'id':'one','features':{**dict.fromkeys(worker.FEATURES,0),'wallet_buyers':1}},{'id':'two','features':{**dict.fromkeys(worker.FEATURES,0),'recency':1}}]
        scores,_=algorithms.run(w.RECIPES['wallet-confluence'][1],items);self.assertGreater(scores[0]['score'],scores[1]['score'])
    def test_finality_cash_and_unknown_transfers(self):
        candidate={'wallet':W,'token':T,'symbol':'T','trades':[event('BUY',1),event('SELL',2,v='2')]}
        def evidence(h):
            n=int(h,16);buy=n==1
            return {'receipt':{'status':'0x1','transactionHash':h,'from':W,'blockNumber':hex(n),'blockHash':BH,'transactionIndex':'0x0','gasUsed':'0x1','effectiveGasPrice':'0x1','logs':[transfer(POOL,W,100,n) if buy else transfer(W,POOL,100,n)]},'trace':{'type':'CALL','from':W,'to':POOL,'value':'0x64' if buy else '0x0','calls':[] if buy else [{'type':'CALL','from':POOL,'to':W,'value':'0xc8'}]}}
        def rpc(method,args):
            if method=='eth_getBlockByNumber':return {'hash':BH,'timestamp':hex(100*int(args[0],16))}
            if method=='eth_call':return '0x0'
            if method=='eth_getLogs':return []
            raise AssertionError(method)
        with patch.object(w,'evidence',side_effect=evidence),patch.object(s,'rpc',side_effect=rpc):
            self.assertEqual(w.verify(candidate,2)['pnlMON'],'0.000000000000000098')
            with self.assertRaises(ValueError):w.verify(candidate,1)
        def unknown(method,args):return [transfer(POOL,W,1,3)] if method=='eth_getLogs' else rpc(method,args)
        with patch.object(w,'evidence',side_effect=evidence),patch.object(s,'rpc',side_effect=unknown),self.assertRaises(ValueError):w.verify(candidate,2)

if __name__=='__main__':unittest.main()
