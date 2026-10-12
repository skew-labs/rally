"""Discovery ordering never treats a missing/stale quote as realized ROI."""
import os
assert os.environ.get('RALLY_TESTING') == '1'
import unittest
from unittest.mock import patch
import market_universe as universe
import service as s
from market_universe import gainer_key

class TokenOrderTests(unittest.TestCase):
    def test_concurrent_cold_requests_share_one_read(self):
        import threading,time
        from concurrent.futures import ThreadPoolExecutor
        barrier=threading.Barrier(6);universe.PAGES.clear()
        def rebuild(params):
            time.sleep(.03)
            return {'tokens':[], 'total':0}
        def read(_):
            barrier.wait()
            return universe.catalog({'scope':'discovery','sort':'gainers','limit':40})
        with patch.object(universe,'uncached_catalog',side_effect=rebuild) as compute:
            with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(read,range(6)))
        self.assertEqual(compute.call_count,1)
        self.assertTrue(all(value is results[0] for value in results))
        universe.PAGES.clear()

    def test_indexed_prices_keep_newest_observation_and_stable_pages(self):
        import json,tempfile
        from pathlib import Path
        rows=[]
        for n in range(300):
            ident='0x'+format(n+500,'040x')
            info={'id':ident,'address':ident,'symbol':'QA'+str(n),'name':'QA indexed token'}
            price={'price':1,'change':n,'volume':n,'fetchedAt':400}
            rows.append((ident,json.dumps(info),json.dumps(price),400))
        with tempfile.TemporaryDirectory() as directory,patch.object(universe,'DB',Path(directory)/'catalog.sqlite3'),patch.object(universe,'READY',False),patch.object(s.GATEWAY,'markets',return_value={'tokens':[]}),patch.object(s.GATEWAY,'prices',{rows[-1][0]:{'price':2,'change':-1,'fetchedAt':401}}),patch.object(s,'now',return_value=402):
            with universe.db() as db:db.executemany('INSERT INTO assets(address,info,price,updated) VALUES(?,?,?,?)',rows)
            first=universe.uncached_catalog({'scope':'all','sort':'gainers','limit':40})
            second=universe.uncached_catalog({'scope':'all','sort':'gainers','limit':40,'offset':40})
            end=universe.uncached_catalog({'scope':'all','sort':'gainers','limit':1,'offset':299})
        self.assertEqual(first['total'],300)
        self.assertEqual([t['change'] for t in first['tokens']+second['tokens']],list(range(298,218,-1)))
        self.assertEqual(end['tokens'][0]['price'],2)
        self.assertIsNone(end['nextOffset'])

    def test_global_order_before_pagination_has_stable_identity_tie_break(self):
        rows=[{'id':'z','change':-3},{'id':'b','change':9},{'id':'a','change':9},{'id':'fresh','change':0}]
        self.assertEqual([x['id'] for x in sorted(rows,key=gainer_key)][:2],['a','b'])

    def test_unknown_nonfinite_and_stale_changes_never_outrank_valid_losses(self):
        rows=[{'id':'stale','change':9000,'stale':True},{'id':'unknown','change':None},{'id':'invalid','change':'NaN'},{'id':'loss','change':-80}]
        self.assertEqual(sorted(rows,key=gainer_key)[0]['id'],'loss')

    def test_discovery_merges_curve_tokens_and_sorts_before_paging_without_rpc(self):
        def asset(n,change,volume):
            return {'id':'0x'+str(n)*40,'address':'0x'+str(n)*40,'symbol':'QA'+str(n),'name':'QA token','price':1,'change':change,'volume':volume,'fetchedAt':400,'referenceAt':400,'stale':False}
        spot=asset(1,5,100);curve={**asset(2,20,1),'nadfun':True,'graduated':False}
        import json
        universe.PAGES.clear()
        with s.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS nad_tokens(address TEXT PRIMARY KEY,version TEXT,info TEXT,observed INTEGER)")
            db.execute("INSERT OR REPLACE INTO nad_tokens VALUES(?,?,?,?)",(curve["id"],"v1",json.dumps(curve),400))
        with patch.object(s,'now',return_value=400),patch.object(s.GATEWAY,'markets',return_value={'tokens':[spot]}),patch.object(s,'rpc',side_effect=AssertionError('No RPC in discovery')):
            first=universe.catalog({'scope':'discovery','sort':'gainers','limit':1})
            second=universe.catalog({'scope':'discovery','sort':'gainers','limit':1,'offset':1})
            volume=universe.catalog({'scope':'discovery','sort':'volume','limit':1})
        self.assertEqual(first['tokens'][0]['id'],curve['id'])
        self.assertEqual(second['tokens'][0]['id'],spot['id'])
        self.assertEqual(volume['tokens'][0]['id'],spot['id'])
        self.assertEqual(first['nextOffset'],1)

if __name__=='__main__':unittest.main()
