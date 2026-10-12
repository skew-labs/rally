"""Bounded, exact-source price observations. These are not exchange fills.

The public reader reuses the live collectors, never issues per-view provider
requests. A price/source change starts a new series; quiet periods stay quiet.
"""
import math
import re
import threading
import time
from collections import deque
import service as s

LOCK = threading.Lock()
SERIES = {}
LIMIT = 240
MAX_SERIES = 256
TTL = 600


def record(asset, kind, value, stamp, source, source_url, identity, select=False):
    try:
        value = float(value)
        stamp = int(stamp)
    except (ValueError, TypeError, OverflowError):
        return
    if not math.isfinite(value) or value <= 0 or not 0 <= s.now() - stamp <= 180:
        return
    key = (kind, str(asset).lower())
    with LOCK:
        state = SERIES.get(key)
        # Only viewed markets allocate observation buffers.
        if not state or time.monotonic() - state['viewed'] > TTL:
            return
        signature = (str(source), str(identity))
        if state.get('signature') != signature:
            if not select:
                return
            state.update(signature=signature, points=deque(maxlen=LIMIT), epoch=s.uid())
        previous = state['points'][-1] if state['points'] else None
        if previous and (stamp < previous['time'] or stamp == previous['time'] and value == previous['value']):
            return
        state['sequence'] += 1
        state['points'].append({'id':state['sequence'], 'time':stamp, 'value':value})
        state.update(source=source, sourceURL=source_url)


def current(asset, kind):
    if kind == 'perps':
        import perp_universe as p
        market = next((m for m in p.catalog()['markets'] if str(m['id']) == asset), None)
        if not market:
            raise s.Problem('Unknown market', 404)
        record(asset, kind, market.get('mark'), market.get('observationAt'), market.get('priceSource') or market['venue'], market.get('sourceURL', ''), market['venue'], select=True)
    else:
        # A nad.fun identity must come from the verified token registry.
        import nadfun
        row = s.one('SELECT info FROM nad_tokens WHERE address=?', (asset.lower(),)) if asset.startswith('0x') else None
        if row:
            import json
            t = nadfun.public_info(json.loads(row['info']))
            if t.get('chainId') != 143 or t.get('address','').lower() != asset.lower():
                raise s.Problem('Tick identity changed', 502, 'chart_identity')
            import launch_ingestion
            launch_ingestion.viewed([t])
            if t.get('graduated'):
                import market_universe as u
                pools = u.references(asset.lower())['tokens']
                if pools and pools[0].get('price') and not pools[0].get('stale'):
                    price = pools[0]
                    record(asset, kind, price['price'], price.get('fetchedAt'), price.get('priceSource') or 'Monad pool reference', price.get('source',''), price.get('pair',asset.lower()), select=True)
                    return
            record(asset, kind, t.get('price'), t.get('referenceAt'), t.get('priceSource') or 'nad.fun USD reference', 'https://nad.fun/tokens/'+asset, t.get('pair') or asset.lower(), select=True)
        else:
            import market_universe as u
            token = u.references(asset)['tokens']
            if not token:
                raise s.Problem('Unknown asset', 404)
            t = token[0]
            record(asset, kind, t.get('price'), t.get('fetchedAt'), t.get('priceSource') or 'Monad pool reference', t.get('source', ''), t.get('pair', asset), select=True)


def read(asset, kind='spot', after=0):
    asset = str(asset)
    if kind not in {'spot', 'perps'} or '://' in asset or not (asset == 'MON' or re.fullmatch(r'0x[0-9a-fA-F]{40}', asset) if kind == 'spot' else re.fullmatch(r'[A-Za-z0-9:/_.-]{1,100}', asset)):
        raise s.Problem('Invalid tick market')
    try:
        after = int(after)
        if after < 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise s.Problem('Invalid tick cursor')
    key = (kind, asset.lower())
    with LOCK:
        now = time.monotonic()
        for k in list(SERIES):
            if now - SERIES[k]['viewed'] > TTL:
                SERIES.pop(k, None)
        if key not in SERIES:
            if len(SERIES) >= MAX_SERIES:
                SERIES.pop(min(SERIES, key=lambda k:SERIES[k]['viewed']))
            SERIES[key] = {'points':deque(maxlen=LIMIT), 'viewed':now, 'sequence':0, 'epoch':s.uid()}
        SERIES[key]['viewed'] = now
    current(asset, kind)
    with LOCK:
        state = SERIES[key]
        # A reset or expired cursor receives the bounded current series.
        points = list(state['points'])
        reset = after > state['sequence'] or bool(points and after and after < points[0]['id'] - 1)
        return {'asset':asset, 'kind':kind, 'chainId':143, 'epoch':state['epoch'],
                'points':points if reset or not after else [p for p in points if p['id'] > after],
                'cursor':state['sequence'], 'reset':reset, 'source':state.get('source'),
                'sourceURL':state.get('sourceURL'), 'lastObservation':points[-1]['time'] if points else None,
                'stale':not points or s.now()-points[-1]['time'] > 60,
                'observationType':'price_update', 'refreshMs':1000, 'pointBudget':LIMIT,
                'financialTransactions':0}
