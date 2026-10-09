"""Independent read batching must fail closed before a wallet prompt."""
import os,unittest
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
import service as s,transaction_preflight as p

W='0x'+'11'*20
TX={'from':W,'to':'0x'+'22'*20,'value':'0x1','data':'0x','chainId':'0x8f'}

class Preflight(unittest.TestCase):
    def values(self,balance=10**18,gas=21000,price=10**9):
        return [{'id':1,'result':hex(balance)},{'id':2,'result':hex(gas)},{'id':3,'result':hex(price)}]
    def test_bounded_batch_preserves_exact_transaction_and_padding(self):
        with patch.object(s,'rpc_read_batch',return_value=self.values()) as batch:
            result=p.funded(TX,150)
        self.assertEqual(result,{**TX,'gas':hex(31500)})
        self.assertNotIn('gas',TX)
        self.assertEqual([c[0] for c in batch.call_args.args[0]],['eth_getBalance','eth_estimateGas','eth_gasPrice'])
    def test_fee_is_required_in_addition_to_amount(self):
        for balance in [0,1,21000*10**9]:
            with patch.object(s,'rpc_read_batch',return_value=self.values(balance=balance)),self.assertRaises(s.Problem) as error:p.funded(TX)
            self.assertEqual(error.exception.code,'insufficient_gas')
    def test_failed_simulation_never_returns_a_transaction(self):
        results=self.values();results[1]={'id':2,'error':{'code':-1}}
        with patch.object(s,'rpc_read_batch',return_value=results),self.assertRaises(s.Problem) as error:p.funded(TX)
        self.assertEqual(error.exception.code,'simulation_failed')
    def test_failed_fee_or_balance_never_returns_a_transaction(self):
        for i in [0,2]:
            results=self.values();results[i]={'id':i+1,'error':{'code':-1}}
            with patch.object(s,'rpc_read_batch',return_value=results),self.assertRaises(s.Problem):p.funded(TX)
    def test_wrong_network_never_reads_provider(self):
        with patch.object(s,'rpc_read_batch',side_effect=AssertionError('Unexpected provider')),self.assertRaises(s.Problem):p.funded({**TX,'chainId':'0x1'})
    def test_zero_estimate_or_fee_is_rejected(self):
        for results in [self.values(gas=0),self.values(price=0)]:
            with patch.object(s,'rpc_read_batch',return_value=results),self.assertRaises(s.Problem):p.funded(TX)

class BatchIdentity(unittest.TestCase):
    def request(self,raw):
        with patch.object(s,'verify_rpc_network'),patch.object(s,'http_json',return_value=raw),patch.object(s,'RPC_REQUEST_AT',0):
            return s.rpc_read_batch([('eth_gasPrice',[]),('eth_getBalance',[W,'latest'])])
    def test_provider_may_reorder_only_matching_ids(self):
        self.assertEqual([r['id'] for r in self.request([{'id':2,'result':'0x1'},{'id':1,'result':'0x2'}])],[1,2])
    def test_duplicate_missing_foreign_or_boolean_ids_fail(self):
        for raw in [[{'id':1},{'id':1}],[{'id':1}],[{'id':1},{'id':3}],[{'id':True},{'id':2}],{'id':1},[None,{'id':2}]]:
            with self.assertRaises(s.Problem):self.request(raw)
    def test_submissions_and_oversized_batches_never_reach_network(self):
        for calls in [[('eth_sendRawTransaction',['0x'])],[('eth_gasPrice',[])]*9,[]]:
            with patch.object(s,'http_json',side_effect=AssertionError('Unexpected provider')),self.assertRaises(s.Problem):s.rpc_read_batch(calls)

if __name__=='__main__':unittest.main()
