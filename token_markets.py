"""Rally token discovery ranks local, identified assets; never quotes or signs orders."""
import base64
import binascii
import json
import math
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import closing

import service as s
import market_universe as universe
import nadfun
import token_images

CATEGORIES = ('crypto', 'trending', 'graduated', 'new')
VERSION = 'rally.tokens.v1'
LOCK = threading.Lock()
SNAPSHOTS = OrderedDict()
FRESH_SECONDS = 15
PAGE_SECONDS = 900


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (ValueError, TypeError, OverflowError):
        return default


def identity(value):
    value = str(value or '')
    if value.upper() == 'MON':
        return 'MON'
    return value.lower() if re.fullmatch(r'0x[0-9a-fA-F]{40}', value) else None


def normalized(item, now):
    t = dict(item)
    ident = identity(t.get('id') or t.get('address'))
    if not ident or t.get('chainId', 143) != 143:
        return None
    t.update(id=ident, address=ident, chainId=143)
    if not t.get('symbol') or not t.get('name'):
        return None
    stamp = number(t.get('referenceAt') if t.get('nadfun') else t.get('fetchedAt'))
    age = now - stamp
    fresh = 0 <= age <= (180 if t.get('nadfun') else 120)
    price = number(t.get('price'))
    t['price'] = price if price > 0 and 0 <= age <= 900 else None
    t['stale'] = not fresh
    t['fetchedAt'] = stamp
    t['priceAgeSeconds'] = max(0, age) if stamp else None
    t['change'] = number(t.get('change'), None) if fresh else None
    if not fresh:
        # These are observations, not an inferred zero return or live liquidity.
        t['rankingFresh'] = False
    else:
        t['rankingFresh'] = bool(t['price'])
    if t.get('marketCap') is not None:
        cap = number(t['marketCap'])
        t['marketCap'] = cap if cap > 0 and t['price'] else None
    return t


def candidates(wanted=None):
    """One local pass; curve identity wins over a duplicate DEX registry entry."""
    if wanted is not None and not wanted:
        return
    now = s.now()
    args = tuple(wanted or ())
    with s.LOCK:
        base = {identity(t['id']): dict(t) for t in s.GATEWAY.tokens if identity(t['id'])}
        if wanted is not None:
            base = {k: v for k, v in base.items() if k in wanted}
        prices = dict(s.GATEWAY.prices)
    seen = set()
    # Stream the database join. Decoding all launch JSON at once exceeds the
    # API service's memory budget when large inventories and charts overlap.
    with closing(universe.db()) as db:
        db.execute('ATTACH DATABASE ? AS rally_launches', (str(s.DB),))
        sql = ('SELECT a.address,a.info,a.price,n.info AS launch_info FROM assets a '
               'LEFT JOIN rally_launches.nad_tokens n ON n.address=a.address WHERE a.info IS NOT NULL')
        if wanted is not None:
            sql += ' AND a.address IN ('+','.join('?' for _ in args)+')'
        for row in db.execute(sql, args):
            ident = identity(row['address'])
            if not ident or ident in seen:
                continue
            seen.add(ident)
            info = {**base.get(ident, {}), **universe.decoded_metadata(row['info'])}
            old = json.loads(row['price']) if row['price'] else {}
            live = prices.get(ident, {})
            value = live if number(live.get('fetchedAt')) >= number(old.get('fetchedAt')) else old
            item = {**info, **value, 'id': ident}
            if row['launch_info']:
                launch = nadfun.public_info(json.loads(row['launch_info']))
                # Lifecycle and quote-asset restrictions remain contract-derived.
                if launch.get('graduated') and number(value.get('fetchedAt')) > number(launch.get('referenceAt')):
                    launch.update({k: value[k] for k in ('price','volume','change','liquidity','marketCap','priceSource') if k in value})
                    launch['referenceAt'] = value['fetchedAt']
                item.update(launch)
            t = normalized(item, now)
            if t:
                yield t
        sql = ('SELECT n.address,n.info FROM rally_launches.nad_tokens n '
               'LEFT JOIN assets a ON a.address=n.address WHERE a.info IS NULL')
        if wanted is not None:
            sql += ' AND n.address IN ('+','.join('?' for _ in args)+')'
        for row in db.execute(sql, args):
            seen.add(identity(row['address']))
            item = normalized(nadfun.public_info(json.loads(row['info'])), now)
            if item:
                yield item
    for ident, t in base.items():
        if ident not in seen:
            item = normalized({**t, **prices.get(ident, {})}, now)
            if item:
                yield item


def log_signal(value, ceiling):
    return min(1, math.log1p(max(0, number(value))) / math.log1p(ceiling))


def rank(t, category, now):
    launch = bool(t.get('nadfun')) and number(t.get('block')) > 0
    if t.get('nadfun') and not launch:
        return None
    graduated = launch and t.get('graduated') is True and t.get('phase') == 'dex'
    if category == 'crypto' and launch and not graduated:
        return None
    if category == 'graduated' and not graduated:
        return None
    created = number(t.get('created'))
    if category == 'new' and (not launch or not 0 < created <= now):
        return None
    fresh = t['rankingFresh']
    liquidity = log_signal(t.get('liquidity'), 10_000_000) if fresh else 0
    volume = log_signal(t.get('volume'), 10_000_000) if fresh else 0
    if category == 'trending':
        momentum = log_signal(t.get('change'), 500) if fresh else 0
        holders = log_signal(t.get('holders'), 10_000) if fresh else 0
        curve = min(1, max(0, number(t.get('progressBps')) / 10000)) if launch and not graduated and fresh else 0
        score = .35*volume + .25*momentum + .25*max(liquidity, .6*curve) + .15*holders
    else:
        score = .65*liquidity + .35*volume
    health = int(not t.get('locked') and t.get('tradeSupported') is not False)
    if category == 'new':
        return (-created, -health, -int(fresh), -score, t['id'])
    return (-int(fresh), -health, -score, t['id'])


def parameters(params):
    category = params.get('category', 'crypto')
    if category not in CATEGORIES:
        raise s.Problem('Unknown token category')
    query = str(params.get('query', '')).strip().lower()[:120]
    try:
        limit = int(params.get('limit', 40))
        if not 1 <= limit <= 60:
            raise ValueError()
    except (TypeError, ValueError):
        raise s.Problem('Invalid token page')
    watch = None
    if 'watch' in params:
        values = str(params['watch']).split(',') if params['watch'] else []
        if len(values) > 300 or any(not identity(x) for x in values):
            raise s.Problem('Invalid watchlist')
        watch = tuple(sorted(set(identity(x) for x in values)))
    return category, query, limit, watch


def catalog(params):
    category, query, limit, watch = parameters(params)
    signature = (category, query, watch)
    cursor = params.get('cursor')
    offset = 0
    with LOCK:
        clock = time.monotonic()
        for key in list(SNAPSHOTS):
            if clock-SNAPSHOTS[key]['clock'] > PAGE_SECONDS:
                del SNAPSHOTS[key]
        if cursor:
            try:
                if not isinstance(cursor, str) or len(cursor) > 200:
                    raise ValueError()
                key, offset = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                snapshot = SNAPSHOTS[key]
                if snapshot['signature'] != signature or type(offset) is not int or not 0 < offset < len(snapshot['ids']):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError):
                raise s.Problem('This list has updated. Refresh to continue.', 400, 'token_page_expired')
        else:
            key = next((key for key, v in reversed(SNAPSHOTS.items()) if v['signature'] == signature and clock-v['clock'] < FRESH_SECONDS), None)
            if key is None:
                ordered = []
                now = s.now()
                for t in candidates(set(watch) if watch is not None else None):
                    if query and query not in (t['symbol']+' '+t['name']+' '+t['id']).lower():
                        continue
                    value = rank(t, category, now)
                    if value is not None:
                        ordered.append((value, t['id']))
                ordered.sort()
                key = uuid.uuid4().hex
                SNAPSHOTS[key] = {'ids': [ident for _, ident in ordered], 'signature': signature, 'clock': clock, 'asOf': s.now()}
                while len(SNAPSHOTS) > 16 or sum(len(v['ids']) for v in SNAPSHOTS.values()) > 300_000 and len(SNAPSHOTS) > 1:
                    SNAPSHOTS.popitem(last=False)
            snapshot = SNAPSHOTS[key]
        ids = snapshot['ids'][offset:offset+limit]
        total = len(snapshot['ids'])
        as_of = snapshot['asOf']
    tokens = resolved(ids)
    next_cursor = base64.urlsafe_b64encode(json.dumps([key, offset+limit]).encode()).decode().rstrip('=') if offset+limit < total else None
    return {'tokens': tokens, 'category': category, 'total': total, 'nextCursor': next_cursor,
            'ranking': {'id': VERSION, 'asOf': as_of}, 'fetchedAt': s.now(), 'chainId': 143, 'financialTransactions': 0}


def resolved(ids):
    if not ids:
        return []
    found = {t['id']: t for t in candidates(set(ids))}
    tokens = [found[ident] for ident in ids if ident in found]
    for t in tokens:
        t.pop('rankingFresh', None)
    token_images.decorate(tokens)
    with s.LOCK:
        for t in tokens:
            s.GATEWAY.token_map.setdefault(t['id'], t)
    import launch_ingestion
    launch_ingestion.viewed([t for t in tokens if t.get('nadfun')][:24])
    with universe.LOCK:
        for t in tokens:
            if not t.get('nadfun'):
                universe.VIEWED[t['id']] = s.now()
        while len(universe.VIEWED) > 256:
            universe.VIEWED.pop(next(iter(universe.VIEWED)))
    return tokens


def references(params):
    ids = list(dict.fromkeys(str(params.get('assets', '')).split(',')))
    if not 1 <= len(ids) <= 60 or any(not identity(x) for x in ids):
        raise s.Problem('Invalid token references')
    return {'tokens': resolved([identity(x) for x in ids]), 'fetchedAt': s.now(), 'financialTransactions': 0}
