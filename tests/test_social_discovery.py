"""Discovery ordering never treats a missing/stale quote as realized ROI."""
import os
assert os.environ.get('RALLY_TESTING') == '1'
import unittest
from unittest.mock import patch
import market_universe as universe
import service as s
from market_universe import gainer_key

class TokenOrderTests(unittest.TestCase):
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
        with patch.object(s,'now',return_value=400),patch.object(s.GATEWAY,'markets',return_value={'tokens':[spot]}),patch.object(s,'rows',return_value=[{'info':json.dumps(curve)}]),patch.object(s,'rpc',side_effect=AssertionError('No RPC in discovery')):
            first=universe.catalog({'scope':'discovery','sort':'gainers','limit':1})
            second=universe.catalog({'scope':'discovery','sort':'gainers','limit':1,'offset':1})
            volume=universe.catalog({'scope':'discovery','sort':'volume','limit':1})
        self.assertEqual(first['tokens'][0]['id'],curve['id'])
        self.assertEqual(second['tokens'][0]['id'],spot['id'])
        self.assertEqual(volume['tokens'][0]['id'],spot['id'])
        self.assertEqual(first['nextOffset'],1)

if __name__=='__main__':unittest.main()
