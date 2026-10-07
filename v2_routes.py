"""Pinned V2 exact-input paths with recipient net-minimum guards and two-hop search."""
import re,threading,time
from eth_abi import encode,decode
from eth_utils import keccak
import service as s
import route_quotes as q
import extra_routes as e

DEPLOYMENTS={
 'Uniswap v2':('0x182a927119d56008d921126764bf884221b10f59','0x4b2ab38dbf28d31d467aa8993f6c2585981d6804','ETH','574177a77ebde539a1477966d57912fcf374a451b9b38cdb540208ab0f09c0e6','98738b3cffd2d3d2a4584373a8cad851ddfc47989955f9f6c12aeb1a85bb092f'),
 'PancakeSwap v2':('0x02a84c1b3bbd7401a5f7fa98a384ebc70bb5749e','0xb1bc24c34e88f7d43d5923034e3a14b24daacff9','ETH','c27d0157b56339bb2f0e8f1b8de64e737472ee5c6e77d4680152dc4709f9a65b','682fb2f9ad6ace09360c989ff16da648d0db9cec2abbfd788e9083ee7d3890aa'),
 'LFJ v1':('0xe32d45c2b1c17a0fe0de76f1ebfa7c44b7810034','0x4face5b0ef2757ceb9151d14c036a1135931c70e','','522f6cc5b43849fb444106fb4c5a0740e755db715d9cba10213073689138f1af','81f127b3655d6b86708fc01b6ba07ebf741342a8e6741471fc14964afba78ff4'),
 'Purps v2':('0xafe4d3eb898591ace6285176b26f0f5beb894447','0x22adf91b491abc7a50895cd5c5c194eccc93f5e2','ETH','70417b587e8c8d7b9ce04d81c2ad06b35ebac0e43229a315fb1e3330b0de2d67','ff23c6f451406fe0f3eac7cc49a1545c40838b5dc5c4857fd3ca6c96ff6ff974'),
 'OctoSwap v1':('0xce104732685b9d7b2f07a09d828f6b19786cda32','0x60fd5aa15debd5ffdefb5129fd9fd8a34d80d608','ETH','fd4f785fa0a4ea0b31087856dead189cb3ac5bde47af91aa3abfff52dee18188','bdb568118a68c6fa5d70a857aa40330182937d1dbed9c47d8040291e4c509db1'),
}
PROVIDERS=set(DEPLOYMENTS)
PUBLIC_VERSIONS={};PUBLIC_VERSION_LOCK=threading.Lock()

def version(provider,block='latest'):
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    factory,router,native,fh,rh=DEPLOYMENTS[provider]
    if s.digest(s.rpc('eth_getCode',[factory,block]).lower())!=fh or s.digest(s.rpc('eth_getCode',[router,block]).lower())!=rh:raise s.Problem('V2 router changed',503,'router_changed')
    values=e.batch([e.request(router,'factory()')]+([e.request(router,'WETH()' if native=='ETH' else 'WAVAX()')] if native else []),block)
    if not all(ok for ok,_ in values) or [e.decoded(['address'],v)[0].lower() for _,v in values]!=([factory,q.WMON] if native else [factory]):raise s.Problem('V2 deployment identity changed',503,'router_changed')
    return {'router':router,'entrypointCodeHash':rh,'factoryCodeHash':fh}

def reference(provider,a,b,amount):
    factory,router,native,fh,rh=DEPLOYMENTS[provider];ai,bi=e.assets(a,b)
    if not native and (a['id']=='MON' or b['id']=='MON'):raise s.Problem('This V1 path requires wrapped MON',422,'native_unsupported')
    block=s.rpc('eth_blockNumber',[])
    with PUBLIC_VERSION_LOCK:
        if time.monotonic()-PUBLIC_VERSIONS.get(provider,0)>=20:version(provider,block);PUBLIC_VERSIONS[provider]=time.monotonic()
    from v3_paths import ANCHORS
    paths=[[ai,bi]]+[[ai,bridge,bi] for bridge in ANCHORS if bridge not in [ai,bi]]
    results=e.batch([e.request(router,'getAmountsOut(uint256,address[])',['uint256','address[]'],[amount,path]) for path in paths],block)
    quotes=[]
    for path,(ok,payload) in zip(paths,results):
        if not ok:continue
        amounts=e.decoded(['uint256[]'],payload)[0]
        if len(amounts)!=len(path) or amounts[0]!=amount or not all(0<=x<2**256 for x in amounts):raise s.Problem('V2 quote identity changed',502,'quote_identity')
        # A thin bridge can round the last hop down to zero. Discard that
        # candidate without hiding the other valid paths from this router.
        if any(x==0 for x in amounts):continue
        quotes.append((amounts[-1],path))
    if not quotes:raise s.Problem('No V2 path for this amount',422,'no_route')
    out,path=max(quotes,key=lambda x:x[0])
    return q.result(provider,out,b,{'path':path,'block':int(block,16),'routeType':'v2_exact_input','nativeWrap':a['id']=='MON' or b['id']=='MON'})

def transaction(provider,a,b,amount,minimum,wallet,deadline,details):
    _,router,native,_,_=DEPLOYMENTS[provider];ai,bi=e.assets(a,b);path=details['path']
    if not native and (a['id']=='MON' or b['id']=='MON'):raise s.Problem('This V1 path requires wrapped MON',422,'native_unsupported')
    from v3_paths import ANCHORS
    allowed={ai,bi,*ANCHORS}
    if not isinstance(path,list) or not 2<=len(path)<=3 or path[0]!=ai or path[-1]!=bi or len(set(path))!=len(path) or any(p not in allowed for p in path):raise s.Problem('V2 path changed',409,'route_identity')
    if a['id']=='MON':data=e.call('swapExact'+native+'ForTokensSupportingFeeOnTransferTokens(uint256,address[],address,uint256)',['uint256','address[]','address','uint256'],[minimum,path,wallet,deadline])
    else:
        method='swapExactTokensFor'+native if b['id']=='MON' else 'swapExactTokensForTokens'
        data=e.call(method+'SupportingFeeOnTransferTokens(uint256,uint256,address[],address,uint256)',['uint256','uint256','address[]','address','uint256'],[amount,minimum,path,wallet,deadline])
    return {'from':wallet,'to':router,'value':hex(amount if a['id']=='MON' else 0),'data':data}

def quote(who,data):
    user=s.require(who,human=True);account=s.one('SELECT wallet FROM accounts WHERE id=?',(user,));wallet=account['wallet'] if account else None
    if not wallet:raise s.Problem('Connect and verify your wallet first',409,'wallet_required')
    provider=data.get('provider')
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    if data.get('comparisonQuote'):
        selected=q.select(who,{**data,'quote':data['comparisonQuote']})
        if selected['fallback'] or selected['selected']['provider']!=provider:raise s.Problem('Choose an available route',409,'route_unavailable')
    a,b,amount=q.inputs(data)
    try:slippage=int(data.get('slippage',50))
    except (TypeError,ValueError):raise s.Problem('Invalid slippage')
    if not 1<=slippage<=100:raise s.Problem('Slippage must be between 0.01% and 1%')
    ref=reference(provider,a,b,amount);out=int(ref['outputRaw']);minimum=out*(10000-slippage)//10000
    if minimum<1:raise s.Problem('Amount too small',422,'no_route')
    deadline=s.now()+120;ident=s.uid();expiry=s.now()+30;tx=transaction(provider,a,b,amount,minimum,wallet,deadline,ref['details'])
    f,r,n,fh,rh=DEPLOYMENTS[provider]
    value={'id':ident,'wallet':wallet,'input':a['id'],'output':b['id'],'amount':s.units(amount,a['decimals']),'amountRaw':str(amount),'receive':s.units(out,b['decimals']),'outputRaw':str(out),'minimum':s.units(minimum,b['decimals']),'minimumRaw':str(minimum),'provider':provider,'chainId':143,'slippageBps':slippage,'expires':expiry,'deadline':deadline,'approval':None if a['id']=='MON' else {'token':a['address'],'spender':r,'amount':str(amount)},'transaction':tx,'details':ref['details'],'fees':{'totalBps':0},'router':r,'entrypointCodeHash':rh,'factoryCodeHash':fh}
    s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(ident,user,wallet,a['id'],b['id'],str(amount),s.dump(value),expiry))
    return value

def validate(value):
    try:
        verified=version(value['provider'])
        if any(value.get(k)!=v for k,v in verified.items()):raise ValueError()
        a,b,amount=q.inputs({'input':value['input'],'output':value['output'],'amount':value['amount']})
        out=int(value['outputRaw']);minimum=int(value['minimumRaw']);slippage=value['slippageBps'];wallet=value['wallet']
        if not isinstance(slippage,int) or isinstance(slippage,bool) or not 1<=slippage<=100 or not 0<minimum<=out<2**256 or minimum!=out*(10000-slippage)//10000:raise ValueError()
        if not re.fullmatch('0x[0-9a-f]{40}',wallet) or wallet==s.ZERO or value['chainId']!=143 or value['fees']!={'totalBps':0} or amount!=int(value['amountRaw']) or value['receive']!=s.units(out,b['decimals']) or value['minimum']!=s.units(minimum,b['decimals']):raise ValueError()
        if not isinstance(value['expires'],int) or not isinstance(value['deadline'],int) or not s.now()<value['expires']<=s.now()+30 or not value['expires']<=value['deadline']<=s.now()+120:raise s.Problem('Swap quote expired',409,'quotes_expired')
        expected=transaction(value['provider'],a,b,amount,minimum,wallet,value['deadline'],value['details'])
        approval=None if a['id']=='MON' else {'token':a['address'],'spender':verified['router'],'amount':str(amount)}
        if value['transaction']!=expected or value['approval']!=approval:raise ValueError()
    except s.Problem:raise
    except Exception:raise s.Problem('Stored V2 swap identity changed',409,'route_identity')

REFERENCE_PROVIDERS=tuple((name,lambda a,b,amount,n=name:reference(n,a,b,amount)) for name in DEPLOYMENTS)
