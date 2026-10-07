"""Direct Monad PancakeSwap v3 / LFJ v2.2 routes, unsigned and owner-bound.

Only reviewed exact-input methods are generated. No signatures, broadcasts,
Permit2, arbitrary router calls, fee-on-transfer methods, or custom LB hooks.
"""
import re,threading,time
from eth_abi import encode,decode
from eth_utils import keccak
import service as s
import route_quotes as q

PANCAKE='PancakeSwap v3'
OCTO='OctoSwap v2'
LFJ='LFJ v2.2'
PROVIDERS={PANCAKE,OCTO,LFJ}
PC_ROUTER='0x1b81d678ffb9c0263b24a97847620c99d213eb14'
PC_FACTORY='0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865'
PC_QUOTER='0xb048bbc1ee6b733fffcfb9e9cef7375518e25997'
LB_ROUTER='0x18556da13313f3532c54711497a8fedac273220e'
LB_FACTORY='0xb43120c4745967fa9b93e79c149e66b0f2d6fe0c'
LB_IMPLEMENTATION='0x7a5b4e301fc2b148cefe57257a236eb845082797'
OCTO_ROUTER='0xbfd2cf709a17c4eee8daaf3b96e134408881259e'
OCTO_FACTORY='0x30db57a29acf3641dfc3885af2e5f1f5a408d9cb'
OCTO_QUOTER='0xf27ba2b4ee5580cb2a14fdf98cb981ff0ae149f4'
V3_DEPLOYMENTS={PANCAKE:(PC_ROUTER,PC_FACTORY,PC_QUOTER,(100,500,2500,10000)),OCTO:(OCTO_ROUTER,OCTO_FACTORY,OCTO_QUOTER,(100,500,3000,10000))}
CODE_HASHES={
    OCTO_ROUTER:'c13a2ff30f8b7a6ea2ef28f1f22fc6eb9bbccf7ff7203e000c706c546d2b6a2e',
    OCTO_FACTORY:'881cc0d2cbf29dedb5b893721d602e0bff22eccf4302f7b026d08cee802b375b',
    OCTO_QUOTER:'c68e876ca236cd792f580d03c3f1bfceb52f682bc57163937e58bb336a7d3b88',
    PC_ROUTER:'801ee488b7d50d4af84e9923c9d1a514523852c44b3ec492eabe160f1bcf7659',
    PC_FACTORY:'0d5c3d2be8f54b0df7b47b7792bfa483038b282951df7e0f060b04ae9c5253f8',
    PC_QUOTER:'0c3380e288affc11586bc655c2b38446aae238f9fb7d11fa56b05bb5d2f1c297',
    LB_ROUTER:'d71a850887c8504712ccc5bdc346c2e1640d3bb475aba38a1dc67e7cca63cb4c',
    LB_FACTORY:'32ea56330470f2d1f9a1d9968da4a6bc5121808238e8158012f7f2d45a529dd4',
    LB_IMPLEMENTATION:'6de7679811491bf1520cebd26018e3d7d04d0483f80737483ca44acd47ef6cdd',
}
LB_PATH='(uint256[],uint8[],address[])'
LB_INFO='(uint16,address,bool,bool)'
LB_CLONE_PREFIX='363d3d373d3d3d3d61002c806035363936013d73'+LB_IMPLEMENTATION[2:]+'5af43d3d93803e603357fd5bf3'
PUBLIC_VERSIONS={};PUBLIC_VERSION_LOCK=threading.Lock()

def call(signature,types=(),values=()):
    return '0x'+keccak(text=signature).hex()[:8]+encode(list(types),list(values)).hex()

def decoded(types,payload):
    try:
        value=decode(list(types),payload)
        if encode(list(types),value)!=payload:raise ValueError()
        return value
    except Exception:raise s.Problem('Venue response did not match the reviewed interface',502,'route_identity')

def read(address,signature,types=(),values=(),outputs=('address',),block='latest'):
    raw=s.rpc('eth_call',[{'to':address,'data':call(signature,types,values),'gas':hex(6000000)},block])
    if not isinstance(raw,str) or not re.fullmatch(r'0x[0-9a-fA-F]{0,32000}',raw):raise s.Problem('Invalid venue response',502,'route_identity')
    return decoded(outputs,bytes.fromhex(raw[2:]))

def batch(calls,block):
    if not 1<=len(calls)<=64:raise s.Problem('Route discovery limit exceeded',422,'route_limit')
    raw=s.rpc('eth_call',[{'to':s.MULTICALL,'data':call('aggregate3((address,bool,bytes)[])',['(address,bool,bytes)[]'],[calls]),'gas':hex(8000000)},block])
    if not isinstance(raw,str) or not re.fullmatch(r'0x[0-9a-fA-F]{0,96000}',raw):raise s.Problem('Invalid batch response',502,'route_identity')
    values=decoded(['(bool,bytes)[]'],bytes.fromhex(raw[2:]))[0]
    if len(values)!=len(calls):raise s.Problem('Pool response changed',502,'route_identity')
    return values

def request(address,signature,types=(),values=()):
    return (address,True,bytes.fromhex(call(signature,types,values)[2:]))

def version_metadata(provider):
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    router,factory,third=V3_DEPLOYMENTS[provider][:3] if provider in V3_DEPLOYMENTS else (LB_ROUTER,LB_FACTORY,LB_IMPLEMENTATION)
    return {'router':router,'entrypointCodeHash':CODE_HASHES[router],'factoryCodeHash':CODE_HASHES[factory],
            'quoteContractCodeHash':CODE_HASHES[third]}

def version(provider,block='latest'):
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    contracts=V3_DEPLOYMENTS[provider][:3] if provider in V3_DEPLOYMENTS else (LB_ROUTER,LB_FACTORY,LB_IMPLEMENTATION)
    for address in contracts:
        code=s.rpc('eth_getCode',[address,block])
        if not isinstance(code,str) or s.digest(code.lower())!=CODE_HASHES[address]:raise s.Problem('Venue contract changed. Integration review required.',503,'router_changed')
    router,factory=contracts[:2]
    signatures=('factory()','WETH9()') if provider in V3_DEPLOYMENTS else ('getFactory()','getWNATIVE()')
    calls=[request(router,signature) for signature in signatures]
    expected=[factory,q.WMON]
    if provider==LFJ:calls.append(request(factory,'getLBPairImplementation()'));expected.append(LB_IMPLEMENTATION)
    for (ok,payload),address in zip(batch(calls,block),expected):
        if not ok or decoded(['address'],payload)[0].lower()!=address:raise s.Problem('Venue factory or wrapped token changed',503,'router_changed')
    return version_metadata(provider)

def reference_version(provider,block):
    # Public comparison only. Wallet prepare always calls uncached version().
    with PUBLIC_VERSION_LOCK:
        observed=PUBLIC_VERSIONS.get(provider,0)
        if time.monotonic()-observed<20:return version_metadata(provider)
        result=version(provider,block);PUBLIC_VERSIONS[provider]=time.monotonic();return result

def assets(a,b):
    ai=q.WMON if a['id']=='MON' else a['address'].lower();bi=q.WMON if b['id']=='MON' else b['address'].lower()
    if ai==bi:raise s.Problem('Wrapped native pair is not a swap',422,'no_route')
    return ai,bi

def pancake(a,b,amount):
    return v3(PANCAKE,a,b,amount)

def v3(provider,a,b,amount):
    import v3_paths
    if provider not in V3_DEPLOYMENTS:raise s.Problem('Unknown V3 provider')
    _,factory,quoter,fees=V3_DEPLOYMENTS[provider]
    block=s.rpc('eth_blockNumber',[]);reference_version(provider,block)
    return v3_paths.reference(provider,factory,quoter,fees,a,b,amount,block)

def clone_code(token_x,token_y,step):
    return '0x'+LB_CLONE_PREFIX+token_x[2:]+token_y[2:]+format(step,'04x')+'002c'

def lb_identity_requests(pair,ai,bi,step):
    return [request(pair,'getTokenX()'),request(pair,'getTokenY()'),request(pair,'getBinStep()'),request(pair,'getLBHooksParameters()'),request(pair,'getFactory()'),request(pair,'implementation()'),request(LB_FACTORY,'getLBPairInformation(address,address,uint256)',('address','address','uint256'),(ai,bi,step))]

def lb_pair_identity(pair,ai,bi,step,block='latest',values=None):
    if values is None:values=batch(lb_identity_requests(pair,ai,bi,step),block)
    if any(not ok for ok,_ in values):raise s.Problem('Unreviewed LFJ pair interface',503,'route_identity')
    x=decoded(['address'],values[0][1])[0];y=decoded(['address'],values[1][1])[0]
    real_step=decoded(['uint16'],values[2][1])[0];hooks=decoded(['bytes32'],values[3][1])[0]
    factory=decoded(['address'],values[4][1])[0];implementation=decoded(['address'],values[5][1])[0]
    info=decoded([LB_INFO],values[6][1])[0]
    if {x,y}!={ai,bi} or real_step!=step or factory!=LB_FACTORY or implementation!=LB_IMPLEMENTATION or info[0]!=step or info[1]!=pair or info[3]:raise s.Problem('LFJ pool identity changed',503,'route_identity')
    if hooks!=b'\0'*32:raise s.Problem('LFJ pools with custom hooks require review',422,'unsupported_hooks')
    code=s.rpc('eth_getCode',[pair,block])
    if str(code).lower()!=clone_code(x,y,step):raise s.Problem('LFJ clone implementation changed',503,'router_changed')
    return {'pool':pair,'binStep':step,'poolCodeHash':s.digest(code.lower()),'tokenX':x,'tokenY':y,'hooks':'0x'+'0'*64}

def lfj_segment(ai,bi,amount,block,infos=None):
    if infos is None:infos=read(LB_FACTORY,'getAllLBPairs(address,address)',('address','address'),(ai,bi),(LB_INFO+'[]',),block)[0]
    if len(infos)>16:raise s.Problem('LFJ pool discovery limit exceeded',422,'route_limit')
    candidates=[];hooked=False
    supported=[(step,pair) for step,pair,_,ignored in infos if not ignored and pair!=s.ZERO and 0<step<=65535]
    if len(supported)>9:raise s.Problem('LFJ pool discovery limit exceeded',422,'route_limit')
    responses=batch([item for step,pair in supported for item in lb_identity_requests(pair,ai,bi,step)],block) if supported else []
    for i,(step,pair) in enumerate(supported):
        try:identity=lb_pair_identity(pair,ai,bi,step,block,responses[i*7:(i+1)*7])
        except s.Problem as e:
            if e.code=='unsupported_hooks':hooked=True;continue
            raise
        candidates.append(identity)
    quotes=[]
    if candidates:
        values=batch([request(LB_ROUTER,'getSwapOut(address,uint128,bool)',('address','uint128','bool'),(d['pool'],amount,d['tokenY']==bi)) for d in candidates],block)
        for detail,(ok,payload) in zip(candidates,values):
            if ok:
                left,out,fee=decoded(['uint128','uint128','uint128'],payload)
                # A quote that cannot consume the whole amount is not executable.
                if left==0 and out>0:quotes.append((out,fee,detail))
    if not quotes:raise s.Problem('No reviewed LFJ v2.2 pool for this amount',422,'unsupported_hooks' if hooked and not candidates else 'no_route')
    out,fee,detail=max(quotes,key=lambda value:value[0])
    return out,fee,detail

def lfj(a,b,amount):
    import v3_paths
    ai,bi=assets(a,b)
    if not 0<amount<2**128:raise s.Problem('LFJ amount exceeds its uint128 quote limit',422,'amount_limit')
    block=s.rpc('eth_blockNumber',[]);reference_version(LFJ,block);quotes=[]
    paths=[[ai,bi]]+[[ai,x,bi] for x in v3_paths.ANCHORS if x not in (ai,bi)]
    edges=list(dict.fromkeys((x,y) for path in paths for x,y in zip(path,path[1:])))
    responses=batch([request(LB_FACTORY,'getAllLBPairs(address,address)',('address','address'),edge) for edge in edges],block)
    topology={edge:decoded([LB_INFO+'[]'],raw)[0] if ok else () for edge,(ok,raw) in zip(edges,responses)}
    for path in paths:
        current=amount;segments=[];fees=[]
        if any(not topology[(x,y)] for x,y in zip(path,path[1:])):continue
        try:
            for x,y in zip(path,path[1:]):
                if not 0<current<2**128:raise s.Problem('Intermediate LFJ amount exceeds its limit',422,'amount_limit')
                current,fee,identity=lfj_segment(x,y,current,block,topology[(x,y)]);segments.append(identity);fees.append(str(fee))
            quotes.append((current,path,segments,fees))
        except s.Problem as exc:
            if exc.code not in {'no_route','unsupported_hooks','amount_limit'}:raise
    if not quotes:raise s.Problem('No reviewed LFJ path for this amount',422,'no_route')
    out,path,segments,fees=max(quotes,key=lambda x:x[0])
    return q.result(LFJ,out,b,{**segments[-1],'path':path,'segments':segments,'feeRaw':fees[-1],'hopFeesRaw':fees,'block':int(block,16),'version':3,'nativeWrap':a['id']=='MON' or b['id']=='MON','routeType':'direct_lb22' if len(path)==2 else 'two_hop_lb22'})

REFERENCE_PROVIDERS=((PANCAKE,pancake),(OCTO,lambda a,b,amount:v3(OCTO,a,b,amount)),(LFJ,lfj))

def transaction(provider,a,b,amount,minimum,wallet,deadline,details):
    ai,bi=assets(a,b)
    if provider in V3_DEPLOYMENTS:
        import v3_paths
        router,_,_,fees=V3_DEPLOYMENTS[provider]
        path,tiers=v3_paths.path_details(a,b,details,fees)
        recipient=router if b['id']=='MON' else wallet
        if len(path)==2:swap=call('exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))',('(address,address,uint24,address,uint256,uint256,uint256,uint160)',),((ai,bi,tiers[0],recipient,deadline,amount,minimum,0),))
        else:swap=call('exactInput((bytes,address,uint256,uint256,uint256))',('(bytes,address,uint256,uint256,uint256)',),((v3_paths.packed(path,tiers),recipient,deadline,amount,minimum),))
        calls=[bytes.fromhex(swap[2:])]
        if b['id']=='MON':calls.append(bytes.fromhex(call('unwrapWETH9(uint256,address)',('uint256','address'),(minimum,wallet))[2:]))
        if a['id']=='MON':calls.append(bytes.fromhex(call('refundETH()')[2:]))
        data=call('multicall(bytes[])',('bytes[]',),(calls,))
    elif provider==LFJ:
        import v3_paths
        tokens=details.get('path',[ai,bi]);segments=details.get('segments',[details]);steps=[int(x['binStep']) for x in segments]
        if not isinstance(tokens,list) or not 2<=len(tokens)<=3 or tokens[0]!=ai or tokens[-1]!=bi or len(set(tokens))!=len(tokens) or any(x not in v3_paths.ANCHORS for x in tokens[1:-1]) or len(steps)!=len(tokens)-1 or any(not 0<x<=65535 for x in steps) or details.get('version')!=3:raise s.Problem('Unreviewed LFJ path',409,'route_identity')
        path=(steps,[3]*len(steps),tokens);router=LB_ROUTER
        if a['id']=='MON':data=call('swapExactNATIVEForTokens(uint256,'+LB_PATH+',address,uint256)',('uint256',LB_PATH,'address','uint256'),(minimum,path,wallet,deadline))
        else:
            method='swapExactTokensForNATIVE' if b['id']=='MON' else 'swapExactTokensForTokens'
            data=call(method+'(uint256,uint256,'+LB_PATH+',address,uint256)',('uint256','uint256',LB_PATH,'address','uint256'),(amount,minimum,path,wallet,deadline))
    else:raise s.Problem('Unknown swap provider')
    return {'from':wallet,'to':router,'value':hex(amount if a['id']=='MON' else 0),'data':data}

def quote(who,data):
    user=s.require(who,human=True);row=s.one('SELECT wallet FROM accounts WHERE id=?',(user,));wallet=row['wallet'] if row else None
    if not wallet:raise s.Problem('Connect and verify your wallet first',409,'wallet_required')
    provider=data.get('provider')
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    if data.get('comparisonQuote'):
        selection=q.select(who,{**data,'quote':data['comparisonQuote']})
        if selection['fallback'] or selection['selected']['provider']!=provider:raise s.Problem('Choose an available route before swapping',409,'route_unavailable')
    a,b,amount=q.inputs(data)
    try:slippage=int(data.get('slippage',50))
    except (ValueError,TypeError):raise s.Problem('Invalid slippage')
    if not 1<=slippage<=100:raise s.Problem('Slippage must be between 0.01% and 1%')
    reference=v3(provider,a,b,amount) if provider in V3_DEPLOYMENTS else lfj(a,b,amount)
    out=int(reference['outputRaw']);minimum=out*(10000-slippage)//10000
    if minimum<1:raise s.Problem('Amount too small',422,'no_route')
    # The reference verified all pinned contracts and identities at its block;
    # prepare checks the current contracts again before wallet review.
    deadline=s.now()+120;details=reference['details'];verified=version_metadata(provider)
    tx=transaction(provider,a,b,amount,minimum,wallet,deadline,details);ident=s.uid();expires=s.now()+30
    result={'id':ident,'wallet':wallet,'input':a['id'],'output':b['id'],'amount':s.units(amount,a['decimals']),'amountRaw':str(amount),
            'receive':s.units(out,b['decimals']),'outputRaw':str(out),'minimum':s.units(minimum,b['decimals']),'minimumRaw':str(minimum),
            'provider':provider,'chainId':143,'slippageBps':slippage,'expires':expires,'deadline':deadline,
            'approval':None if a['id']=='MON' else {'token':a['address'],'spender':tx['to'],'amount':str(amount)},
            'transaction':tx,'details':details,'fees':{'totalBps':0},**verified}
    s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(ident,user,wallet,a['id'],b['id'],str(amount),s.dump(result),expires))
    return result

def validate(quote):
    try:
        provider=quote['provider'];verified=version(provider)
        if any(quote.get(key)!=value for key,value in verified.items()):raise s.Problem('Router changed. Get a fresh quote.',409,'router_changed')
        a,b,amount=q.inputs({'input':quote['input'],'output':quote['output'],'amount':quote['amount']});ai,bi=assets(a,b)
        wallet=quote['wallet'];out=int(quote['outputRaw']);minimum=int(quote['minimumRaw']);slippage=quote['slippageBps']
        if not re.fullmatch(r'0x[0-9a-f]{40}',wallet) or wallet==s.ZERO or not isinstance(slippage,int) or not 1<=slippage<=100:raise s.Problem('Stored swap identity changed',409,'route_identity')
        if amount!=int(quote['amountRaw']) or quote['chainId']!=143 or quote['receive']!=s.units(out,b['decimals']) or quote['minimum']!=s.units(minimum,b['decimals']) or not 0<minimum<=out<2**256 or minimum!=out*(10000-slippage)//10000 or quote['fees']!={'totalBps':0}:raise s.Problem('Stored swap economics changed',409,'route_identity')
        if not isinstance(quote['deadline'],int) or not isinstance(quote['expires'],int) or not s.now()<quote['expires']<=s.now()+30 or not quote['expires']<=quote['deadline']<=s.now()+120:raise s.Problem('Swap quote expired. Refresh routes.',409,'quotes_expired')
        details=quote['details']
        if provider==LFJ:
            tokens=details.get('path',[ai,bi]);segments=details.get('segments',[details])
            if len(segments)!=len(tokens)-1 or not amount<2**128:raise s.Problem('Stored LFJ path changed',409,'route_identity')
            for x,y,segment in zip(tokens,tokens[1:],segments):
                identity=lb_pair_identity(segment['pool'],x,y,int(segment['binStep']))
                if any(segment.get(key)!=value for key,value in identity.items()):raise s.Problem('Stored LFJ pool changed',409,'route_identity')
        elif provider in V3_DEPLOYMENTS:
            import v3_paths
            _,factory,_,fees=V3_DEPLOYMENTS[provider]
            v3_paths.validate_pools(factory,a,b,details,fees)
        expected=transaction(provider,a,b,amount,minimum,wallet,quote['deadline'],details)
        if quote['transaction']!=expected:raise s.Problem('Stored swap data changed',409,'route_identity')
        approval=None if a['id']=='MON' else {'token':a['address'],'spender':verified['router'],'amount':str(amount)}
        if quote['approval']!=approval:raise s.Problem('Stored allowance changed',409,'route_identity')
    except s.Problem:raise
    except (KeyError,ValueError,TypeError,OverflowError):raise s.Problem('Stored venue route is invalid',409,'route_identity')

def capabilities():
    return [{'provider':name,'chainId':143,'referenceQuotes':True,'unsignedExecution':True,'router':config[0],'routes':'direct and two-hop v3 pools','feeTiers':list(config[3]),'walletRequiredForExecution':True,'fundedExecutionVerified':False} for name,config in V3_DEPLOYMENTS.items()]+[
            {'provider':LFJ,'chainId':143,'referenceQuotes':True,'unsignedExecution':True,'router':LB_ROUTER,'routes':'direct and two-hop v2.2 pools without custom hooks','walletRequiredForExecution':True,'fundedExecutionVerified':False}]
