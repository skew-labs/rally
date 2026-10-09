"""Financial unit/identity/failure checks with isolated state and no providers."""
import os, sys, copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from eth_abi import encode
assert os.environ.get('RALLY_TESTING') == '1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s, wallet_assets as w, wallet_transfer as t, token_holders as h

W='0x'+'11'*20;R='0x'+'22'*20;TOKEN='0x'+'33'*20


class WalletAssets(unittest.TestCase):
    def setUp(self):
        self.token={'id':TOKEN,'address':TOKEN,'symbol':'T','decimals':6,'price':2,'change':100}
        self.native={'id':'MON','address':s.ZERO,'symbol':'MON','decimals':18,'price':1,'change':0}
        self.g=SimpleNamespace(tokens=[self.native,self.token],token_map={'MON':self.native,TOKEN:self.token},markets=lambda:{'tokens':[self.native,self.token]})
        self.snapshot={'wallet':W,'holdings':[{'asset':TOKEN,'amount':'2','amountRaw':'2000000'}],'complete':True,'refreshing':False,'unavailable':[]}
    def test_decimal_valuation_and_price_basket_change(self):
        p=w.value_snapshot(self.snapshot,self.g)
        self.assertEqual(p['valuation']['valueUSD'],'4');self.assertEqual(p['valuation']['change24hPercent'],'100')
        self.assertEqual(p['valuation']['changeBasis'],'current_holdings_price_change');self.assertNotIn('token',self.snapshot['holdings'][0])
    def test_unknown_price_is_not_valued_as_zero(self):
        self.token['price']=None;p=w.value_snapshot(self.snapshot,self.g)
        self.assertIsNone(p['valuation']['valueUSD']);self.assertEqual(p['valuation']['unpricedAssets'],1);self.assertIsNone(p['valuation']['change24hPercent'])
    def test_missing_change_does_not_fabricate_daily_return(self):
        self.token.pop('change');self.assertIsNone(w.value_snapshot(self.snapshot,self.g)['valuation']['change24hPercent'])
    def test_empty_confirmed_wallet_is_zero_loading_is_unknown(self):
        self.snapshot['holdings']=[];self.assertEqual(w.value_snapshot(self.snapshot,self.g)['valuation']['valueUSD'],'0')
        self.snapshot['complete']=False;self.assertIsNone(w.value_snapshot(self.snapshot,self.g)['valuation']['valueUSD'])
    def test_invalid_price_never_becomes_a_value(self):
        for value in ['NaN','Infinity',-1,0]:
            self.token['price']=value;self.assertIsNone(w.value_snapshot(self.snapshot,self.g)['valuation']['valueUSD'])
    def test_cached_extra_asset_can_already_contain_stale_flag(self):
        gateway=s.Gateway();gateway.token_map[TOKEN]=self.token
        gateway.prices[TOKEN]={'price':2,'stale':True,'fetchedAt':s.now()}
        with patch.object(s,'rows',return_value=[]):
            value=next(t for t in gateway.markets(False)['tokens'] if t['id']==TOKEN)
        self.assertEqual(value['price'],2);self.assertFalse(value['stale'])
    def test_scan_keeps_failed_token_balance_but_updates_native(self):
        previous=copy.deepcopy(self.snapshot)
        with patch.object(s,'rpc',side_effect=['0x64','0xde0b6b3a7640000']),patch.object(w,'catalog',return_value=[self.token]),patch.object(s,'rpc_call_batch',return_value=[{'error':{'code':-1}}]):
            w.scan(self.g,W,previous)
        p=w.CACHE[W];self.assertFalse(p['complete']);self.assertEqual(p['unavailable'],[TOKEN]);self.assertEqual(p['holdings'][0]['amount'],'2');self.assertTrue(p['holdings'][0]['staleBalance']);self.assertFalse(p['holdings'][1]['staleBalance'])
    def test_successful_zero_removes_old_balance(self):
        with patch.object(s,'rpc',side_effect=['0x64','0x0']),patch.object(w,'catalog',return_value=[self.token]),patch.object(s,'rpc_call_batch',return_value=[{'result':'0x'+encode(['(bool,bytes)[]'],[[(True,bytes(32))]]).hex()}]):w.scan(self.g,W,self.snapshot)
        self.assertEqual([x['asset'] for x in w.CACHE[W]['holdings']],['MON']);self.assertTrue(w.CACHE[W]['complete'])
    def test_two_wallets_cannot_share_snapshot(self):
        with w.LOCK:w.CACHE.clear();w.CACHE[W]={**self.snapshot,'attemptAt':s.now()};w.JOBS[R]=True
        with patch.object(w.POOL,'submit',side_effect=AssertionError('No job')):
            self.assertEqual(w.portfolio(self.g,W)['wallet'],W);self.assertEqual(w.portfolio(self.g,R)['holdings'],[])
        w.JOBS.clear()
    def test_inflight_reads_coalesce_without_waiting_for_rpc(self):
        with w.LOCK:w.CACHE.clear();w.JOBS.clear()
        with patch.object(w.POOL,'submit') as pool:
            self.assertTrue(w.portfolio(self.g,W)['refreshing']);w.portfolio(self.g,W);self.assertEqual(pool.call_count,1)
        w.JOBS.clear()
    def test_confirmed_send_refreshes_even_when_an_older_scan_finishes(self):
        with patch.dict(w.CACHE,{},clear=True):
            w.CACHE[W]={**w.empty(W),'blockNumber':100,'attemptAt':s.now()}
            w.invalidate(W,101)
            self.assertEqual(w.CACHE[W]['attemptAt'],0)
            with patch.object(s,'rpc',side_effect=['0x64','0x0']),patch.object(w,'catalog',return_value=[]):w.scan(self.g,W,{})
            self.assertEqual(w.CACHE[W]['attemptAt'],0)
            self.assertEqual(w.CACHE[W]['refreshAfterBlock'],101)
            with patch.object(s,'rpc',side_effect=['0x65','0x0']),patch.object(w,'catalog',return_value=[]):w.scan(self.g,W,{})
            self.assertNotIn('refreshAfterBlock',w.CACHE[W]);self.assertGreater(w.CACHE[W]['attemptAt'],0)


class Transfer(unittest.TestCase):
    def setUp(self):
        self.token={'id':TOKEN,'address':TOKEN,'symbol':'T','decimals':6}
        self.g=SimpleNamespace(token_map={'MON':{'symbol':'MON','decimals':18},TOKEN:self.token})
        self.payload={'summary':{'token':TOKEN,'recipient':R,'amount':'0.01','amountRaw':'10000','asset':'T'},'transaction':{'from':W,'to':TOKEN,'data':'0x','value':'0x0'},'pin':s.digest('0x1234')}
        topic='0x'+t.keccak(text='Transfer(address,address,uint256)').hex()
        self.log={'address':TOKEN,'topics':[topic,'0x'+W[2:].rjust(64,'0'),'0x'+R[2:].rjust(64,'0')],'data':'0x'+hex(10000)[2:].rjust(64,'0')}
    def test_recipient_rejects_zero_self_and_bad_checksum(self):
        for recipient in [s.ZERO,W,'0x123','0x1c8F822682DDAbFF7dA1A7D5D881bdA96c8F41c5']:
            with self.assertRaises(s.Problem):t.recipient(recipient,W)
    def test_send_plan_is_exact_amount_recipient_no_allowance(self):
        with patch('venues.wallet',return_value=('owner',W)),patch.object(s,'GATEWAY',self.g),patch.object(s,'rpc',return_value='0x1234'),patch.object(s,'write'):
            p=t.plan({},dict(venue='wallet',kind='send',asset=TOKEN,recipient=R,amount='0.01'))
        self.assertIsNone(p['approval']);self.assertEqual(p['transaction']['data'],'0xa9059cbb'+R[2:].rjust(64,'0')+hex(10000)[2:].rjust(64,'0'));self.assertEqual(p['transaction']['value'],'0x0')
    def test_precision_error_is_rejected(self):
        with patch('venues.wallet',return_value=('owner',W)),patch.object(s,'GATEWAY',self.g):
            with self.assertRaises(s.Problem):t.plan({},dict(kind='send',asset=TOKEN,recipient=R,amount='0.0000001'))
    def test_exact_transfer_event_required(self):
        receipt={'status':'0x1','logs':[self.log]};self.assertEqual(t.outcome(self.payload,receipt)['businessState'],'sent')
        for field,value in [('address',R),('data','0x01'),('removed',True)]:
            log={**self.log,field:value};self.assertEqual(t.outcome(self.payload,{'status':'0x1','logs':[log]})['businessState'],'transfer_unverified')
    def test_success_receipt_without_transfer_is_not_complete(self):self.assertEqual(t.outcome(self.payload,{'status':'0x1','logs':[]})['businessState'],'transfer_unverified')
    def test_reverted_receipt_is_not_sent(self):self.assertEqual(t.outcome(self.payload,{'status':'0x0','logs':[self.log]})['businessState'],'reverted')
    def test_prepare_rejects_changed_contract_and_insufficient_balance(self):
        with patch.object(s,'rpc_read_batch',return_value=[{'result':'0xbeef'},{'result':hex(10000)},{'result':'0x'}]):
            with self.assertRaises(s.Problem):t.prepare({'wallet':W},self.payload)
        with patch.object(s,'rpc_read_batch',return_value=[{'result':'0x1234'},{'result':'0x1'},{'result':'0x'}]):
            with self.assertRaises(s.Problem):t.prepare({'wallet':W},self.payload)
    def test_prepare_rejects_false_erc20_return(self):
        with patch.object(s,'rpc_read_batch',return_value=[{'result':'0x1234'},{'result':hex(10000)},{'result':'0x'+'0'*64}]):
            with self.assertRaises(s.Problem):t.prepare({'wallet':W},self.payload)


class Holders(unittest.TestCase):
    def test_units_identity_and_duplicates(self):
        raw={'total_count':2,'holders':[{'account_info':{'account_id':W,'nickname':'Alice'},'balance_info':{'balance':'1234567'}}]*2}
        p=h.normalize(TOKEN,{'decimals':6},raw);self.assertEqual(len(p['holders']),1);self.assertEqual(p['holders'][0]['amount'],'1.234567');self.assertEqual(p['asset'],TOKEN)
    def test_malformed_holder_never_borrows_identity(self):
        p=h.normalize(TOKEN,{'decimals':18},{'total_count':2,'holders':[{'account_info':{'account_id':'alice'},'balance_info':{'balance':'1'}}]})
        self.assertEqual(p['holders'],[])
    def test_unindexed_asset_does_not_start_provider_reads(self):
        with patch.object(h.POOL,'submit',side_effect=AssertionError('Provider')):self.assertFalse(h.holders('MON')['indexed'])

if __name__=='__main__':unittest.main()
