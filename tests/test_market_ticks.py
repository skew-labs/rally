import unittest
from unittest.mock import patch
import market_ticks as m
import service as s

class MarketTicksTests(unittest.TestCase):
    def setUp(self):
        m.SERIES.clear()
        self.current=patch.object(m,'current')
        self.current.start()
    def tearDown(self):self.current.stop()
    def sample(self,value=10,stamp=None,source='Perpl mark',identity='Perpl',select=False):
        m.record('1','perps',value,stamp or s.now(),source,'https://perpl.xyz',identity,select)
    def test_only_viewed_markets_allocate_buffers(self):
        self.sample(select=True);self.assertEqual(m.SERIES,{})
    def test_duplicate_and_old_observations_are_not_fake_ticks(self):
        m.read('1','perps');self.sample(select=True)
        for _ in range(144):self.sample()
        self.sample(9,s.now()-1);self.sample(float('nan'));self.sample(12,s.now()+5)
        data=m.read('1','perps');self.assertEqual(len(data['points']),1)
        self.assertEqual(data['points'][0]['value'],10)
        self.assertEqual(data['observationType'],'price_update')
        self.assertEqual(m.read('1','perps',data['cursor'])['points'],[])
    def test_same_second_changed_prices_are_kept_with_distinct_ids(self):
        m.read('1','perps');self.sample(select=True);self.sample(11)
        values=m.read('1','perps')['points']
        self.assertEqual([p['value'] for p in values],[10,11]);self.assertEqual(values[0]['time'],values[1]['time'])
        self.assertNotEqual(values[0]['id'],values[1]['id'])
    def test_unselected_collector_cannot_mix_reference_sources(self):
        m.read('1','perps');self.sample(select=True);before=m.read('1','perps')
        self.sample(99,source='Global spot',identity='bitcoin')
        self.assertEqual(m.read('1','perps')['points'],before['points'])
        self.sample(99,source='Global spot',identity='bitcoin',select=True)
        data=m.read('1','perps');self.assertNotEqual(before['epoch'],data['epoch']);self.assertEqual(len(data['points']),1)
    def test_ring_is_bounded_and_expired_cursor_resets(self):
        m.read('1','perps');self.sample(select=True)
        for i in range(500):self.sample(100+i)
        data=m.read('1','perps',1);self.assertTrue(data['reset']);self.assertEqual(len(data['points']),240)
        self.assertEqual(data['points'][-1]['value'],599)
    def test_invalid_market_or_cursor_is_rejected(self):
        for args in [('1','stocks',0),('wallet://sign','perps',0),('0xBAD','spot',0),('1','perps',-1)]:
            with self.assertRaises(s.Problem):m.read(*args)
    def test_stale_observation_has_real_age(self):
        m.read('1','perps');self.sample(stamp=s.now()-100,select=True)
        self.assertTrue(m.read('1','perps')['stale'])

if __name__=='__main__':unittest.main()
