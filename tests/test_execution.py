"""Financial call matching with synthetic transactions. All providers disabled."""
import os,copy,json,unittest
from unittest.mock import patch
from eth_abi import encode
from eth_utils import keccak
assert os.environ.get('RALLY_TESTING')=='1'
import service as s,venues as v,settlement as p,wallet_execution as w

W='0x'+'11'*20; R='0x'+'22'*20; RELAY='0x'+'33'*20; H='0x'+'44'*32; B='0x'+'55'*32
ACTOR={'user':'buyer','actor':'buyer','grant':None,'scopes':s.SCOPES}
def topic_address(address):return '0x'+address[2:].rjust(64,'0')
def event(address,signature,topics,types,values):
    return {'address':address,'topics':['0x'+keccak(text=signature).hex(),*topics],
        'data':'0x'+encode(types,values).hex(),'removed':False}

class Execution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(s,'rpc',side_effect=AssertionError('No live RPC')),patch.object(s,'http_json',side_effect=AssertionError('No provider')):s.initialize()
        s.write('INSERT INTO accounts(id,handle,name,kind,wallet,created) VALUES(?,?,?,?,?,?)',('buyer','buyer','Buyer','person',W,s.now()))
        s.write('INSERT INTO accounts(id,handle,name,kind,wallet,created) VALUES(?,?,?,?,?,?)',('creator','creator','Creator','person',R,s.now()))
        s.write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient) VALUES(?,?,?,?,?,?,?,?,?)',('feed','creator','Signals','[100,0,0]','[]',s.now(),'100000',1,R))
    def setUp(self):
        for table in ['execution_records','execution_plans','invoices','entitlements']:s.write('DELETE FROM '+table)
        self.expected={'from':W,'to':R,'data':'0x12345678','value':'0x0','chainId':'0x8f'}
        self.tx={**self.expected,'input':self.expected['data'],'hash':H}
        self.receipt={'transactionHash':H,'status':'0x1','blockNumber':'0x64','blockHash':B,'logs':[]}
        self.final=100;self.canonical=True;self.trace=None;self.calls=[]
        self.rpc=patch.object(s,'rpc',side_effect=self.read);self.rpc.start()
        self.net=patch.object(s,'verify_rpc_network',return_value=None);self.net.start()
        self.http=patch.object(s,'http_json',side_effect=AssertionError('No provider'));self.http.start()
        self.addCleanup(self.rpc.stop);self.addCleanup(self.net.stop);self.addCleanup(self.http.stop)
    def read(self,method,args):
        self.calls.append(method)
        if method=='eth_getTransactionByHash':return self.tx
        if method=='eth_getTransactionReceipt':return self.receipt
        if method=='eth_getBlockByNumber':return {'number':hex(self.final if args[0]=='finalized' else 100),'hash':B if self.canonical else '0x'+'00'*32,'timestamp':hex(s.now())}
        if method=='debug_traceTransaction':
            if self.trace is None:raise s.Problem('No trace',503)
            return self.trace
        raise AssertionError('Unexpected RPC '+method)
    def relay(self,expected=None):
        expected=expected or self.expected
        self.tx={'from':RELAY,'to':W,'input':'0xaabbccdd','value':'0x0','hash':H,'chainId':'0x8f'}
        self.trace={**self.tx,'type':'CALL','calls':[{**expected,'input':expected['data'],'type':'CALL'}]}
    def plan(self,venue='perpl',approval=None,summary=None):
        payload={'transaction':self.expected,'approval':approval,'summary':summary or {'action':'order'},'created':s.now()-10,'expires':s.now()+90}
        s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',('plan','buyer',W,venue,payload['summary']['action'],s.dump(payload),payload['expires']))
        return payload
    def allowance(self):
        amount=100000;data='0x095ea7b3'+R[2:].rjust(64,'0')+hex(amount)[2:].rjust(64,'0')
        self.expected={'from':W,'to':s.USDC,'data':data,'value':'0x0'};self.tx={**self.expected,'input':data,'hash':H,'chainId':'0x8f'}
        self.receipt['logs']=[event(s.USDC,'Approval(address,address,uint256)',[topic_address(W),topic_address(R)],['uint256'],[amount])]
        return {'token':s.USDC,'spender':R,'amountRaw':str(amount)}
    def invoice(self,terms=None):
        s.write('INSERT INTO invoices(id,buyer,feed,version,wallet,recipient,amount_raw,created,expires,state,community_terms) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('invoice','buyer','feed',1,W,R,'100000',s.now()-10,s.now()+90,'awaiting_payment',s.dump(terms) if terms else None))
        row=s.one('SELECT * FROM invoices');self.expected={'from':W,'to':R if terms else s.USDC,'data':p.calldata(row),'value':'0x0'};self.tx={**self.expected,'input':self.expected['data'],'hash':H,'chainId':'0x8f'}
        return row
    def test_exact_direct_record(self):
        self.plan();self.assertEqual(v.record(ACTOR,{'plan':'plan','tx':H})['state'],'submitted')
    def test_wrapped_records_for_all_shared_adapters(self):
        for venue in ['perpl','castora','nadfun','nadfees','leverup','pingu','drake']:
            with self.subTest(venue=venue):
                s.write('DELETE FROM execution_records');s.write('DELETE FROM execution_plans');self.plan(venue);self.relay()
                self.assertEqual(v.record(ACTOR,{'plan':'plan','tx':H})['state'],'submitted')
    def test_record_retry_is_idempotent(self):
        self.plan();a=v.record(ACTOR,{'plan':'plan','tx':H});b=v.record(ACTOR,{'plan':'plan','tx':H});self.assertEqual(a['id'],b['id']);self.assertEqual(s.one('SELECT count(*) n FROM execution_records')['n'],1)
    def test_record_wrong_chain(self):
        self.plan();self.tx['chainId']='0x1'
        with self.assertRaises(s.Problem):v.record(ACTOR,{'plan':'plan','tx':H})
    def test_relay_pending_does_not_record(self):
        self.plan();self.relay();self.final=99
        with self.assertRaises(s.Problem):v.record(ACTOR,{'plan':'plan','tx':H})
        self.assertEqual(s.one('SELECT count(*) n FROM execution_records')['n'],0)
    def test_relay_trace_missing_does_not_record(self):
        self.plan();self.relay();self.trace=None
        with self.assertRaises(s.Problem):v.record(ACTOR,{'plan':'plan','tx':H})
        self.assertEqual(s.one('SELECT count(*) n FROM execution_records')['n'],0)
    def test_relay_wrong_internal_call(self):
        for key,value in [('from',R),('to',W),('input','0x12345679'),('value','0x1'),('type','DELEGATECALL')]:
            with self.subTest(key=key):
                self.relay();self.trace['calls'][0][key]=value
                with self.assertRaises(s.Problem):w.verified_call(H,self.expected)
    def test_duplicate_relay_calls_rejected(self):
        self.relay();self.trace['calls'].append(copy.deepcopy(self.trace['calls'][0]))
        with self.assertRaises(s.Problem):w.verified_call(H,self.expected)
    def test_reverted_ancestor_rejected(self):
        self.relay();self.trace['error']='execution reverted'
        with self.assertRaises(s.Problem):w.verified_call(H,self.expected)
    def test_relay_size_limit(self):
        self.relay();self.trace['calls'] += [{'type':'STATICCALL'}]*2048
        with self.assertRaises(s.Problem):w.verified_call(H,self.expected)
    def test_wrapped_approval(self):
        a=self.allowance();self.plan(approval=a);self.relay()
        self.assertEqual(v.check_approval(ACTOR,{'plan':'plan','tx':H})['state'],'approved')
    def test_approval_waits_for_finality(self):
        a=self.allowance();self.plan(approval=a);self.final=99
        self.assertEqual(v.check_approval(ACTOR,{'plan':'plan','tx':H})['state'],'pending')
    def test_reorg_is_pending(self):
        a=self.allowance();self.plan(approval=a);self.canonical=False
        self.assertEqual(v.check_approval(ACTOR,{'plan':'plan','tx':H})['state'],'pending')
    def test_receipt_hash_mismatch(self):
        a=self.allowance();self.plan(approval=a);self.receipt['transactionHash']='0x'+'66'*32
        with self.assertRaises(s.Problem):v.check_approval(ACTOR,{'plan':'plan','tx':H})
    def test_exact_approval_event_required(self):
        a=self.allowance();self.plan(approval=a);base=copy.deepcopy(self.receipt)
        for change in ['absent','removed','wrong_owner','wrong_spender','wrong_token','wrong_amount','duplicate']:
            self.receipt=copy.deepcopy(base)
            if change=='absent':self.receipt['logs']=[]
            elif change=='removed':self.receipt['logs'][0]['removed']=True
            elif change=='wrong_owner':self.receipt['logs'][0]['topics'][1]=topic_address(R)
            elif change=='wrong_spender':self.receipt['logs'][0]['topics'][2]=topic_address(W)
            elif change=='wrong_token':self.receipt['logs'][0]['address']=R
            elif change=='wrong_amount':self.receipt['logs'][0]['data']='0x'+encode(['uint256'],[99999]).hex()
            else:self.receipt['logs'].append(copy.deepcopy(self.receipt['logs'][0]))
            with self.subTest(change=change),self.assertRaises(s.Problem):v.check_approval(ACTOR,{'plan':'plan','tx':H})
    def test_reverted_approval_is_failed(self):
        a=self.allowance();self.plan(approval=a);self.receipt['status']='0x0';self.receipt['logs']=[]
        self.assertEqual(v.check_approval(ACTOR,{'plan':'plan','tx':H})['state'],'failed')
    def test_posting_agent_cannot_record_or_approve(self):
        a=self.allowance();self.plan(approval=a);actor={**ACTOR,'grant':'posting','actor':'agent'}
        for fn in [v.record,v.check_approval]:
            with self.assertRaises(s.Problem):fn(actor,{'plan':'plan','tx':H})
        self.assertEqual(self.calls,[])
    def test_payment_relay_delivers_access_once(self):
        self.invoice();self.receipt['logs']=[event(s.USDC,'Transfer(address,address,uint256)',[topic_address(W),topic_address(R)],['uint256'],[100000])];self.relay()
        a=p.record(ACTOR,{'invoice':'invoice','tx':H});until=a['accessExpires'];self.assertEqual(a['state'],'paid')
        self.assertEqual(p.record(ACTOR,{'invoice':'invoice','tx':H})['accessExpires'],until)
    def test_payment_relay_missing_trace_no_access(self):
        self.invoice();self.relay();self.trace=None
        with self.assertRaises(s.Problem):p.record(ACTOR,{'invoice':'invoice','tx':H})
        self.assertEqual(s.one('SELECT count(*) n FROM entitlements')['n'],0);self.assertIsNone(s.one('SELECT tx FROM invoices')['tx'])
    def test_payment_missing_delivery_no_access(self):
        self.invoice();self.assertEqual(p.record(ACTOR,{'invoice':'invoice','tx':H})['state'],'invalid');self.assertEqual(s.one('SELECT count(*) n FROM entitlements')['n'],0)
    def test_payment_approval_relay(self):
        terms={'vault':R,'creator':R,'buybackBps':2000,'policyNonce':1};self.invoice(terms);self.allowance();self.relay()
        self.assertEqual(p.approval_check(ACTOR,{'invoice':'invoice','tx':H})['state'],'confirmed')
    def test_perpl_collateral_other_account_rejected(self):
        self.plan(summary={'action':'deposit','amount':'0.1','accountId':7});s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','buyer','plan',H,'submitted',None,s.now()))
        self.receipt['logs']=[event(v.PERPL,'CollateralDeposit(uint256,uint256,uint256)',[],['uint256']*3,[8,100000,100000])]
        with patch.object(v,'read',return_value={'accountId':7,'accountAddr':W}):v.reconcile('record')
        self.assertEqual(json.loads(s.one('SELECT outcome FROM execution_records')['outcome'])['businessState'],'check_venue_result')
    def test_perpl_removed_and_noncanonical_logs_rejected(self):
        self.plan(summary={'action':'deposit','amount':'0.1','accountId':7});s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','buyer','plan',H,'submitted',None,s.now()))
        log=event(v.PERPL,'CollateralDeposit(uint256,uint256,uint256)',[],['uint256']*3,[7,100000,100000])
        for change in ['removed','extra_topic','trailing_data']:
            item=copy.deepcopy(log)
            if change=='removed':item['removed']=True
            elif change=='extra_topic':item['topics'].append(topic_address(W))
            else:item['data']+='00'*32
            self.receipt['logs']=[item];s.write("UPDATE execution_records SET state='submitted',outcome=NULL")
            with patch.object(v,'read',return_value={'accountId':7,'accountAddr':W}):v.reconcile('record')
            self.assertEqual(json.loads(s.one('SELECT outcome FROM execution_records')['outcome'])['businessState'],'check_venue_result')
    def test_new_perpl_account_collateral_bound_at_inclusion(self):
        self.plan(summary={'action':'deposit','amount':'0.1'});s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','buyer','plan',H,'submitted',None,s.now()))
        self.receipt['logs']=[event(v.PERPL,'CollateralDeposit(uint256,uint256,uint256)',[],['uint256']*3,[7,100000,100000]),event(v.AUSD,'Transfer(address,address,uint256)',[topic_address(W),topic_address(v.PERPL)],['uint256'],[100000])]
        with patch.object(v,'read',return_value={'accountId':7,'accountAddr':W}) as read:v.reconcile('record')
        self.assertEqual(read.call_args.kwargs['block'],'0x64');self.assertEqual(json.loads(s.one('SELECT outcome FROM execution_records')['outcome'])['businessState'],'collateral_deposit')
    def test_perpl_withdrawal_requires_wallet_delivery(self):
        self.plan(summary={'action':'withdraw','amount':'0.1','accountId':7});s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','buyer','plan',H,'submitted',None,s.now()))
        withdrawal=event(v.PERPL,'CollateralWithdrawal(uint256,uint256,uint256)',[],['uint256']*3,[7,100000,0]);self.receipt['logs']=[withdrawal]
        with patch.object(v,'read',return_value={'accountId':7,'accountAddr':W}):v.reconcile('record')
        self.assertEqual(json.loads(s.one('SELECT outcome FROM execution_records')['outcome'])['businessState'],'check_venue_result')
        s.write("UPDATE execution_records SET state='submitted',outcome=NULL")
        self.receipt['logs'].append(event(v.AUSD,'Transfer(address,address,uint256)',[topic_address(v.PERPL),topic_address(W)],['uint256'],[100000]))
        with patch.object(v,'read',return_value={'accountId':7,'accountAddr':W}):v.reconcile('record')
        self.assertEqual(json.loads(s.one('SELECT outcome FROM execution_records')['outcome'])['businessState'],'collateral_withdraw')
    def test_reconcilers_receive_the_reviewed_wallet(self):
        for venue in ['nadfees','nadrevenue','leverup','pingu','drake','nadfun']:
            with self.subTest(venue=venue):
                s.write('DELETE FROM execution_records');s.write('DELETE FROM execution_plans');self.plan(venue)
                s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','buyer','plan',H,'submitted',None,s.now()))
                module=__import__({'nadfees':'launch_fees','nadrevenue':'nad_revenue'}.get(venue,venue))
                with patch.object(module,'reconcile') as reconcile:v.reconcile('record')
                self.assertEqual(reconcile.call_args.args[0]['wallet'],W)

if __name__=='__main__':unittest.main(verbosity=2)
