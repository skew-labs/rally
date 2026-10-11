"""Public observation identity, recovery and nonblocking reads; no provider calls."""
import copy, json, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING') == '1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import token_holders as h
import nadfun as n

A='0x'+'11'*20
B='0x'+'22'*20

class HolderSnapshots(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'holders.json'
        self.value={'asset':A,'holders':[{'address':B,'name':'Alice','amount':'890567000.123456789','amountRaw':'890567000123456789'}], 'total':42,'fetchedAt':1000,'source':'nad.fun','indexed':True,'limit':20}
        self.patches=[patch.object(h,'SNAPSHOTS',self.path),patch.object(h.s,'now',return_value=1000),patch.object(h.s,'GATEWAY',SimpleNamespace(token_map={A:{'nadfun':True,'decimals':9}}))]
        for p in self.patches:p.start()
        h.CACHE.clear();h.ACTIVE.clear()
    def tearDown(self):
        h.CACHE.clear();h.ACTIVE.clear()
        for p in reversed(self.patches):p.stop()
        self.directory.cleanup()
    def test_persisted_snapshot_retains_observed_identity_amount_and_time(self):
        h.save_snapshots({A:self.value});h.load_snapshots()
        with patch.object(h.POOL,'submit',side_effect=AssertionError('No refresh needed')):
            result=h.holders(A)
        for key in ['asset','holders','fetchedAt','total']:self.assertEqual(result[key],self.value[key])
        result['holders'][0]['amount']='1';self.assertEqual(h.CACHE[A]['holders'][0]['amount'],self.value['holders'][0]['amount'])
    def test_corrupt_expired_future_and_cross_asset_snapshots_are_rejected(self):
        for value in [dict(self.value,asset=B),dict(self.value,fetchedAt=99),dict(self.value,fetchedAt=1001),dict(self.value,holders=[{'address':'fake','amount':'1'}])]:
            self.path.write_text(json.dumps({A:value}));h.load_snapshots();self.assertEqual(h.CACHE,{})
        self.path.write_text('invalid json');h.load_snapshots();self.assertEqual(h.CACHE,{})
    def test_cold_concurrent_reads_share_one_job_and_return_without_upstream_wait(self):
        with patch.object(h.POOL,'submit') as pool:
            self.assertTrue(h.holders(A)['refreshing']);self.assertTrue(h.holders(A)['refreshing']);self.assertEqual(pool.call_count,1)
    def test_stale_snapshot_remains_visible_but_expired_balances_are_not_exposed(self):
        h.CACHE[A]=dict(self.value,fetchedAt=900)
        with patch.object(h.POOL,'submit'):
            result=h.holders(A);self.assertTrue(result['stale']);self.assertEqual(result['holders'],self.value['holders'])
            h.CACHE[A]['fetchedAt']=99;self.assertEqual(h.holders(A)['holders'],[])
    def test_refresh_disk_failure_retains_valid_memory_snapshot(self):
        raw={'total_count':42,'holders':[{'account_info':{'account_id':B},'balance_info':{'balance':'890567000123456789'}}]}
        with patch.object(n,'api',return_value=raw),patch.object(Path,'write_text',side_effect=OSError('Disk unavailable')):
            h.refresh(A,{'decimals':9})
        self.assertEqual(h.CACHE[A]['holders'][0]['amount'],'890567000.123456789')
    def test_upstream_failure_keeps_previous_observed_data(self):
        h.CACHE[A]=copy.deepcopy(self.value)
        with patch.object(n,'api',side_effect=RuntimeError('Offline')):h.refresh(A,{'decimals':9})
        self.assertEqual(h.CACHE[A]['holders'],self.value['holders']);self.assertEqual(h.CACHE[A]['fetchedAt'],1000)
    def test_unindexed_assets_do_not_schedule_provider_reads(self):
        with patch.object(h.POOL,'submit',side_effect=AssertionError('Provider')):self.assertFalse(h.holders(B)['indexed'])
    def test_busy_queue_returns_explicit_retry_instead_of_false_empty_completion(self):
        h.ACTIVE.update({'x','y','z'})
        with patch.object(h.POOL,'submit',side_effect=AssertionError('Queue full')):
            result=h.holders(A);self.assertTrue(result['waiting']);self.assertEqual(result['retryAfter'],1);self.assertFalse(result['refreshing'])

if __name__=='__main__':unittest.main()
