"""Match reviewed EVM calls, including finalized smart-account relay calls.

Never submit transactions. A relay envelope is not proof of the user's call:
require a canonical receipt and an exact CALL frame from the reviewed wallet.
"""
import service as s
from eth_utils import keccak

def lower(value):return str(value or '').lower()
def number(value):
    try:return int(value,16) if isinstance(value,str) else int(value)
    except (ValueError,TypeError):raise s.Problem('Invalid wallet transaction',409)

def finalized_receipt(tx):
    r=s.rpc('eth_getTransactionReceipt',[tx])
    if not r:raise s.Problem('Transaction is pending. Check the same hash.',409,'transaction_pending')
    if r.get('transactionHash') and lower(r['transactionHash'])!=lower(tx):raise s.Problem('Receipt does not match transaction',409)
    block=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False])
    final=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not block or not final or lower(block['hash'])!=lower(r['blockHash']) or number(final['number'])<number(r['blockNumber']):
        raise s.Problem('Waiting for finality. Check the same hash.',409,'transaction_pending')
    return r

def approval_receipt(tx,wallet,token,spender,amount,observed=None):
    """One canonical, finalized allowance for the exact reviewed call."""
    wallet,token,spender=map(lower,(wallet,token,spender));amount=int(amount)
    expected={'from':wallet,'to':token,'value':'0x0',
        'data':'0x095ea7b3'+spender[2:].rjust(64,'0')+hex(amount)[2:].rjust(64,'0')}
    verified_call(tx,expected,observed)
    receipt=finalized_receipt(tx)
    if number(receipt['status'])==1:
        topic='0x'+keccak(text='Approval(address,address,uint256)').hex()
        events=[l for l in receipt.get('logs',[]) if not l.get('removed')
            and lower(l.get('address'))==token and len(l.get('topics',[]))==3
            and lower(l['topics'][0])==topic and lower('0x'+l['topics'][1][-40:])==wallet
            and lower('0x'+l['topics'][2][-40:])==spender and number(l.get('data','0x0'))==amount]
        if len(events)!=1:raise s.Problem('The exact token allowance was not verified',409,'approval_unverified')
    return receipt

def exact(frame,expected):
    return (lower(frame.get('from'))==lower(expected['from']) and lower(frame.get('to'))==lower(expected['to'])
      and lower(frame.get('input'))==lower(expected['data']) and number(frame.get('value','0x0'))==number(expected.get('value','0x0')))

def verified_call(tx,expected,observed=None):
    observed=observed or s.rpc('eth_getTransactionByHash',[tx])
    if not observed:raise s.Problem('Transaction is not indexed. Check the same hash.',409,'transaction_pending')
    if observed.get('hash') and lower(observed['hash'])!=lower(tx):raise s.Problem('Transaction hash differs',409)
    if observed.get('chainId') is not None and number(observed['chainId'])!=143:raise s.Problem('Use the Monad transaction',409)
    if exact(observed,expected):return {'kind':'direct'}
    # No substring searches, wrapper guesses or trust in a relayer's address.
    s.verify_rpc_network();receipt=finalized_receipt(tx)
    try:trace=s.rpc('debug_traceTransaction',[tx,{'tracer':'callTracer','timeout':'5s','tracerConfig':{'onlyTopCall':False,'withLog':False}}])
    except Exception:raise s.Problem('Wallet execution verification unavailable. Keep this hash and check again.',503,'wallet_verification_unavailable')
    if not isinstance(trace,dict) or any(lower(trace.get(k))!=lower(observed.get(k)) for k in ['from','to','input']) or number(trace.get('value','0x0'))!=number(observed.get('value','0x0')):
        raise s.Problem('Wallet execution trace differs from transaction',409)
    successful=number(receipt['status'])==1;stack=[(trace,False,0)];matches=0;nodes=0
    while stack:
        frame,reverted,depth=stack.pop();nodes+=1
        if nodes>2048 or depth>64 or not isinstance(frame,dict):raise s.Problem('Wallet execution trace cannot be verified',409)
        reverted=reverted or bool(frame.get('error'))
        if (not successful or not reverted) and lower(frame.get('type'))=='call' and exact(frame,expected):matches+=1
        children=frame.get('calls',[])
        if not isinstance(children,list):raise s.Problem('Wallet execution trace cannot be verified',409)
        stack.extend((child,reverted,depth+1) for child in children)
    if matches!=1:raise s.Problem('Wallet transaction does not match the reviewed call',409)
    return {'kind':'smart_account','block':receipt['blockNumber'],'blockHash':receipt['blockHash'],'successful':successful}
