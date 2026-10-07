"""Pool-derived prices for both token sides and concentrated-liquidity pools."""
import math,time,threading
from decimal import Decimal,localcontext
import service as s

LOCK=threading.Lock();POOL_LOCK=threading.Lock();DISCOVERED_AT=0;DISCOVERY_CURSOR=0;V3_CURSOR=0;V3_POOLS={};OBSERVED={}

def dex_prices(pairs,addresses):
    addresses=set(addresses);output={}
    for p in pairs:
        if p.get('chainId')!='monad':continue
        try:
            base=str(p.get('baseToken',{}).get('address','')).lower();quote=str(p.get('quoteToken',{}).get('address','')).lower()
            usd=Decimal(str(p.get('priceUsd') or 0));native=Decimal(str(p.get('priceNative') or 0));liquidity=float((p.get('liquidity') or {}).get('usd') or 0)
            if not usd.is_finite() or usd<=0 or not math.isfinite(liquidity) or liquidity<=0:continue
            sides=[(base,usd,'DexScreener base token')]
            if native.is_finite() and native>0:
                with localcontext() as context:context.prec=96;sides.append((quote,usd/native,'DexScreener quote token ratio'))
            for a,price,method in sides:
                price=float(price)
                if a not in addresses or not math.isfinite(price) or price<=0 or output.get(a,{}).get('liquidity',0)>=liquidity:continue
                output[a]={'price':price,'liquidity':liquidity,'change':p.get('priceChange',{}).get('h24') if a==base else None,'volume':p.get('volume',{}).get('h24'),'pair':p.get('pairAddress'),'venue':p.get('dexId'),'source':p.get('url'),'priceSource':method,'fetchedAt':s.now()}
        except (ValueError,TypeError,ArithmeticError):continue
    return output

def target_tokens():
    tokens={t['id']:t for t in s.GATEWAY.tokens if t['id']!='MON'}
    for t in s.GATEWAY.markets()['tokens']:
        if t.get('nadfun') and t.get('phase')=='dex':tokens[t['id']]=t
    return list(tokens.values())

def discover(tokens,block):
    import market_universe as u,route_quotes as q,extra_routes as e,v3_paths
    items=[];calls=[]
    for t in tokens:
        a=t['address'].lower()
        for b in v3_paths.ANCHORS:
            if a==b:continue
            for venue,factory,fees in [('Uniswap v3',q.FACTORY,(100,500,3000,10000)),*[(name,config[1],config[3]) for name,config in e.V3_DEPLOYMENTS.items()]]:
                for fee in fees:items.append((venue,a,b,fee));calls.append(e.request(factory,'getPool(address,address,uint24)',['address','address','uint24'],[a,b,fee]))
    pools={}
    for i in range(0,len(calls),64):
        for (venue,a,b,fee),(ok,raw) in zip(items[i:i+64],e.batch(calls[i:i+64],block)):
            if ok:
                pool=e.decoded(['address'],raw)[0]
                if pool!=s.ZERO:pools[pool]={'address':pool,'venue':venue,'a':a,'b':b,'fee':fee}
    with u.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS price_pools(address TEXT PRIMARY KEY,info TEXT)')
        for pool,info in pools.items():c.execute('INSERT INTO price_pools VALUES(?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info',(pool,s.dump(info)))
    with POOL_LOCK:V3_POOLS.update(pools)

def discovery_background():
    """Discovery has its own cadence; warm prices never wait for it."""
    global DISCOVERY_CURSOR,DISCOVERED_AT
    time.sleep(10)
    while True:
        try:
            tokens=target_tokens()
            if DISCOVERY_CURSOR>=len(tokens) and time.monotonic()-DISCOVERED_AT>900:DISCOVERY_CURSOR=0
            if DISCOVERY_CURSOR<len(tokens):
                discover(tokens[DISCOVERY_CURSOR:DISCOVERY_CURSOR+2],s.rpc('eth_blockNumber',[]));DISCOVERY_CURSOR+=2
                if DISCOVERY_CURSOR>=len(tokens):DISCOVERED_AT=time.monotonic()
        except Exception:pass
        time.sleep(30)

def refresh():
    """Priority refresh never waits for the 34K-token cold scan to reach a token."""
    global V3_CURSOR
    if not LOCK.acquire(False):return
    try:
        import market_universe as u,extra_routes as e,v3_paths
        from eth_abi import decode
        started=time.monotonic();tokens=target_tokens()
        # Anchors first, then every recently priced asset, ahead of unpriced tokens.
        u.prices(list(v3_paths.ANCHORS))
        with u.db() as c:hot=[r[0] for r in c.execute('SELECT address FROM assets WHERE price IS NOT NULL AND updated>? ORDER BY updated ASC',(s.now()-86400,))]
        addresses=list(dict.fromkeys(u.priority_ids()+hot+[t['address'].lower() for t in tokens]))
        outputs=u.prices([a for a in addresses if a not in v3_paths.ANCHORS])
        block=s.rpc('eth_blockNumber',[])
        with POOL_LOCK:loaded=bool(V3_POOLS)
        if not loaded:
            with u.db() as c:
                c.execute('CREATE TABLE IF NOT EXISTS price_pools(address TEXT PRIMARY KEY,info TEXT)')
                saved=[__import__('json').loads(r[0]) for r in c.execute('SELECT info FROM price_pools')]
            with POOL_LOCK:V3_POOLS.update({v['address']:v for v in saved})
        # A failed reserve/V3 chunk must not discard successful HTTP batches.
        try:u.pool_prices(hot_only=True)
        except Exception:pass
        references={a:s.GATEWAY.prices.get(a,{}) for a in v3_paths.ANCHORS};outputs={}
        with POOL_LOCK:all_pools=list(V3_POOLS.values())
        hot_pairs={v.get('pair') for v in s.GATEWAY.prices.copy().values() if s.now()-v.get('fetchedAt',0)<86400}
        priority=[p for p in all_pools if p['address'] in hot_pairs]
        cold=[p for p in all_pools if p['address'] not in hot_pairs]
        part=cold[V3_CURSOR:V3_CURSOR+24];V3_CURSOR=V3_CURSOR+24 if len(part)==24 else 0
        pools=priority+part
        for i in range(0,len(pools),12):
            part=pools[i:i+12];calls=[]
            for p in part:calls += [e.request(p['address'],'slot0()'),e.request(p['address'],'liquidity()'),e.request(p['address'],'token0()'),e.request(p['a'],'balanceOf(address)',['address'],[p['address']]),e.request(p['b'],'balanceOf(address)',['address'],[p['address']])]
            try:values=e.batch(calls,block)
            except Exception:continue
            for j,p in enumerate(part):
                fields=values[j*5:j*5+5]
                if not all(ok for ok,_ in fields):continue
                try:
                    sqrt=decode(['uint160'],fields[0][1][:32])[0];active=decode(['uint128'],fields[1][1])[0];token0=decode(['address'],fields[2][1])[0]
                    ra=decode(['uint256'],fields[3][1])[0];rb=decode(['uint256'],fields[4][1])[0]
                    if not sqrt or not active or token0 not in (p['a'],p['b']):continue
                    for a,b,balance,own_balance in [(p['a'],p['b'],rb,ra),(p['b'],p['a'],ra,rb)]:
                        ref=references.get(b,{});ta=s.GATEWAY.token_map.get(a);tb=s.GATEWAY.token_map.get(b)
                        if not ta or not tb or not ref.get('price') or s.now()-ref.get('fetchedAt',0)>120:continue
                        with localcontext() as context:
                            context.prec=96;ratio=Decimal(sqrt)**2/Decimal(2**192)
                            if a!=token0:ratio=1/ratio
                            ratio*=Decimal(10)**(ta['decimals']-tb['decimals'])
                            exact_price=ratio*Decimal(str(ref['price']));price=float(exact_price);depth=float(Decimal(balance)/Decimal(10)**tb['decimals']*Decimal(str(ref['price'])))
                            liquidity=float(Decimal(own_balance)/Decimal(10)**ta['decimals']*exact_price+Decimal(str(depth)))
                        if depth<25 or not math.isfinite(price) or price<=0 or not math.isfinite(liquidity):continue
                        old=outputs.get(a,s.GATEWAY.prices.get(a,{}))
                        if str(old.get('pair','')).lower()!=p['address'] and s.now()-old.get('fetchedAt',0)<120 and old.get('liquidity',0)>=liquidity:continue
                        outputs[a]={'price':price,'liquidity':liquidity,'quoteSideDepthUSD':depth,'liquiditySource':'Pool token balances; includes inactive liquidity','poolActiveLiquidityRaw':str(active),'change':None,'volume':None,'pair':p['address'],'venue':p['venue'],'source':'https://monadvision.com/address/'+p['address'],'priceSource':'On-chain V3 pool reference','blockNumber':int(block,16),'fetchedAt':min(s.now(),ref['fetchedAt'])}
                except (ValueError,TypeError,ArithmeticError):continue
            u.publish_prices(outputs)
        OBSERVED.update(at=s.now(),block=int(block,16),tokens=len(tokens),v3Pools=len(all_pools),scannedV3Pools=len(pools),prices=len(outputs),durationSeconds=round(time.monotonic()-started,3))
        with s.LOCK:s.GATEWAY.error=None
        u.source('Priority prices',state='live',lastSuccessAt=s.now(),**OBSERVED)
    finally:LOCK.release()

def background():
    import market_universe as u
    try:u.restore()
    except Exception:pass
    threading.Thread(target=discovery_background,daemon=True,name='v3-discovery').start()
    while True:
        started=time.monotonic()
        try:refresh()
        except Exception:
            with s.LOCK:s.GATEWAY.error='Price refresh delayed; last observations retained'
            try:u.source('Priority prices',state='delayed',lastAttemptAt=s.now())
            except Exception:pass
        time.sleep(max(1,15-(time.monotonic()-started)))
