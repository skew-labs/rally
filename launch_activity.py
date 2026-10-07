"""Public, read-only launch revenue. No provider calls or wallet authority.

Only registered token vaults and finalized Rally receipts are exposed. Buyer
identities, invoice/feed identifiers and unbound payments stay private. Cached
all-time vault balances are deliberately separate from receipt-period totals.
"""
import json
import re
from eth_abi import decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak
import service as s
import social
import launchpad
import community_tokens as ct

PERIODS = {'24h': 86400, '7d': 604800, '30d': 2592000, 'all': None}
TRANSFER = '0x' + keccak(text='Transfer(address,address,uint256)').hex()
BUYBACK = '0x' + keccak(text='BuybackExecuted(uint256,uint256,uint256,uint256)').hex()
FIELDS = ('salesRaw', 'creatorPayoutRaw', 'reservedRaw', 'feesClaimedRaw', 'buybackSpentRaw')


def object_json(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def raw(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not re.fullmatch(r'\d{1,78}', str(value)):
        raise ValueError('Invalid recorded amount')
    return int(value)


def registry(viewer):
    tokens = {}
    for row in s.rows('SELECT l.*, n.info FROM launch_tokens l LEFT JOIN nad_tokens n ON n.address=l.token ORDER BY l.created DESC LIMIT 500'):
        if not social.visible(viewer, row['identity']):
            continue
        info = object_json(row['info'])
        tokens[row['token'].lower()] = {
            'address': row['token'].lower(), 'name': info.get('name') or 'Token',
            'symbol': info.get('symbol') or '', 'logoURI': info.get('logoURI'),
            'creator': launchpad.creator(row['identity']), 'community': row['community'],
            'beneficiary': object_json(row['beneficiary']) or None, 'venue': 'nad.fun V2',
            'allocations': object_json(row['allocations']), 'vault': None, 'stats': None,
            'verifiedAt': None, 'stale': True, 'burnMethod': 'dead_address',
        }
    for row in s.rows("SELECT owner FROM creator_tokens WHERE state='live' LIMIT 50"):
        if not social.visible(viewer, row['owner']):
            continue
        token = ct.public(row['owner'])
        if not token:
            continue
        tokens[token['address'].lower()] = {k: token.get(k) for k in
            ('address', 'name', 'symbol', 'logoURI', 'community', 'venue', 'vault', 'stats', 'verifiedAt', 'stale')}
        tokens[token['address'].lower()].update(creator=launchpad.creator(row['owner']),
            beneficiary=None, allocations=None, burnMethod='supply_burn')
    for row in s.rows('SELECT * FROM nad_revenue_vaults ORDER BY verified DESC LIMIT 500'):
        token = tokens.get(row['token'].lower())
        if token and token['creator'] and token['creator']['id'] == row['owner']:
            token.update(vault=row['vault'], stats=object_json(row['stats']),
                verifiedAt=row['verified'], stale=not row['verified'] or s.now()-row['verified'] > 120)
        elif token and token['creator'] and token['creator'].get('owner') == row['owner']:
            token.update(vault=row['vault'], stats=object_json(row['stats']),
                verifiedAt=row['verified'], stale=not row['verified'] or s.now()-row['verified'] > 120)
    # Only already-public counters are serialized, never keeper/policy credentials.
    for token in tokens.values():
        stats = token['stats']
        token['stats'] = {k: stats[k] for k in ('grossRevenue', 'creatorPaid', 'pendingBuyback',
            'quoteSpent', 'tokensBought', 'tokensBurned', 'paused') if k in stats} if stats is not None else None
    return tokens


def receipt_ok(receipt, tx):
    return (bool(re.fullmatch(r'0x[0-9a-fA-F]{64}', tx or '')) and
        str(receipt.get('transactionHash', '')).lower() == tx.lower() and
        receipt.get('status') == '0x1' and bool(receipt.get('blockHash')))


def transfers(receipt, asset, source, recipient, amount):
    return any(not l.get('removed') and str(l.get('address', '')).lower() == asset.lower() and
        len(l.get('topics', [])) == 3 and l['topics'][0].lower() == TRANSFER and
        '0x'+l['topics'][1][-40:].lower() == source.lower() and
        '0x'+l['topics'][2][-40:].lower() == recipient.lower() and
        int(l.get('data', '0x0'), 16) == amount for l in receipt.get('logs', []))


def invoice_events(row, tokens):
    terms = object_json(row['community_terms'])
    token = tokens.get(str(terms.get('communityToken', '')).lower())
    receipt = object_json(row['receipt'])
    if not token or not token['vault'] or token['vault'].lower() != str(terms.get('vault', '')).lower() or not receipt_ok(receipt, row['tx']):
        return []
    gross = raw(row['amount_raw']); bps = raw(terms['buybackBps'])
    if bps > 10000 or not gross:
        return []
    reserve = gross*bps//10000; paid = gross-reserve
    # Recheck the exact public vault event and actual creator transfer. No buyer
    # or subscription metadata leaves this function.
    events = [l for l in receipt.get('logs', []) if not l.get('removed') and
        str(l.get('address', '')).lower() == token['vault'].lower() and
        len(l.get('topics', [])) == 4 and l['topics'][0].lower() == ct.REVENUE_TOPIC and
        l['topics'][1].lower() == '0x'+ct.word(row['id']).hex() and
        l['topics'][2].lower() == '0x'+ct.word(row['feed']).hex() and
        '0x'+l['topics'][3][-40:].lower() == row['wallet'].lower()]
    if len(events) != 1 or decode(['uint256','uint256','uint256','uint64'], bytes.fromhex(events[0]['data'][2:])) != (gross, paid, reserve, terms['policyNonce']):
        return []
    if not transfers(receipt, s.USDC, row['wallet'], token['vault'], gross) or paid and not transfers(receipt, s.USDC, token['vault'], terms['creator'], paid):
        return []
    result = [dict(token=token['address'], kind='creator_payout', asset='USDC', decimals=6,
        amountRaw=str(paid), salesRaw=str(gross), reservedRaw=str(reserve),
        recipient=terms['creator'], tx=row['tx'], recordedAt=row['settled'], state='finalized')]
    for log in receipt.get('logs', []):
        if log.get('removed') or str(log.get('address', '')).lower() != token['vault'].lower() or log.get('topics') != [BUYBACK]:
            continue
        spent, bought, burned, treasury = decode(['uint256']*4, bytes.fromhex(log['data'][2:]))
        if spent and bought and burned+treasury == bought:
            result.append(dict(token=token['address'], kind='buyback', asset='USDC', decimals=6,
                amountRaw=str(spent), tokensBoughtRaw=str(bought), tokensBurnedRaw=str(burned),
                burnMethod=terms.get('burnMethod', token['burnMethod']), tx=row['tx'],
                recordedAt=row['settled'], state='finalized', logIndex=log.get('logIndex')))
    return result


def execution_event(row, tokens):
    payload = object_json(row['payload']); summary = payload.get('summary') or {}
    token = tokens.get(str(summary.get('token', '')).lower()); outcome = object_json(row['outcome'])
    if not token or not receipt_ok(outcome.get('receipt') or {}, row['tx']):
        return None
    event = dict(token=token['address'], tx=row['tx'], recordedAt=row['created'], state='finalized')
    if row['venue'] == 'nadfees' and row['kind'] in {'creator_claim', 'gift_claim'} and outcome.get('businessState') == 'fees_claimed':
        asset = outcome.get('deliveryAsset'); quoted = raw(outcome['quotedRaw'])
        delivered = raw(outcome['nativeDeliveredRaw'] if asset == 'MON' else outcome['deliveredRaw'])
        if asset not in {'MON','WMON','LVMON'} or not quoted or delivered < quoted or outcome.get('recipient') != (payload.get('transaction') or {}).get('from'):
            return None
        event.update(kind='fee_claim', asset=asset, decimals=18, amountRaw=str(delivered), recipient=outcome['recipient'])
    elif row['venue'] == 'nadrevenue' and row['kind'] == 'revenue_execute' and outcome.get('businessState') == 'buyback_executed':
        delivery = outcome.get('delivery') or {}; spent = raw(delivery['quoteSpentRaw'])
        bought = raw(delivery['tokensBoughtRaw']); sunk = raw(delivery['tokensSunkRaw']); kept = raw(delivery['creatorTokensRaw'])
        if not token['vault'] or str((payload.get('transaction') or {}).get('to', '')).lower() != token['vault'].lower() or str(delivery.get('token', '')).lower() != token['address'] or not spent or not bought or sunk+kept != bought:
            return None
        event.update(kind='buyback', asset='USDC', decimals=6, amountRaw=str(spent),
            tokensBoughtRaw=str(bought), tokensBurnedRaw=str(sunk), burnMethod='dead_address')
    else:
        return None
    return event


def overview(who=None, period='30d', token=None, limit='50'):
    if period not in PERIODS:
        raise s.Problem('Choose 24h, 7d, 30d or all')
    if not str(limit).isdigit() or not 1 <= int(limit) <= 200:
        raise s.Problem('Choose a result limit from 1 to 200')
    if token and not re.fullmatch(r'0x[0-9a-fA-F]{40}', token):
        raise s.Problem('Enter a Monad token address')
    now = s.now(); start = now-PERIODS[period] if PERIODS[period] else 0
    tokens = registry(who['user'] if who else None)
    if token:
        token = token.lower()
        if token not in tokens:
            raise s.Problem('Registered token not found', 404)
        tokens = {token: tokens[token]}
    events = []; seen = set()
    with s.connection() as db:
        invoices = db.execute("SELECT id,feed,wallet,amount_raw,tx,settled,community_terms,receipt FROM invoices WHERE state='paid' AND settled>=? AND settled<=? ORDER BY settled DESC,id DESC LIMIT 1001", (start, now)).fetchall()
        executions = db.execute("SELECT e.tx,e.outcome,e.created,p.payload,p.venue,p.kind FROM execution_records e JOIN execution_plans p ON p.id=e.plan WHERE e.state='finalized' AND e.created>=? AND e.created<=? AND p.venue IN ('nadfees','nadrevenue') ORDER BY e.created DESC,e.id DESC LIMIT 1001", (start, now)).fetchall()
    for row in invoices[:1000]:
        try:
            events.extend(invoice_events(dict(row), tokens))
        except (ValueError, TypeError, KeyError, OverflowError, DecodingError):
            continue
    for row in executions[:1000]:
        try:
            event = execution_event(dict(row), tokens)
            if event:
                events.append(event)
        except (ValueError, TypeError, KeyError, OverflowError, DecodingError):
            continue
    result = []
    for event in sorted(events, key=lambda e: (e['recordedAt'], e['tx']), reverse=True):
        key = (event['tx'].lower(), event['token'], event['kind'], event.get('logIndex'))
        if key in seen:
            continue
        seen.add(key); result.append(event)
    series_start = (start or min((e['recordedAt'] for e in result), default=now-30*86400))
    step = 3600 if period == '24h' else max(86400, ((now-series_start)//86400//30+1)*86400)
    series_start = series_start//step*step
    groups = {a: {'asset':a, 'decimals':d, 'count':0, **dict.fromkeys(FIELDS, 0)} for a,d in [('USDC',6),('MON',18),('WMON',18),('LVMON',18)]}
    buckets = [{**{'at':at}, **{a:dict.fromkeys(FIELDS, 0) for a in groups}} for at in range(series_start, now+1, step)]
    for event in result:
        group = groups[event['asset']]; group['count'] += 1
        bucket = buckets[(event['recordedAt']-series_start)//step][event['asset']]
        amounts = {'creator_payout':{'salesRaw':event.get('salesRaw','0'), 'creatorPayoutRaw':event['amountRaw'], 'reservedRaw':event.get('reservedRaw','0')}, 'fee_claim':{'feesClaimedRaw':event['amountRaw']}, 'buyback':{'buybackSpentRaw':event['amountRaw']}}[event['kind']]
        for field, value in amounts.items():
            group[field] += raw(value); bucket[field] += raw(value)
    for group in groups.values():
        for field in FIELDS:
            group[field] = str(group[field])
    for bucket in buckets:
        for asset in groups:
            bucket[asset] = {k:str(v) for k,v in bucket[asset].items()}
    return {'period':period, 'token':token, 'fetchedAt':now, 'chainId':143,
        'tokens':list(tokens.values()), 'totals':list(groups.values()),
        'activity':result[:int(limit)], 'count':len(result), 'hasMore':len(result)>int(limit),
        'series':buckets, 'seriesStep':step, 'historyLimited':len(invoices)>1000 or len(executions)>1000,
        'coverage':'Rally-recorded finalized receipts only. Dates use recording time; claims use request time. Vault counters are separate all-time snapshots. Other venue activity is not indexed.'}
