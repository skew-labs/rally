"""Chart latency, identity and backpressure checks without provider access."""
import json, os, sys, tempfile, threading, time, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING') == '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nad_chart_cache import ChartCache
import nadfun as n
import service as s

A = '0x'+'11'*20
B = '0x'+'22'*20


class Charts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = 1000
        self.cache = ChartCache(Path(self.directory.name)/'charts.json', lambda: self.now)
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        self.cache.pool.shutdown(wait=True)
        self.directory.cleanup()

    def value(self, token=A, interval='60'):
        return dict(token=token, interval=interval, source='nad.fun', fetchedAt=self.now,
                    candles=[dict(time=900, open=1, high=2, low=1, close=2, volume=10)])

    def blocked(self, token=B):
        self.release.wait(3)
        return self.value(token)

    def test_cached_token_does_not_wait_for_another_token(self):
        self.cache.get(A, '60', self.value)
        self.cache.get(B, '60', self.blocked, wait=False)
        start=time.monotonic()
        value=self.cache.get(A, '60', self.value)
        self.assertLess(time.monotonic()-start, .1)
        self.assertEqual(value['token'], A)
        self.assertTrue(value['candles'])

    def test_same_key_has_one_inflight_fetch_and_native_waits_for_candles(self):
        calls=[]
        def fetch():
            calls.append(1)
            return self.blocked(A)
        with ThreadPoolExecutor(max_workers=8) as clients:
            results=[clients.submit(self.cache.get, A, '60', fetch) for _ in range(8)]
            while not calls: time.sleep(.001)
            self.release.set()
            for future in results: self.assertEqual(future.result()['candles'], self.value()['candles'])
        self.assertEqual(len(calls), 1)

    def test_stale_returns_immediately_and_only_refreshes_once(self):
        self.cache.get(A, '60', self.value)
        self.now+=100
        with patch.object(self.cache.pool, 'submit') as submit:
            first=self.cache.get(A, '60', self.value)
            second=self.cache.get(A, '60', self.value)
        self.assertTrue(first['stale']);self.assertTrue(first['refreshing'])
        self.assertEqual(first['fetchedAt'], 1000)
        self.assertEqual(second['candles'], first['candles']);submit.assert_called_once()

    def test_failed_refresh_keeps_snapshot_and_backs_off(self):
        self.cache.get(A, '60', self.value);self.now+=100
        def fail(): raise ValueError('provider down')
        self.cache._refresh(A+':60', fail)
        with patch.object(self.cache.pool, 'submit') as submit:
            value=self.cache.get(A, '60', fail)
        submit.assert_not_called();self.assertTrue(value['stale'])
        self.assertEqual(value['fetchedAt'], 1000);self.assertGreater(value['retryAfter'], 0)

    def test_expired_and_future_snapshots_are_not_rendered(self):
        for stamp in [-1, 2000]:
            self.cache.loaded=True;self.cache.values[A+':60']={**self.value(), 'fetchedAt':stamp}
            self.cache.failures[A+':60']=self.now
            value=self.cache.get(A, '60', self.value)
            self.assertEqual(value['candles'], []);self.assertIsNone(value['fetchedAt'])

    def test_refreshes_are_bounded(self):
        for i in range(20): self.cache.get('0x'+f'{i:040x}', '60', self.blocked, wait=False)
        self.assertEqual(len(self.cache.active), 8)

    def test_snapshot_survives_restart_without_provider_call(self):
        self.cache.get(A, '60', self.value)
        restored=ChartCache(self.cache.path, lambda:self.now)
        try:
            with patch.object(restored.pool, 'submit') as submit:
                value=restored.get(A, '60', self.value)
            submit.assert_not_called();self.assertEqual(value['candles'], self.value()['candles'])
        finally: restored.pool.shutdown()

    def test_interval_keys_and_lru_bound(self):
        self.cache.loaded=True
        for i in range(130):
            token='0x'+f'{i:040x}'
            self.cache._refresh(token+':60', lambda token=token:self.value(token))
        self.assertEqual(len(self.cache.values), 128)
        self.assertNotIn('0x'+'0'*40+':60', self.cache.values)
        self.cache.get(A, '15', lambda:self.value(A,'15'))
        self.assertEqual(self.cache.values[A+':15']['interval'], '15')

    def test_invalid_interval_does_not_trigger_identity_or_provider(self):
        with patch.object(n,'token_info') as identity:
            with self.assertRaises(s.Problem): n.chart(A,'bad')
        identity.assert_not_called()

    def test_preview_forwards_nonblocking_read(self):
        with patch.object(n, 'token_info', return_value={'address':A}), patch.object(n.CHART_CACHE, 'get', return_value={}) as get:
            n.chart(A, '60', wait=False)
            self.assertFalse(get.call_args.kwargs['wait'])
            n.chart(A, '60')
            self.assertTrue(get.call_args.kwargs['wait'])

    def test_rate_spacing_and_chart_priority_are_preserved(self):
        stamp=[1000.0];starts=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return b'{}'
        class Opener:
            def open(self,*args,**kwargs): starts.append(stamp[0]);return Response()
        previous=(n.API_AT,n.API_RETRY_AT)
        n.API_AT=999;n.API_RETRY_AT=0
        background=(999, object(), False)
        n.API_WAITERS.append(background)
        def wait(timeout): stamp[0]+=timeout
        try:
            with patch.object(n.time,'monotonic',side_effect=lambda:stamp[0]),patch.object(n.API_CONDITION,'wait',side_effect=wait),patch.object(n,'build_opener',return_value=Opener()):
                n.api('/trade/chart/'+A)
            self.assertGreaterEqual(starts[0]-999, 7.5)
            self.assertIn(background, n.API_WAITERS);self.assertFalse(n.API_BUSY)
        finally:
            n.API_WAITERS.remove(background);n.API_AT,n.API_RETRY_AT=previous


if __name__ == '__main__': unittest.main()
