import os,sys,json,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,nadfun as n,launch_graduations as g,launch_metrics as m,token_markets as tm
from token_market_fixture import launch,address
class Recency(unittest.TestCase):
 @classmethod
 def setUpClass(cls):s.initialize();n.initialize()
 def setUp(self):
  with s.connection() as c:
   for t in ['nad_tokens','nad_graduations','nad_events','nad_metrics']:c.execute('DELETE FROM '+t)
  tm.SNAPSHOTS.clear();m.VALUES.clear();m.QUEUE.clear();m.RETRY.clear();n.MARKET_REFERENCES.clear()
 def record(self,i,stamp,block=100):
  a=address(i);item={'name':'Graduate','fields':{'token':a}}
  log={'address':n.contract('v2','curve'),'blockNumber':hex(block),'blockHash':'0xabc','transactionHash':'0xdef'}
  header={'number':hex(block),'hash':'0xabc','timestamp':hex(stamp)}
  self.assertTrue(g.record('v2',item,log,header));return item,log,header
 def test_graduations_rank_by_finalized_event_not_launch_or_cap(self):
  launch(1,graduated=True,phase='dex',created=s.now()-10,marketCap=1e12)
  launch(2,graduated=True,phase='dex',created=s.now()-1000,marketCap=1)
  launch(3,graduated=True,phase='dex',created=s.now()-1)
  self.record(1,s.now()-500);self.record(2,s.now()-100,110)
  result=tm.catalog({'category':'graduated'})['tokens']
  self.assertEqual([t['id'] for t in result],[address(2),address(1),address(3)])
  self.assertEqual(result[0]['graduatedAt'],s.now()-100);self.assertNotIn('graduatedAt',result[-1])
 def test_graduation_header_and_contract_must_match(self):
  item,log,h=self.record(1,s.now()-100)
  for changed in [dict(h,hash='wrong'),dict(h,number='0xff'),dict(h,timestamp=hex(s.now()+100))]:
   with self.assertRaises(s.Problem):g.record('v2',item,log,changed)
  self.assertFalse(g.record('v2',item,dict(log,removed=True),h))
  with self.assertRaises(s.Problem):g.record('v2',item,dict(log,address=address(9)),h)
 def test_quote_refresh_does_not_change_graduation(self):
  launch(1,graduated=True,phase='dex');self.record(1,s.now()-100)
  launch(1,graduated=True,phase='dex',referenceAt=s.now(),lifecycleAt=s.now(),block=999)
  t=tm.catalog({'category':'graduated'})['tokens'][0]
  self.assertEqual(t['graduatedBlock'],100);self.assertEqual(t['graduatedAt'],s.now()-100)
 def test_future_creation_excluded_and_new_snapshot_can_receive_launch(self):
  launch(1,created=s.now()-200);self.assertEqual(len(tm.catalog({'category':'new'})['tokens']),1)
  launch(2,created=s.now()-10);launch(3,created=s.now()+50);tm.SNAPSHOTS.clear()
  self.assertEqual([t['id'] for t in tm.catalog({'category':'new'})['tokens']],[address(2),address(1)])
 def test_fresh_price_restores_cap_from_known_supply(self):
  launch(1,price=.002,totalSupply='1000000000',marketCap=None)
  self.assertEqual(tm.catalog({'category':'new'})['tokens'][0]['marketCap'],2000000)
 def test_daily_metrics_dont_confuse_curve_progress_or_raw_volume(self):
  data={'metrics':[{'timeframe':'1D','percent':-12.5,'volume':{'total':'1234.567'}}],'percent':99}
  v=m.parse(data);self.assertEqual(v['change'],-12.5);self.assertEqual(v['volume'],'1234.567');self.assertEqual(v['changeWindow'],'24h')
  for bad in [dict(data,metrics=[]),{'metrics':[{'timeframe':'1D','percent':'NaN','volume':{'total':1}}]}, {'metrics':[{'timeframe':'1D','percent':2,'volume':{'total':-1}}]}]:
   with self.assertRaises(ValueError):m.parse(bad)
 def test_metrics_are_scoped_bounded_and_expire(self):
  info=launch(1);m.queue([info]);m.VALUES[info['id']]={'metricsAt':s.now()-601,'change':50};self.assertNotIn('change',m.overlay(info))
  with patch.object(n,'api',return_value={'metrics':[{'timeframe':'1D','percent':.25,'volume':{'total':6.81}}]}) as api:
   self.assertTrue(m.refresh_once());self.assertIn(info['id'],api.call_args.args[0]);self.assertEqual(m.overlay(info)['change'],.25)
  m.queue([info]);self.assertFalse(m.refresh_once())
 def test_metric_failure_does_not_replace_last_good_data(self):
  info=launch(1);m.queue([info]);v={'metricsAt':s.now()-150,'change':2};m.VALUES[info['id']]=v
  with patch.object(n,'api',side_effect=Exception('down')):self.assertFalse(m.refresh_once())
  self.assertEqual(m.VALUES[info['id']],v)
if __name__=='__main__':unittest.main()
