"""Bounded V3 path search at one block; public topology cache contains no quotes."""
import itertools,re,threading,time
from eth_abi import decode
import service as s

WMON='0x3bd359c1119da7da1d913d1c4d2b7c461115433a'
AUSD='0x00000000efe302beaa2b3e6e1b18d08d69a9012a'
ANCHORS=(WMON,s.USDC,AUSD,
 '0xe7cd86e13ac4309349f30b3435a9d337750fc82d', # USDT0
 '0xee8c0e9f1bffb4eb878d8f15f368a02a35481242', # WETH
 '0x0555e30da8f98308edb960aa94c0db47230d2b9c', # WBTC
 '0x91b81bfbe3a747230f0529aa28d8b2bc898e6d56', # LVMon
 '0x8498312a6b3cbd158bf0c93abdcf29e6e4f55081') # gMON
LOCK=threading.Lock();TOPOLOGY={}

def path_details(a,b,details,fees):
    ai=WMON if a['id']=='MON' else a['address'].lower();bi=WMON if b['id']=='MON' else b['address'].lower()
    path=details.get('path',[ai,bi]);tiers=details.get('feeTiers',[details.get('feeTier',round(details.get('feeBps',0)*100))])
    if not isinstance(path,list) or not 2<=len(path)<=3 or path[0]!=ai or path[-1]!=bi or len(set(path))!=len(path) or any(not isinstance(x,str) or not re.fullmatch('0x[0-9a-f]{40}',x) for x in path) or any(x not in ANCHORS for x in path[1:-1]):raise s.Problem('V3 path changed',409,'route_identity')
    if not isinstance(tiers,list) or len(tiers)!=len(path)-1 or any(type(f) is not int or f not in fees for f in tiers):raise s.Problem('V3 fee tiers changed',409,'route_identity')
    return path,tiers

def packed(path,fees):
    value=bytes.fromhex(path[0][2:])
    for fee,address in zip(fees,path[1:]):value+=fee.to_bytes(3,'big')+bytes.fromhex(address[2:])
    return value

def topology(factory,ai,bi,fees,block):
    import extra_routes as e
    key=(factory,ai,bi,tuple(fees))
    with LOCK:cached=TOPOLOGY.get(key)
    if cached and time.monotonic()-cached[0]<30:return cached[1]
    paths=[[ai,bi]]+[[ai,x,bi] for x in ANCHORS if x not in (ai,bi)]
    pairs=list(dict.fromkeys((x,y) for p in paths for x,y in zip(p,p[1:])))
    items=[(x,y,f) for x,y in pairs for f in fees]
    calls=[e.request(factory,'getPool(address,address,uint24)',['address','address','uint24'],[x,y,f]) for x,y,f in items]
    values=[]
    for i in range(0,len(calls),64):values.extend(e.batch(calls[i:i+64],block))
    pools={}
    for item,(ok,raw) in zip(items,values):
        if ok:
            pool=e.decoded(['address'],raw)[0]
            if pool!=s.ZERO:pools[item]=pool
    candidates=[]
    for path in paths:
        options=[[f for f in fees if (x,y,f) in pools] for x,y in zip(path,path[1:])]
        for tiers in itertools.product(*options):candidates.append((path,list(tiers),[pools[(x,y,f)] for x,y,f in zip(path,path[1:],tiers)]))
    with LOCK:
        if len(TOPOLOGY)>512:TOPOLOGY.clear()
        TOPOLOGY[key]=(time.monotonic(),candidates)
    return candidates

def reference(provider,factory,quoter,fees,a,b,amount,block=None):
    import extra_routes as e,route_quotes as q
    ai,bi=e.assets(a,b);block=block or s.rpc('eth_blockNumber',[])
    candidates=topology(factory,ai,bi,fees,block)
    if not candidates:raise s.Problem('No V3 path',422,'no_route')
    calls=[e.request(quoter,'quoteExactInput(bytes,uint256)',['bytes','uint256'],[packed(path,tiers),amount]) for path,tiers,_ in candidates]
    values=[]
    for i in range(0,len(calls),8):
        response=s.rpc_call_batch([{'to':address,'data':'0x'+data.hex(),'gas':hex(1500000)} for address,_,data in calls[i:i+8]],block)
        for r in response:
            raw=r.get('result')
            if r.get('error') or not isinstance(raw,str) or not re.fullmatch('0x[0-9a-fA-F]{0,12000}',raw):values.append((False,b''))
            else:values.append((True,bytes.fromhex(raw[2:])))
    quotes=[]
    for (path,tiers,pools),(ok,raw) in zip(candidates,values):
        if not ok:continue
        out,prices,crossed,gas=e.decoded(['uint256','uint160[]','uint32[]','uint256'],raw)
        if len(prices)!=len(tiers) or len(crossed)!=len(tiers):raise s.Problem('V3 quote identity changed',502,'quote_identity')
        if 0<out<2**256:quotes.append((out,path,tiers,pools,gas))
    if not quotes:raise s.Problem('No liquid V3 path for this amount',422,'no_route')
    out,path,tiers,pools,gas=max(quotes,key=lambda x:x[0])
    return q.result(provider,out,b,{'path':path,'feeTiers':tiers,'pools':pools,'pool':pools[-1],'feeTier':tiers[-1],'feeBps':sum(tiers)/100,'block':int(block,16),'gasEstimate':str(gas),'nativeWrap':a['id']=='MON' or b['id']=='MON','routeType':'direct_v3' if len(path)==2 else 'two_hop_v3'})

def validate_pools(factory,a,b,details,fees):
    import extra_routes as e
    path,tiers=path_details(a,b,details,fees)
    results=e.batch([e.request(factory,'getPool(address,address,uint24)',['address','address','uint24'],[x,y,f]) for x,y,f in zip(path,path[1:],tiers)],'latest')
    pools=[e.decoded(['address'],raw)[0] if ok else s.ZERO for ok,raw in results]
    expected=details.get('pools',[details.get('pool')])
    if any(p==s.ZERO for p in pools) or pools!=expected:raise s.Problem('V3 pool identity changed',409,'route_identity')
