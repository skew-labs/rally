import unittest
from unittest.mock import patch
import service as s
import market_data as m
import native_market_transport as transport

TOKEN='0x'+'a'*40
POOL='0x'+'b'*40

class HourlyCandlesTests(unittest.TestCase):
    def setUp(self):
        self.hour=s.now()//3600*3600
        self.ident={'asset':TOKEN,'kind':'spot','pool':POOL,'token':TOKEN,'reference':'Monad pool','symbol':'TEST'}
    def test_perpl_uses_trade_ohlc_and_context_precision_not_global_spot(self):
        raw={'r':3600,'d':[{'t':self.hour*1000,'o':1005,'h':1012,'l':999,'c':1009}]}
        with patch.object(s.GATEWAY,'perpl_markets',return_value={'markets':[{'id':1,'priceDecimals':1,'symbol':'BTC'}]}),patch.object(s,'http_json',return_value=raw) as read:
            result=m.hourly_chart('1','perps')
        self.assertIn('/1/candles/3600/',read.call_args.args[0]);self.assertEqual(result['reference'],'Perpl trades')
        self.assertEqual(result['candles'],[{'time':self.hour,'open':100.5,'high':101.2,'low':99.9,'close':100.9}])
        self.assertTrue(result['freshRead']);self.assertFalse(result['cached'])
    def test_wrong_perpl_resolution_is_rejected(self):
        with patch.object(s.GATEWAY,'perpl_markets',return_value={'markets':[{'id':1,'priceDecimals':1,'symbol':'BTC'}]}),patch.object(s,'http_json',return_value={'r':60,'d':[]}):
            with self.assertRaises(s.Problem) as error:m.hourly_chart('1','perps')
        self.assertEqual(error.exception.code,'chart_identity')
    def test_exact_quote_token_and_one_hour_pool_request(self):
        raw={'meta':{'quote':{'address':TOKEN}},'data':{'attributes':{'ohlcv_list':[[self.hour,2,3,1,2.5,0]]}}}
        with patch.object(m,'identity',return_value=self.ident),patch.object(transport,'get',return_value=(raw,{})) as read:
            result=m.hourly_chart(TOKEN)
        self.assertEqual(result['candles'][0]['high'],3)
        self.assertIn('/ohlcv/hour?',read.call_args.args[0]);self.assertIn('aggregate=1',read.call_args.args[0]);self.assertIn('token='+TOKEN,read.call_args.args[0]);self.assertIn('include_empty_intervals=false',read.call_args.args[0])
    def test_another_token_is_rejected(self):
        with patch.object(m,'identity',return_value=self.ident),patch.object(transport,'get',return_value=({'meta':{'base':{'address':POOL}}},{})):
            with self.assertRaises(s.Problem) as error:m.hourly_chart(TOKEN)
        self.assertEqual(error.exception.code,'chart_identity')
    def test_leverup_keeps_hourly_oracle_source(self):
        ident={'asset':'leverup:test','pairBase':TOKEN,'kind':'perps','reference':'LeverUp oracle reference'}
        raw={'pairBase':TOKEN,'blockChain':'MONAD','executionVenue':'POOL','candles':[{'time':self.hour,'open':5,'high':6,'low':4,'close':5.5}]}
        with patch.object(m,'identity',return_value=ident),patch.object(s,'http_json',return_value=raw) as read:
            result=m.hourly_chart(ident['asset'],'perps','7D')
        self.assertIn('resolution=60',read.call_args.args[0]);self.assertEqual(result['reference'],'LeverUp oracle reference')
        self.assertEqual(result['candles'][0]['close'],5.5)
    def test_gaps_extremes_and_partial_current_hour_preserved(self):
        rows=[[self.hour-7200,2,100,.1,3],[self.hour,3,4,2,2.5],[self.hour+3600,1,2,1,1]]
        result=m.hourly_series(rows)
        self.assertEqual(len(result),2);self.assertEqual(result[0]['high'],100);self.assertEqual(result[0]['low'],.1)
        self.assertEqual(result[-1]['time'],self.hour)
    def test_invalid_ohlc_and_off_interval_times_are_never_drawn(self):
        rows=[[self.hour,1,2,.5,1.5],[self.hour-1,1,2,.5,1.5],[self.hour-3600,2,1,.5,2],[self.hour-7200,2,3,2.5,2],[self.hour-10800,1,float('inf'),.5,1]]
        self.assertEqual(len(m.hourly_series(rows)),1)
    def test_backpressure_no_provider_io_and_slot_released(self):
        m.SLOTS.acquire();m.SLOTS.acquire()
        try:
            with patch.object(s,'http_json') as read:
                with self.assertRaises(s.Problem):m.hourly_chart('1','perps')
                read.assert_not_called()
        finally:m.SLOTS.release();m.SLOTS.release()
    def test_month_never_compacts_away_hourly_extremes(self):
        rows=[[self.hour-i*3600,1,2,.1,1.5] for i in range(800)]
        result=m.hourly_series(rows,'1M');self.assertEqual(len(result),721)
        self.assertTrue(all(b['high']==2 and b['low']==.1 for b in result))

if __name__=='__main__':unittest.main()
