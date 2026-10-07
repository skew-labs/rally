"""Owner-wallet swaps. Builds unsigned transactions; never signs or broadcasts."""
import json
import re
from eth_abi import encode,decode
from eth_utils import keccak
import service as s
import route_quotes as q
import extra_routes as extra
import v2_routes as v2

UNI='0xfe31f71c1b106eac32f1a19239c9a9a72ddfb900'
KYBER='0x6131b5fae19ea4f9d964eac0408e4408b66337b5'
EXECUTOR='0x8f10b468b06c6fd214b65f87778827f7d113f996'
CODE_HASHES={UNI:'f641f8882bf3111931f8eb334f3899872e708b1fe9b1320c6d92be08b160b5b6',KYBER:'9beab122fde56d8769e71c7850bdfd39c461e5b3184b111b4ef3118c9990267d'}
DESC='(address,address,address[],uint256[],address[],uint256[],address,uint256,uint256,uint256,bytes)'
SWAP='(address,address,bytes,'+DESC+',bytes)'
PROVIDERS={'Kuru','Kuru Flow','KyberSwap','Uniswap v3',*extra.PROVIDERS,*v2.PROVIDERS}

def call(signature,types,values):return '0x'+keccak(text=signature).hex()[:8]+encode(types,values).hex()

def canonical(data,signature,types):
    try:
        if not re.fullmatch(r'0x[0-9a-fA-F]{8,60000}',data) or data[2:10].lower()!=keccak(text=signature).hex()[:8]:raise ValueError()
        payload=bytes.fromhex(data[10:]);values=decode(types,payload)
        if encode(types,values)!=payload:raise ValueError()
        return values
    except Exception:raise s.Problem('Swap data did not match the reviewed interface',502,'route_identity')

def version(provider):
    if provider in v2.PROVIDERS:return v2.version(provider)
    if provider in extra.PROVIDERS:return extra.version(provider)
    if provider in {'Kuru','Kuru Flow'}:return s.flow_version()
    router=UNI if provider=='Uniswap v3' else KYBER if provider=='KyberSwap' else None
    if not router:raise s.Problem('Unknown swap provider')
    code=s.rpc('eth_getCode',[router,'latest']);code_hash=s.digest(str(code).lower())
    if code_hash!=CODE_HASHES[router]:raise s.Problem('Router changed. Integration review required.',503,'router_changed')
    return {'router':router,'entrypointCodeHash':code_hash}

def uniswap_transaction(a,b,amount,out,minimum,wallet,deadline,details):
    import v3_paths
    if isinstance(details,int):details={'feeTier':details}
    path,tiers=v3_paths.path_details(a,b,details,(100,500,3000,10000))
    ai=q.WMON if a['id']=='MON' else a['address'];bi=q.WMON if b['id']=='MON' else b['address']
    recipient=UNI if b['id']=='MON' else wallet
    if len(path)==2:swap=bytes.fromhex(call('exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))',
        ['(address,address,uint24,address,uint256,uint256,uint160)'],[(ai,bi,tiers[0],recipient,amount,minimum,0)])[2:])
    else:swap=bytes.fromhex(call('exactInput((bytes,address,uint256,uint256))',['(bytes,address,uint256,uint256)'],[(v3_paths.packed(path,tiers),recipient,amount,minimum)])[2:])
    calls=[swap]
    if b['id']=='MON':calls.append(bytes.fromhex(call('unwrapWETH9(uint256,address)',['uint256','address'],[minimum,wallet])[2:]))
    if a['id']=='MON':calls.append(bytes.fromhex(call('refundETH()',[],[])[2:]))
    return {'from':wallet,'to':UNI,'value':hex(amount if a['id']=='MON' else 0),
        'data':call('multicall(uint256,bytes[])',['uint256','bytes[]'],[deadline,calls])}

def kyber_validate(data,a,b,amount,out,slippage,wallet):
    # ABI from verified MetaAggregationRouterV2 source. Only its exact-input paths.
    if data[2:10].lower()==keccak(text='swap('+SWAP+')').hex()[:8]:
        execution=canonical(data,'swap('+SWAP+')',[SWAP])[0]
        target,approve,target_data,desc,_=execution
        if target.lower()!=EXECUTOR or approve.lower()!=s.ZERO or not target_data:raise s.Problem('Unreviewed swap executor',502,'route_identity')
    else:
        target,desc,target_data,_=canonical(data,'swapSimpleMode(address,'+DESC+',bytes,bytes)',['address',DESC,'bytes','bytes'])
        if a['id']=='MON' or target.lower()!=EXECUTOR or not target_data:raise s.Problem('Unreviewed swap executor',502,'route_identity')
    ai=q.NATIVE if a['id']=='MON' else a['address'];bi=q.NATIVE if b['id']=='MON' else b['address']
    src,dst,receivers,amounts,fees,fee_amounts,recipient,value,minimum,flags,permit=desc
    if src.lower()!=ai.lower() or dst.lower()!=bi.lower() or recipient.lower()!=wallet or value!=amount or not 0<minimum<=out or minimum<out*(10000-slippage)//10000:
        raise s.Problem('Swap tokens, amount or recipient changed',502,'route_identity')
    if permit or fees or fee_amounts or flags & ~(512|32) or len(receivers)!=len(amounts) or sum(amounts)>amount:
        raise s.Problem('Swap requests unreviewed fees or permissions',502,'route_identity')
    return minimum

def quote(who,data):
    if data.get('provider') in v2.PROVIDERS:return v2.quote(who,data)
    if data.get('provider') in extra.PROVIDERS:return extra.quote(who,data)
    user=s.require(who,human=True);wallet=s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
    if not wallet:raise s.Problem('Connect and verify your wallet first',409,'wallet_required')
    provider=data.get('provider','Kuru')
    if provider not in PROVIDERS:raise s.Problem('Unknown swap provider')
    if data.get('comparisonQuote'):
        selection=q.select(who,{**data,'quote':data['comparisonQuote']})
        if selection['fallback'] or selection['selected']['provider']!=provider:raise s.Problem('Choose an available route before swapping',409,'route_unavailable')
    if provider in {'Kuru','Kuru Flow'}:return s.GATEWAY.quote(who,data)
    a,b,amount=q.inputs(data)
    try:slippage=int(data.get('slippage',50))
    except (ValueError,TypeError):raise s.Problem('Invalid slippage')
    if not 1<=slippage<=100:raise s.Problem('Slippage must be between 0.01% and 1%')
    deadline=s.now()+120;details={}
    if provider=='Uniswap v3':
        reference=q.uniswap(a,b,amount);out=int(reference['outputRaw']);minimum=out*(10000-slippage)//10000
        if minimum<1:raise s.Problem('Amount too small',422)
        details=reference['details']
        transaction=uniswap_transaction(a,b,amount,out,minimum,wallet,deadline,details)
    else:
        ai=q.NATIVE if a['id']=='MON' else a['address'];bi=q.NATIVE if b['id']=='MON' else b['address']
        raw=s.http_json('https://aggregator-api.kyberswap.com/monad/api/v1/routes?'+q.urlencode({'tokenIn':ai,'tokenOut':bi,'amountIn':str(amount)}),headers={'X-Client-Id':'rally-monad'})
        route=raw.get('data',{}).get('routeSummary',{})
        if raw.get('code')!=0 or raw.get('data',{}).get('routerAddress','').lower()!=KYBER or route.get('tokenIn','').lower()!=ai.lower() or route.get('tokenOut','').lower()!=bi.lower() or str(route.get('amountIn'))!=str(amount):raise s.Problem('Quote identity changed',502,'route_identity')
        built=s.http_json('https://aggregator-api.kyberswap.com/monad/api/v1/route/build',{'routeSummary':route,'sender':wallet,'recipient':wallet,'slippageTolerance':slippage,'deadline':deadline},headers={'X-Client-Id':'rally-monad'})
        value=built.get('data',{});out=int(value.get('amountOut','0'));calldata=value.get('data','')
        if built.get('code')!=0 or value.get('routerAddress','').lower()!=KYBER or int(value.get('amountIn','0'))!=amount or int(value.get('transactionValue','0'))!=(amount if a['id']=='MON' else 0) or not 0<out<2**256:raise s.Problem('Built route identity changed',502,'route_identity')
        minimum=kyber_validate(calldata,a,b,amount,out,slippage,wallet)
        transaction={'from':wallet,'to':KYBER,'data':calldata,'value':hex(amount if a['id']=='MON' else 0)}
    verified=version(provider);ident=s.uid();expires=s.now()+30
    result={'id':ident,'wallet':wallet,'input':a['id'],'output':b['id'],'amount':s.units(amount,a['decimals']),'amountRaw':str(amount),
        'receive':s.units(out,b['decimals']),'outputRaw':str(out),'minimum':s.units(minimum,b['decimals']),'minimumRaw':str(minimum),
        'provider':provider,'chainId':143,'slippageBps':slippage,'expires':expires,'deadline':deadline,
        'approval':None if a['id']=='MON' else {'token':a['address'],'spender':transaction['to'],'amount':str(amount)},
        'transaction':transaction,'details':details,'fees':{'totalBps':0},**verified}
    s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(ident,user,wallet,a['id'],b['id'],str(amount),s.dump(result),expires))
    return result

def validate(quote):
    if quote.get('provider') in v2.PROVIDERS:return v2.validate(quote)
    if quote.get('provider') in extra.PROVIDERS:return extra.validate(quote)
    provider=quote.get('provider','Kuru Flow');verified=version(provider)
    if any(verified[k]!=quote.get(k) for k in verified):raise s.Problem('Router changed. Get a fresh quote.',409,'router_changed')
    if provider in {'Kuru','Kuru Flow'}:return
    a,b,amount=q.inputs({'input':quote['input'],'output':quote['output'],'amount':quote['amount']})
    wallet=quote['wallet'];tx=quote['transaction'];out=int(quote['outputRaw']);minimum=int(quote['minimumRaw'])
    if amount!=int(quote['amountRaw']) or quote['chainId']!=143 or quote['receive']!=s.units(out,b['decimals']) or quote['minimum']!=s.units(minimum,b['decimals']) or not 0<minimum<=out or minimum<out*(10000-quote['slippageBps'])//10000:raise s.Problem('Stored swap economics changed',409)
    if tx.get('from')!=wallet or tx.get('to')!=verified['router'] or int(tx.get('value','0x0'),16)!=(amount if a['id']=='MON' else 0):raise s.Problem('Stored swap identity changed',409)
    expected_approval=None if a['id']=='MON' else {'token':a['address'],'spender':verified['router'],'amount':str(amount)}
    if quote['approval']!=expected_approval:raise s.Problem('Stored allowance changed',409)
    if provider=='Uniswap v3':
        import v3_paths
        v3_paths.validate_pools(q.FACTORY,a,b,quote['details'],(100,500,3000,10000))
        expected=uniswap_transaction(a,b,amount,out,minimum,wallet,quote['deadline'],quote['details'])
        if expected!=tx:raise s.Problem('Stored swap data changed',409)
    elif kyber_validate(tx['data'],a,b,amount,out,quote['slippageBps'],wallet)!=minimum:raise s.Problem('Stored minimum changed',409)
