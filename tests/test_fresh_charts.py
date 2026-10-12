import unittest
from unittest.mock import patch
import service as s
import market_data as m
import native_market_transport as n

TOKEN='0x'+'a'*40
POOL='0x'+'b'*40
OTHER='0x'+'c'*40

class FreshChartTests(unittest.TestCase):
    def setUp(self):
        self.ident={'asset':TOKEN,'pool':POOL,'token':TOKEN,'symbol':'TEST','reference':'Monad pool reference','kind':'spot'}
        self.raw={'meta':{'base':{'address':OTHER},'quote':{'address':TOKEN}},'data':{'attributes':{'ohlcv_list':[[s.now()-60,1,2,.5,1.25,10]]}}}
    def test_every_read_reaches_provider_and_never_mutates_market_cache(self):
        before=dict(m.CACHE)
        with patch.object(m,'identity',return_value=self.ident),patch.object(n,'get',return_value=(self.raw,{'transport':'fixture','marketCache':False})) as read:
            for _ in range(2):
                value=m.fresh_chart(TOKEN)
                self.assertEqual(value['points'][0]['value'],1.25)
                self.assertTrue(value['freshRead']);self.assertFalse(value['cached'])
            self.assertEqual(read.call_count,2)
            self.assertIn('token='+TOKEN,read.call_args.args[0])
        self.assertEqual(m.CACHE,before)
    def test_cross_token_response_is_rejected(self):
        raw={**self.raw,'meta':{'base':{'address':OTHER}}}
        with patch.object(m,'identity',return_value=self.ident),patch.object(n,'get',return_value=(raw,{})):
            with self.assertRaises(s.Problem) as raised:m.fresh_chart(TOKEN)
            self.assertEqual(raised.exception.code,'chart_identity')
    def test_full_ingress_slots_fail_without_an_upstream_request(self):
        with patch.object(m,'identity',return_value=self.ident),patch.object(n,'get') as read:
            m.SLOTS.acquire();m.SLOTS.acquire()
            try:
                with self.assertRaises(s.Problem):m.fresh_chart(TOKEN)
                read.assert_not_called()
            finally:m.SLOTS.release();m.SLOTS.release()
    def test_unknown_period_never_reaches_a_provider(self):
        with patch.object(n,'get') as read:
            with self.assertRaises(s.Problem):m.fresh_chart(TOKEN,period='BAD')
            read.assert_not_called()
    def test_verified_nad_pool_can_precede_spot_registry(self):
        import json
        token={'address':TOKEN,'id':TOKEN,'chainId':143,'symbol':'TEST','graduated':True,'pair':POOL}
        with patch.object(s.GATEWAY,'token_map',{}),patch.object(s,'one',return_value={'info':json.dumps(token)}):
            self.assertEqual(m.identity(TOKEN,'spot')['pool'],POOL)
        token['graduated']=False
        with patch.object(s.GATEWAY,'token_map',{}),patch.object(s,'one',return_value={'info':json.dumps(token)}):
            with self.assertRaises(s.Problem):m.identity(TOKEN,'spot')

if __name__=='__main__':unittest.main()
