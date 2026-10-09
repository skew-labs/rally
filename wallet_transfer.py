"""Unsigned, owner-scoped MON/ERC20 sends through the existing durable execution flow."""
import re
from eth_utils import keccak, is_checksum_address
import service as s


def recipient(value, sender):
    value = str(value).strip()
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}', value) or value.lower() in {s.ZERO, sender.lower()}:
        raise s.Problem('Enter a different valid recipient wallet')
    letters = value[2:]
    if letters != letters.lower() and letters != letters.upper() and not is_checksum_address(value):
        raise s.Problem('Recipient address checksum is invalid')
    return value.lower()


def plan(who, data):
    import venues as v
    if data.get('kind') != 'send':
        raise s.Problem('Unsupported wallet action')
    user, sender = v.wallet(who)
    destination = recipient(data.get('recipient'), sender)
    asset = str(data.get('asset', 'MON'))
    asset = asset if asset == 'MON' else asset.lower()
    token = s.GATEWAY.token_map.get(asset)
    if not token:
        raise s.Problem('Refresh your wallet to load this token', 409)
    amount = v.raw(data.get('amount'), token['decimals'])
    if amount >= 2**256:
        raise s.Problem('Amount is too large')
    native = asset == 'MON'
    code = None if native else s.rpc('eth_getCode', [token['address'], 'latest'])
    if not native and (not code or code == '0x'):
        raise s.Problem('Token contract is unavailable', 409)
    payload = {'summary': {'action': 'send', 'asset': token['symbol'], 'token': asset,
               'recipient': destination, 'amount': s.units(amount, token['decimals']),
               'amountRaw': str(amount), 'decimals': token['decimals']},
               'transaction': {'from': sender, 'to': destination if native else token['address'],
               'data': '0x' if native else '0xa9059cbb'+destination[2:].rjust(64, '0')+hex(amount)[2:].rjust(64, '0'),
               'value': hex(amount) if native else '0x0', 'chainId': '0x8f'},
               'approval': None, 'pin': s.digest(code.lower()) if code else None,
               'created': s.now(), 'expires': s.now()+90}
    ident = s.uid()
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)', (ident, user, sender, 'wallet', 'send', s.dump(payload), payload['expires']))
    return {'id': ident, **payload}


def prepare(row, payload):
    summary = payload['summary']
    if summary['token'] == 'MON':
        return
    results=s.rpc_read_batch([
        ('eth_getCode',[payload['transaction']['to'],'latest']),
        ('eth_call',[{'to':payload['transaction']['to'],'data':'0x70a08231'+row['wallet'][2:].rjust(64,'0')},'latest']),
        ('eth_call',[{k:v for k,v in payload['transaction'].items() if k!='chainId'},'latest'])])
    if any(item.get('error') for item in results):
        raise s.Problem('Token transfer checks failed. Refresh and try again.',409)
    code = results[0].get('result')
    if not code or s.digest(code.lower()) != payload['pin']:
        raise s.Problem('Token contract changed. Refresh your wallet.', 409)
    balance = int(results[1]['result'],16)
    if balance < int(summary['amountRaw']):
        raise s.Problem('Not enough '+summary['asset'], 409, 'insufficient_balance')
    simulated = results[2].get('result')
    if simulated not in {'0x', '0x'+'0'*63+'1'}:
        raise s.Problem('Token transfer was rejected', 409)


def outcome(payload, receipt):
    summary, tx = payload['summary'], payload['transaction']
    if int(receipt['status'], 16) != 1:
        return {'businessState': 'reverted'}
    if summary['token'] != 'MON':
        topic = '0x'+keccak(text='Transfer(address,address,uint256)').hex()
        matches = [log for log in receipt.get('logs', []) if not log.get('removed')
                   and str(log.get('address', '')).lower() == tx['to'].lower()
                   and len(log.get('topics', [])) == 3 and log['topics'][0].lower() == topic
                   and log['topics'][1].lower() == '0x'+tx['from'][2:].rjust(64, '0')
                   and log['topics'][2].lower() == '0x'+summary['recipient'][2:].rjust(64, '0')
                   and log.get('data', '').lower() == '0x'+hex(int(summary['amountRaw']))[2:].rjust(64, '0')]
        if len(matches) != 1:
            return {'businessState': 'transfer_unverified'}
    return {'businessState': 'sent', 'recipient': summary['recipient'], 'amount': summary['amount'], 'asset': summary['asset']}
