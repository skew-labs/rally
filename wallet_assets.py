"""Account-scoped, progressive on-chain balances. No signer or token approvals."""
import copy
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation, localcontext
import service as s

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wallet-balances')
LOCK = threading.Lock()
CACHE, JOBS = {}, {}


def decimal(value):
    try:
        n = Decimal(str(value))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def value_snapshot(snapshot, gateway):
    result = copy.deepcopy(snapshot)
    prices = {t['id']: t for t in gateway.markets().get('tokens', [])}
    total = prior = covered = Decimal(0)
    priced = unpriced = 0
    with localcontext() as ctx:
        ctx.prec = 96
        for h in result['holdings']:
            token = dict(gateway.token_map.get(h['asset'], h.get('token', {})))
            token.update(prices.get(h['asset'], {}))
            h['token'] = token
            price, amount = decimal(token.get('price')), decimal(h['amount'])
            valid = price is not None and price > 0 and amount is not None
            value = amount * price if valid else None
            h['valueUSD'] = format(value, 'f') if value is not None else None
            if not amount:
                continue
            if value is None:
                unpriced += 1
                continue
            priced += 1
            total += value
            change = decimal(token.get('change'))
            if change is not None and change > -100:
                prior += value / (1 + change / 100)
                covered += value
        change = ((covered / prior - 1) * 100) if prior and covered == total and not unpriced else None
    # A price basket change is not account PnL (deposits and positions are excluded).
    result['valuation'] = {
        'valueUSD': format(total, 'f') if priced or (not unpriced and result.get('complete')) else None,
        'change24hPercent': format(change, 'f') if change is not None else None,
        'changeBasis': 'current_holdings_price_change', 'pricedAssets': priced,
        'unpricedAssets': unpriced, 'partial': bool(unpriced or result['unavailable'] or not result.get('complete')),
        'includes': 'wallet_tokens', 'currency': 'USD',
    }
    return result


def catalog(gateway, wallet, previous):
    referenced = s.rows('''SELECT asset FROM watches WHERE user_id IN (SELECT id FROM accounts WHERE wallet=?)
        UNION SELECT q.input FROM quotes q JOIN orders o ON o.quote_id=q.id WHERE q.wallet=?
        UNION SELECT q.output FROM quotes q JOIN orders o ON o.quote_id=q.id WHERE q.wallet=? LIMIT 200''', (wallet, wallet, wallet))
    launches = s.rows('SELECT info FROM nad_tokens ORDER BY observed DESC LIMIT 150')
    owned = s.rows('''SELECT info FROM nad_tokens WHERE address IN (
        SELECT json_extract(p.payload,'$.summary.token') FROM execution_plans p JOIN execution_records r ON r.plan=p.id WHERE p.wallet=?
        ) LIMIT 200''', (wallet,))
    import json
    tokens = {t['id']: t for t in gateway.tokens[1:]}
    tokens.update({t['id']: t for t in (json.loads(x['info']) for x in launches + owned)})
    for row in referenced:
        t = gateway.token_map.get(row['asset'])
        if t and t['id'] != 'MON':
            tokens[t['id']] = t
    for h in previous.get('holdings', []):
        t = h.get('token') or gateway.token_map.get(h['asset'])
        if t and h['asset'] != 'MON':
            tokens[h['asset']] = t
    gateway.token_map.update(tokens)
    priority = {s.USDC, '0xe80e4f02aadf8f51e2f4c39c4cb14f8de4064438'}
    priority.update(h['asset'] for h in previous.get('holdings', []))
    priority.update(r['asset'] for r in referenced)
    return sorted(tokens.values(), key=lambda t: (t['id'] not in priority, t['id']))


def empty(wallet):
    return {'wallet': wallet, 'holdings': [], 'unavailable': [], 'fetchedAt': None,
            'chainId': 143, 'blockNumber': None, 'complete': False, 'refreshing': True}


def invalidate(wallet, block):
    """A verified send makes older snapshots eligible for immediate refresh."""
    wallet = wallet.lower()
    with LOCK:
        cached = CACHE.setdefault(wallet, empty(wallet))
        if (cached.get('blockNumber') or 0) < block:
            cached['refreshAfterBlock'] = max(block, cached.get('refreshAfterBlock', 0))
            cached['attemptAt'] = 0


def scan(gateway, wallet, previous):
    from eth_abi import encode, decode
    from eth_utils import keccak
    result = empty(wallet)
    # Retain known balances if a batch fails, explicitly marked as unavailable/stale.
    holdings = {h['asset']: dict(h, staleBalance=True) for h in previous.get('holdings', [])}
    def publish():
        result['holdings'] = list(holdings.values())
        with LOCK:
            after = CACHE.get(wallet, {}).get('refreshAfterBlock', 0)
            if after and (result.get('blockNumber') or 0) < after:
                result.update(refreshAfterBlock=after, attemptAt=0)
            else:
                result.pop('refreshAfterBlock', None)
            CACHE[wallet] = copy.deepcopy(result)
    try:
        block = s.rpc('eth_blockNumber', [])
        native = int(s.rpc('eth_getBalance', [wallet, block]), 16)
        result.update(blockNumber=int(block, 16), fetchedAt=s.now())
        holdings['MON'] = {'asset': 'MON', 'amount': s.units(native, 18), 'amountRaw': str(native), 'staleBalance': False}
        publish()
        tokens = catalog(gateway, wallet, previous)
        # First priority batch is immediately available; remaining batches use bounded RPC batches.
        parts = [tokens[i:i+40] for i in range(0, len(tokens), 40)]
        groups = [parts[:1]] + [parts[i:i+4] for i in range(1, len(parts), 4)] if parts else []
        for group in groups:
            requests = []
            for part in group:
                calls = [(t['address'], True, bytes.fromhex('70a08231'+wallet[2:].rjust(64, '0'))) for t in part]
                requests.append({'to': s.MULTICALL, 'data': '0x'+keccak(text='aggregate3((address,bool,bytes)[])').hex()[:8]+encode(['(address,bool,bytes)[]'], [calls]).hex(), 'gas': hex(3_000_000)})
            try:
                responses = s.rpc_call_batch(requests, block)
            except Exception:
                responses = [None] * len(group)
            for part, response in zip(group, responses):
                try:
                    raw = response.get('result') if isinstance(response, dict) else response
                    values = decode(['(bool,bytes)[]'], bytes.fromhex(raw[2:]))[0]
                    if len(values) != len(part):
                        raise ValueError('Balance result length')
                except Exception:
                    values = [(False, b'')] * len(part)
                for t, (success, value) in zip(part, values):
                    if not success or len(value) != 32:
                        result['unavailable'].append(t['id'])
                        continue
                    amount = int.from_bytes(value, 'big')
                    if amount:
                        holdings[t['id']] = {'asset': t['id'], 'amount': s.units(amount, t['decimals']), 'amountRaw': str(amount), 'token': t, 'staleBalance': False}
                    else:
                        holdings.pop(t['id'], None)
            publish()
        result['complete'] = not result['unavailable']
    except Exception:
        result['error'] = 'Balances are refreshing. Your last snapshot is kept.'
        if not result['fetchedAt']:
            result.update(fetchedAt=previous.get('fetchedAt'), blockNumber=previous.get('blockNumber'))
    finally:
        result.update(refreshing=False, attemptAt=s.now())
        publish()
        with LOCK:
            JOBS.pop(wallet, None)


def portfolio(gateway, wallet):
    wallet = str(wallet).lower()
    if not re.fullmatch(r'0x[0-9a-f]{40}', wallet) or wallet == s.ZERO:
        raise s.Problem('Invalid wallet address')
    with LOCK:
        cached = CACHE.get(wallet)
        if wallet not in JOBS and (not cached or s.now()-cached.get('attemptAt', 0) >= 30):
            if len(JOBS) < 8:
                # Set marker before submission; a very fast job cannot leave a stale marker.
                JOBS[wallet] = True
                POOL.submit(scan, gateway, wallet, copy.deepcopy(cached or {}))
        result = copy.deepcopy(cached or empty(wallet))
        result['refreshing'] = wallet in JOBS
        if len(CACHE) > 256:
            for key in sorted(CACHE, key=lambda k: CACHE[k].get('attemptAt', 0))[:len(CACHE)-256]:
                if key not in JOBS:
                    CACHE.pop(key, None)
    return value_snapshot(result, gateway)
