"""Remote preview server. Bind only to loopback; reach it through SSH forwarding."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import math
import time
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
CHART_ASSETS = frozenset('MON BTC ETH SOL HYPE PENGU LINK ONDO AAVE PEPE UNI USDC'.split())
CHART_INTERVALS = frozenset(('15', '60', '240', 'D'))
CHART_CACHE = {}
CHART_LOCK = Lock()


def candles(asset, interval):
    """Bounded, public spot-reference data. No trading or wallet endpoints."""
    if asset not in CHART_ASSETS or interval not in CHART_INTERVALS:
        raise ValueError('Unsupported chart')
    key = (asset, interval)
    with CHART_LOCK:
        cached = CHART_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < 15:
            return cached[1]
    query = urlencode(dict(category='spot', symbol=asset+'USDT', interval=interval, limit=300))
    with urlopen('https://api.bybit.com/v5/market/kline?'+query, timeout=8) as response:
        raw = json.loads(response.read(512_000))
    result = raw.get('result', {})
    if raw.get('retCode') != 0 or result.get('symbol') != asset+'USDT' or result.get('category') != 'spot':
        raise RuntimeError('Invalid provider response')
    rows = {}
    for row in result.get('list', []):
        ts = int(row[0]) // 1000
        o, h, l, c, v = map(float, row[1:6])
        if ts <= 0 or not all(math.isfinite(x) for x in (o,h,l,c,v)) or not (0 < l <= min(o,c) <= max(o,c) <= h) or v < 0:
            raise RuntimeError('Invalid candle')
        rows[ts] = dict(time=ts, open=o, high=h, low=l, close=c, volume=v)
    if not rows:
        raise RuntimeError('No candles available')
    body = dict(asset=asset, symbol=asset+'USDT', interval=interval, provider='Bybit', market='spot', fetchedAt=int(time.time()), candles=[rows[t] for t in sorted(rows)])
    with CHART_LOCK:
        CHART_CACHE[key] = (time.monotonic(), body)
    return body


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != '/api/chart':
            return super().do_GET()
        params = parse_qs(url.query)
        try:
            body = candles(params.get('asset', [''])[0], params.get('interval', [''])[0])
            status = 200
        except ValueError:
            body, status = {'error': 'Unsupported chart'}, 400
        except Exception:
            body, status = {'error': 'Chart data unavailable'}, 502
        data = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        if self.path.startswith('/assets/'):
            self.send_header('Cache-Control', 'public, max-age=86400')
        else:
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 4186), PreviewHandler).serve_forever()
