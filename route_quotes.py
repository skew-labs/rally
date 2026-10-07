"""Wallet-free, bounded reference quotes. Never supplies submission calldata."""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlencode
import service as s

WMON='0x3bd359c1119da7da1d913d1c4d2b7c461115433a'
FACTORY='0x204faca1764b154221e35c0d20abb3c525710498'
QUOTER='0x661e93cca42afacb172121ef892830ca3b70f08d'
NATIVE='0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
CACHE={};LOCK=threading.Lock();SLOTS=threading.BoundedSemaphore(2)


def inputs(data):
    a=s.GATEWAY.token_map.get(str(data.get('input','')));b=s.GATEWAY.token_map.get(str(data.get('output','')))
    if not a or not b or a['id']==b['id']:raise s.Problem('Choose two different assets')
    try:
        with localcontext() as c:
            c.prec=96;v=Decimal(str(data.get('amount','')))
            if not v.is_finite() or not 0<v<=Decimal('1000000000000') or len(str(v))>80:raise ValueError()
            raw=v*10**a['decimals'];amount=int(raw)
            if amount<1 or raw!=amount:raise ValueError()
    except (InvalidOperation,ValueError,OverflowError):raise s.Problem('Enter a valid amount')
    return a,b,amount


def result(name, amount, b, details=None):
    value=int(amount)
    if not 0<value<2**256:raise s.Problem('No route for this amount',422,'no_route')
    return {'provider':name,'outputRaw':str(value),'output':s.units(value,b['decimals']),'state':'quoted','details':details or {},'executable':False}


def kuru(a,b,amount):
    # Public quote caller: no user account, wallet, approval or signing.
    wallet=s.ZERO
    with s.GATEWAY.quote_lock:
        key=s.GATEWAY.keys.get(wallet)
        if not key or key['expires_at']<s.now()+60:
            key=s.http_json('https://ws.kuru.io/api/generate-token',{'user_address':wallet});s.GATEWAY.keys[wallet]=key
        time.sleep(max(0,1.1-(time.monotonic()-s.GATEWAY.last_quote)))
        raw=s.http_json('https://ws.kuru.io/api/quote',{'userAddress':wallet,'tokenIn':a['address'],'tokenOut':b['address'],'amount':str(amount),'slippageTolerance':50,'autoSlippage':False},{'Authorization':'Bearer '+key['token']})
        s.GATEWAY.last_quote=time.monotonic()
    if raw.get('status')!='success':raise s.Problem('No Kuru route',422,'no_route')
    tx=raw.get('transaction',{});calldata=str(tx.get('calldata','')).removeprefix('0x')
    if tx.get('to','').lower()!=s.FLOW or not re.fullmatch(r'ce1e7030[0-9a-fA-F]{512,60000}',calldata):raise s.Problem('Kuru router changed',502,'router_changed')
    from eth_abi import decode,encode
    abi=['(address,uint256,address,uint256)','(address,uint256,address,uint256,bool)','bytes']
    try:
        payload=bytes.fromhex(calldata[8:]);decoded=decode(abi,payload)
        if encode(abi,decoded)!=payload:raise ValueError()
        out_token,minimum,in_token,in_amount=decoded[0]
        if out_token.lower()!=b['address'].lower() or in_token.lower()!=a['address'].lower() or in_amount!=amount or not 0<minimum<=int(raw['output']) or int(tx.get('value','0'))!=(amount if a['id']=='MON' else 0):raise ValueError()
    except Exception:raise s.Problem('Kuru quote identity mismatch',502,'quote_identity')
    return result('Kuru',raw['output'],b)


def kyber(a,b,amount):
    ai=NATIVE if a['id']=='MON' else a['address'];bi=NATIVE if b['id']=='MON' else b['address']
    raw=s.http_json('https://aggregator-api.kyberswap.com/monad/api/v1/routes?'+urlencode({'tokenIn':ai,'tokenOut':bi,'amountIn':str(amount)}),headers={'X-Client-Id':'rally-monad'})
    if raw.get('code') not in (0,None):raise s.Problem('No KyberSwap route for this amount',422,'no_route')
    route=raw.get('data',{}).get('routeSummary',{})
    if raw.get('code')!=0 or route.get('tokenIn','').lower()!=ai.lower() or route.get('tokenOut','').lower()!=bi.lower() or str(route.get('amountIn'))!=str(amount):raise s.Problem('Kyber quote identity mismatch',502,'quote_identity')
    return result('KyberSwap',route['amountOut'],b,{'gasEstimate':route.get('gas'),'router':raw['data'].get('routerAddress')})


def uniswap(a,b,amount):
    import v3_paths
    return v3_paths.reference('Uniswap v3',FACTORY,QUOTER,(100,500,3000,10000),a,b,amount)


def compare(who,data):
    if who and who['grant']:s.require(who,'markets:read')
    a,b,amount=inputs(data);key=(a['id'],b['id'],amount)
    with LOCK:
        cached=CACHE.get(key)
        if cached and cached.get('complete',True) and s.now()-cached['quotedAt']<20:return dict(cached,cached=True)
    if not SLOTS.acquire(timeout=.1):raise s.Problem('Quotes are busy. Try again.',503)
    try:
        def call(name,fn):
            try:return fn(a,b,amount)
            except Exception as e:return {'provider':name,'state':'unavailable','code':e.code if isinstance(e,s.Problem) else 'provider_unavailable','executable':False}
        import extra_routes, v2_routes
        providers=[('Kuru',kuru),('KyberSwap',kyber),('Uniswap v3',uniswap),*extra_routes.REFERENCE_PROVIDERS,*v2_routes.REFERENCE_PROVIDERS]
        with ThreadPoolExecutor(max_workers=3) as pool:
            routes=list(pool.map(lambda pair:call(*pair),providers))
        routes.sort(key=lambda r:int(r.get('outputRaw','0')),reverse=True)
        available=[r for r in routes if r['state']=='quoted']
        value={'id':s.uid(),'input':a['id'],'output':b['id'],'amountRaw':str(amount),'routes':routes,'best':available[0]['provider'] if available else None,'quotedAt':s.now(),'expires':s.now()+20,'comparison':'output_before_network_gas','transaction':None}
        with LOCK:
            if len(CACHE)>200:CACHE.clear()
            CACHE[key]=value
        return value
    finally:SLOTS.release()


def select(who,data):
    if who and who['grant']:s.require(who,'markets:read')
    a,b,amount=inputs(data)
    with LOCK:value=CACHE.get((a['id'],b['id'],amount))
    if not value or value['id']!=data.get('quote') or value['expires']<=s.now():raise s.Problem('Quotes expired. Refresh routes.',409,'quotes_expired')
    provider=data.get('provider')
    requested=next((r for r in value['routes'] if r['provider']==provider),None)
    if not requested:raise s.Problem('Unknown route')
    if requested['state']=='checking':raise s.Problem('This route is still loading',409,'quotes_pending')
    selected=requested if requested['state']=='quoted' else next((r for r in value['routes'] if r['state']=='quoted'),None)
    if not selected:raise s.Problem('No provider has a quote for this pair.',503,'no_route')
    return {'quote':value['id'],'selected':selected,'fallback':selected['provider']!=provider,
        'requested':provider,'expires':value['expires'],'comparison':value['comparison'],'transaction':None}
