"""Bounded nad.fun holder snapshots; discovery data, not trade execution evidence."""
import copy
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
import service as s

LOCK = threading.Lock()
CACHE, ACTIVE = {}, set()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='token-holders')


def normalize(asset, token, raw):
    values = raw.get('holders')
    if not isinstance(values, list) or not isinstance(raw.get('total_count'), int):
        raise ValueError('Holder response changed')
    output, seen = [], set()
    for row in values[:20]:
        account, balance = row.get('account_info', {}), row.get('balance_info', {})
        wallet = str(account.get('account_id', '')).lower()
        amount = str(balance.get('balance', ''))
        if not re.fullmatch(r'0x[0-9a-f]{40}', wallet) or wallet in seen or not amount.isdigit() or len(amount) > 78:
            continue
        seen.add(wallet)
        with localcontext() as ctx:
            ctx.prec = 96
            quantity = Decimal(amount) / (Decimal(10) ** token['decimals'])
        output.append({'address': wallet, 'name': str(account.get('nickname') or '')[:80],
                       'image': str(account.get('image_uri') or '')[:1024],
                       'amount': format(quantity, 'f'), 'amountRaw': amount})
    return {'asset': asset, 'holders': output, 'total': max(0, raw['total_count']),
            'fetchedAt': s.now(), 'source': 'nad.fun', 'indexed': True, 'limit': 20}


def refresh(asset, token):
    import nadfun
    try:
        value = normalize(asset, token, nadfun.api('/trade/holder/'+asset+'?page=1&limit=20&direction=DESC'))
        with LOCK:
            CACHE[asset] = value
    except Exception:
        with LOCK:
            CACHE[asset] = dict(CACHE.get(asset, {'asset': asset, 'holders': [], 'total': None, 'fetchedAt': None, 'indexed': True, 'source': 'nad.fun'}), error='Holder data is temporarily unavailable.', attemptAt=s.now())
    finally:
        with LOCK:
            ACTIVE.discard(asset)


def holders(asset):
    asset = str(asset).lower()
    if not re.fullmatch(r'0x[0-9a-f]{40}', asset):
        return {'asset': asset, 'holders': [], 'indexed': False, 'refreshing': False}
    token = s.GATEWAY.token_map.get(asset)
    if not token or not token.get('nadfun'):
        return {'asset': asset, 'holders': [], 'indexed': False, 'refreshing': False}
    with LOCK:
        cached = CACHE.get(asset)
        stamp = max((cached or {}).get('fetchedAt') or 0, (cached or {}).get('attemptAt') or 0)
        if asset not in ACTIVE and s.now()-stamp > 60 and len(ACTIVE) < 3:
            ACTIVE.add(asset)
            POOL.submit(refresh, asset, dict(token))
        value = copy.deepcopy(cached or {'asset': asset, 'holders': [], 'total': None, 'fetchedAt': None, 'source': 'nad.fun', 'indexed': True})
        value.update(refreshing=asset in ACTIVE, stale=bool(cached and s.now()-(cached.get('fetchedAt') or 0)>90))
        if len(CACHE) > 128:
            for key in sorted(CACHE, key=lambda k: CACHE[k].get('fetchedAt') or 0)[:len(CACHE)-128]:
                if key not in ACTIVE:
                    CACHE.pop(key, None)
        return value
