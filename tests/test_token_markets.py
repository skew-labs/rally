"""Ranking, lifecycle and cursor guarantees; all external providers are blocked."""
import os, sys, json, unittest, tracemalloc, time
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING') == '1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s
import nadfun, market_universe as universe, token_markets as market
from token_market_fixture import address, asset, dex, launch


class TokenMarkets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s.initialize();nadfun.initialize()

    def setUp(self):
        self.stack=[]
        for obj,key in [(s,'rpc'),(s,'http_json'),(s,'rpc_read_batch')]:
            p=patch.object(obj,key,side_effect=AssertionError('Provider access forbidden'));p.start();self.stack.append(p)
        self.original=(s.GATEWAY.tokens,s.GATEWAY.token_map,s.GATEWAY.prices)
        s.GATEWAY.tokens=[];s.GATEWAY.token_map={};s.GATEWAY.prices={}
        s.write('DELETE FROM nad_tokens')
        with universe.db() as db:db.execute('DELETE FROM assets')
        nadfun.MARKET_REFERENCES.clear();market.SNAPSHOTS.clear()

    def tearDown(self):
        s.GATEWAY.tokens,s.GATEWAY.token_map,s.GATEWAY.prices=self.original
        for p in self.stack:p.stop()

    def ids(self, category, **params):
        return [t['id'] for t in market.catalog(dict(category=category,**params))['tokens']]

    def test_categories_use_contract_lifecycle(self):
        dex(1);launch(2);launch(3,graduated=True,phase='dex');launch(4,graduated=True,phase='curve');launch(5,block=0)
        self.assertEqual(set(self.ids('crypto')), {address(1),address(3)})
        self.assertEqual(self.ids('graduated'), [address(3)])
        self.assertEqual(set(self.ids('new')), {address(2),address(3),address(4)})
        self.assertNotIn(address(5),self.ids('trending'))

    def test_identity_deduplicates_without_losing_curve_restrictions(self):
        dex(2,volume=1e9);launch(2,locked=True,tradeSupported=False,router='exact-router')
        t=market.catalog({'category':'trending'})['tokens']
        self.assertEqual(len(t),1);self.assertTrue(t[0]['nadfun']);self.assertTrue(t[0]['locked'])
        self.assertFalse(t[0]['tradeSupported']);self.assertEqual(t[0]['router'],'exact-router')

    def test_symbols_do_not_collapse_distinct_tokens(self):
        a=launch(1,symbol='SAME');b=launch(2,symbol='SAME')
        self.assertEqual(set(self.ids('trending')), {a['id'],b['id']})

    def test_liquidity_and_activity_rank_actual_fresh_observations(self):
        dex(1,liquidity=1000000,volume=1000000,change=0)
        dex(2,liquidity=1,volume=1,change=100)
        dex(3,liquidity=1e12,volume=1e12,change=1000,fetchedAt=s.now()-500)
        self.assertEqual(self.ids('crypto'),[address(1),address(2),address(3)])
        self.assertEqual(self.ids('trending')[0],address(1))

    def test_new_is_verified_creation_order_not_fetch_order(self):
        launch(1,created=s.now()-100);launch(2,created=s.now()-10);launch(3,created=s.now()+100)
        self.assertEqual(self.ids('new'),[address(2),address(1)])

    def test_current_gateway_prices_overlay_older_index(self):
        dex(1,fetchedAt=s.now()-50)
        s.GATEWAY.prices[address(1)]={'price':2,'fetchedAt':s.now()}
        self.assertEqual(market.references({'assets':address(1)})['tokens'][0]['price'],2)

    def test_community_token_outside_index_is_retained(self):
        item=asset(999);s.GATEWAY.tokens=[item];s.GATEWAY.token_map={item['id']:item}
        s.GATEWAY.prices[item['id']]={'price':1,'fetchedAt':s.now()}
        self.assertEqual(self.ids('crypto'),[item['id']])

    def test_pagination_keeps_original_order_but_refreshes_values(self):
        for i in range(1,8):dex(i)
        first=market.catalog({'limit':3});original=self.ids('crypto')
        dex(1,volume=1e9,liquidity=1e9,price=9);dex(8)
        second=market.catalog({'limit':3,'cursor':first['nextCursor']})
        third=market.catalog({'limit':3,'cursor':second['nextCursor']})
        self.assertEqual([t['id'] for t in first['tokens']+second['tokens']+third['tokens']],original)
        self.assertEqual(third['tokens'][0]['price'],9)
        self.assertNotIn(address(8),original)

    def test_cursor_is_bound_to_query_category_and_watchlist(self):
        dex(1);dex(2);cursor=market.catalog({'limit':1})['nextCursor']
        for params in [{'category':'trending'},{'query':'QA'},{'watch':address(1)}]:
            with self.assertRaises(s.Problem):market.catalog(dict(cursor=cursor,**params))

    def test_malformed_and_expired_cursors_are_client_errors(self):
        for cursor in ['!', 'a', '_w', 'e30', 'bnVsbA', ['a'], 'a'*201]:
            with self.assertRaises(s.Problem):market.catalog({'cursor':cursor})
        dex(1);dex(2);cursor=market.catalog({'limit':1})['nextCursor'];market.SNAPSHOTS.clear()
        with self.assertRaises(s.Problem):market.catalog({'cursor':cursor})

    def test_empty_watchlist_and_exact_address_search(self):
        dex(1);dex(2)
        self.assertEqual(self.ids('crypto',watch=''),[])
        self.assertEqual(self.ids('crypto',query=address(2).upper()),[address(2)])

    def test_stale_missing_and_nonfinite_values_are_not_live_zero_returns(self):
        dex(1,fetchedAt=s.now()-1000);dex(2,price='NaN',change='Infinity')
        items=market.references({'assets':address(1)+','+address(2)})['tokens']
        self.assertTrue(items[0]['stale']);self.assertIsNone(items[0]['price']);self.assertIsNone(items[0]['change'])
        self.assertIsNone(items[1]['price']);self.assertIsNone(items[1]['change'])

    def test_parameters_bounded_and_references_preserve_order(self):
        dex(1);dex(2)
        self.assertEqual([t['id'] for t in market.references({'assets':address(2)+','+address(1)})['tokens']], [address(2),address(1)])
        for params in [{'limit':0},{'limit':61},{'category':'fake'},{'watch':'invalid'}]:
            with self.assertRaises(s.Problem):market.catalog(params)
        for ids in ['',','.join(address(n) for n in range(61)),'invalid']:
            with self.assertRaises(s.Problem):market.references({'assets':ids})

    def test_launch_json_is_streamed_with_bounded_working_memory(self):
        sample=launch(1,description='x'*16384)
        with s.connection() as db:
            db.executemany('INSERT OR REPLACE INTO nad_tokens VALUES(?,?,?,?)',
                           ((address(n),'v2',s.dump(dict(sample,id=address(n),address=address(n))),s.now()) for n in range(1,257)))
        tracemalloc.start()
        iterator=market.candidates()
        try:
            first=next(iterator)
            self.assertTrue(first['nadfun'])
            self.assertLess(tracemalloc.get_traced_memory()[1],2*1024*1024)
        finally:
            iterator.close();tracemalloc.stop()

    def test_snapshot_inventory_has_an_aggregate_memory_bound(self):
        for n in range(4):
            market.SNAPSHOTS[str(n)]={'ids':[address(1)]*80000,'signature':('unused',str(n),None),'clock':time.monotonic(),'asOf':s.now()}
        dex(1);market.catalog({})
        self.assertLessEqual(sum(len(v['ids']) for v in market.SNAPSHOTS.values()),300000)


if __name__=='__main__':unittest.main()
