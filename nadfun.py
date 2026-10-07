"""nad.fun mainnet discovery and unsigned execution. No signing keys or custody.

API results are discovery candidates. Contract state establishes token identity;
quotes, lifecycle and fees always come from the official contracts at one block.
"""
import json, math, threading, time
from decimal import Decimal
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError
from eth_abi import encode, decode
from eth_utils import keccak
import service as s
import venues as v

ROOT=s.ROOT/'config/nadfun'
WMON='0x3bd359c1119da7da1d913d1c4d2b7c461115433a'
LVMON='0x91b81bfbe3a747230f0529aa28d8b2bc898e6d56'
FILES={'v1':{'curve':'curveAbi.json','lens':'lensAbi.json','router':'routerAbi.json','dex':'dexRouterAbi.json'},
       'v2':{'curve':'BondingCurve.json','router':'NadFunRouter.json','factory':'NadFunFactory.json','fees':'FeeCollector.json'}}
MANIFEST=json.loads((ROOT/'pins.json').read_text())
API_LOCK=threading.Lock();API_AT=0;API_RETRY_AT=0;SYNC_LOCK=threading.Lock();DRAFT_LOCK=threading.Lock();SYNC_ERROR=None
ABIS={};TRANSFER='0x'+keccak(text='Transfer(address,address,uint256)').hex()
CHARTS={};CHART_LOCK=threading.Lock()
MARKET_REFERENCES={};MARKET_REFERENCE_LOCK=threading.Lock()
REFERENCE_HEALTH={}

def market_numbers(market,decimals=18):
    """Provider USD reference and total-supply valuation, never an order quote."""
    def decimal(value):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() and result>=0 else None
        except Exception:return None
    price=decimal(market.get('price_usd'))
    raw=market.get('total_supply');supply=None
    if isinstance(raw,(str,int)) and not isinstance(raw,bool) and str(raw).isdigit() and len(str(raw))<=78:
        supply=Decimal(str(raw))/(Decimal(10)**decimals)
    cap=price*supply if price is not None and supply is not None else None
    return {'price':str(price) if price is not None else None,'totalSupply':str(supply) if supply is not None else None,'marketCap':str(cap) if cap is not None else None,'marketCapBasis':'total_supply','priceSource':'nad.fun USD reference'}

def refresh_market_references():
    # A bounded background snapshot keeps rendering independent of RPC reads.
    # Only exact, previously verified identities are exposed by public_info.
    failures=0;all_updates={}
    for order in ['creation_time','market_cap']:
        try:
            candidates=api('/order/'+order+'?'+urlencode({'page':1,'limit':100,'is_nsfw':'false','direction':'DESC'})).get('tokens',[])
            if not isinstance(candidates,list):raise ValueError('Invalid reference page')
        except Exception:failures+=1;continue
        observed=s.now();updates={}
        for candidate in candidates[:100]:
            ti=candidate.get('token_info',{});market=candidate.get('market_info',{})
            try:token=address(ti.get('token_id'))
            except s.Problem:continue
            if str(market.get('token_id','')).lower()!=token:continue
            updates[token]={'name':ti.get('name'),'symbol':ti.get('symbol'),'version':str(ti.get('version','')).lower(),'referenceAt':observed,**market_numbers(market)}
        with MARKET_REFERENCE_LOCK:
            MARKET_REFERENCES.update(updates)
            for token in list(MARKET_REFERENCES):
                if observed-MARKET_REFERENCES[token]['referenceAt']>900:MARKET_REFERENCES.pop(token,None)
            while len(MARKET_REFERENCES)>600:MARKET_REFERENCES.pop(min(MARKET_REFERENCES,key=lambda t:MARKET_REFERENCES[t]['referenceAt']))
        all_updates.update(updates)
    with MARKET_REFERENCE_LOCK:REFERENCE_HEALTH.update(state='partial' if failures else 'live',lastAttemptAt=s.now(),failedPages=failures,**({'lastSuccessAt':s.now()} if all_updates else {}))
    if all_updates:
        import market_universe as u
        with u.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS nad_market_references(address TEXT PRIMARY KEY,info TEXT NOT NULL)')
            for a,v in all_updates.items():c.execute('INSERT OR REPLACE INTO nad_market_references VALUES(?,?)',(a,s.dump(v)))
            c.execute("DELETE FROM nad_market_references WHERE json_extract(info,'$.referenceAt')<?",(s.now()-900,))

def market_background():
    try:
        import market_universe as u
        with u.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS nad_market_references(address TEXT PRIMARY KEY,info TEXT NOT NULL)')
            saved={r['address']:json.loads(r['info']) for r in c.execute('SELECT * FROM nad_market_references')}
        with MARKET_REFERENCE_LOCK:MARKET_REFERENCES.update({a:v for a,v in saved.items() if 0<=s.now()-v.get('referenceAt',0)<=900})
    except Exception:pass
    while True:
        try:refresh_market_references()
        except Exception:
            with MARKET_REFERENCE_LOCK:REFERENCE_HEALTH.update(state='delayed',lastAttemptAt=s.now())
        time.sleep(60)

def initialize():
    with s.connection() as db:db.executescript('''
    CREATE TABLE IF NOT EXISTS nad_tokens(address TEXT PRIMARY KEY,version TEXT NOT NULL,info TEXT NOT NULL,observed INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS nad_events(version TEXT,tx TEXT,log_index INTEGER,block INTEGER,block_hash TEXT,name TEXT,fields TEXT,PRIMARY KEY(tx,log_index));
    CREATE TABLE IF NOT EXISTS nad_sync(version TEXT PRIMARY KEY,block INTEGER,block_hash TEXT,updated INTEGER);
    CREATE TABLE IF NOT EXISTS nad_drafts(id TEXT PRIMARY KEY,user_id TEXT,wallet TEXT,request_key TEXT UNIQUE,payload TEXT,created INTEGER);
    ''')
    import launch_ingestion
    launch_ingestion.initialize()
    if LVMON not in s.GATEWAY.token_map:
        quote={'id':LVMON,'address':LVMON,'symbol':'LVMon','name':'LVMon','decimals':18,'chainId':143,'logoURI':None}
        s.GATEWAY.tokens.append(quote);s.GATEWAY.token_map[LVMON]=quote

def address(value):
    value=str(value or '').lower()
    if not s.re.fullmatch('0x[0-9a-f]{40}',value) or value==s.ZERO:raise s.Problem('Enter a Monad token contract address')
    return value

def contract(version,label):return MANIFEST['versions'][version][label]['address']
def abi(version,label):
    key=version+label
    if key not in ABIS:
        file=FILES[version][label];value=json.loads((ROOT/file).read_text())
        if s.digest(s.dump(value))!=MANIFEST['abiHashes'][file]:raise s.Problem('nad.fun interface changed. Review required.',503,'nad_contract_changed')
        ABIS[key]=value
    return ABIS[key]
def fn(version,label,name):return next(f for f in abi(version,label) if f.get('type')=='function' and f.get('name')==name)
def calldata(version,label,name,args=()):
    f=fn(version,label,name);types=[v.typ(x) for x in f['inputs']]
    return '0x'+keccak(text=name+'('+','.join(types)+')').hex()[:8]+encode(types,list(args)).hex()
def read(version,label,name,args=(),block='latest'):
    f=fn(version,label,name)
    data=s.rpc('eth_call',[{'to':contract(version,label),'data':calldata(version,label,name,args)},block])
    try:values=decode([v.typ(x) for x in f['outputs']],bytes.fromhex(data[2:]))
    except Exception:raise s.Problem('nad.fun contract read changed. Refresh and try again.',503,'nad_interface_changed')
    return v.named(f['outputs'][0],values[0]) if len(values)==1 else {o['name'] or str(i):v.named(o,x) for i,(o,x) in enumerate(zip(f['outputs'],values))}
def simple(target,name,types=(),args=(),outs=('uint256',),block='latest'):
    data='0x'+keccak(text=name+'('+','.join(types)+')').hex()[:8]+encode(list(types),list(args)).hex()
    result=s.rpc('eth_call',[{'to':target,'data':data},block])
    try:return decode(list(outs),bytes.fromhex(result[2:]))[0]
    except Exception:raise s.Problem('Could not verify this token contract',503,'nad_interface_changed')

def pin(version,creation=False):
    labels=['curve','router','lens','dex'] if version=='v1' else ['curve','router','factory','fees','manager']+(['creatorVault'] if creation else [])
    for label in labels:
        p=MANIFEST['versions'][version][label];a=p['address']
        if s.digest(s.rpc('eth_getCode',[a,'latest']).lower())!=p['codeHash']:raise s.Problem('nad.fun contract changed. Review required.',503,'nad_contract_changed')
        impl='0x'+s.rpc('eth_getStorageAt',[a,v.IMPL_SLOT,'latest'])[-40:].lower()
        if impl!=p['implementation'] or impl!=s.ZERO and s.digest(s.rpc('eth_getCode',[impl,'latest']).lower())!=p['implementationHash']:raise s.Problem('nad.fun implementation changed. Review required.',503,'nad_contract_changed')
    # Pin dependency wiring as well as code. These pointers can change in storage.
    if version=='v2':
        if read(version,'router','bondingCurve')!=contract(version,'curve') or read(version,'router','wrappedNative')!=WMON or read(version,'factory','protocolManager')!=contract(version,'manager') or read(version,'factory','feeCollector')!=contract(version,'fees'):raise s.Problem('nad.fun configuration changed. Review required.',503,'nad_contract_changed')
    for label in FILES[version]:abi(version,label)
    return {'version':version,'manifestHash':s.digest(s.dump(MANIFEST))}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def api(path,data=None,mime=None):
    """Respect the unauthenticated external API limit; never spoof Origin."""
    global API_AT,API_RETRY_AT
    with API_LOCK:
        if time.monotonic()<API_RETRY_AT:raise s.Problem('nad.fun is cooling down. Try again shortly.',503,'nad_api_backoff')
        remaining=7.5-(time.monotonic()-API_AT)
        if remaining>0:time.sleep(remaining)
        API_AT=time.monotonic()
        body=data if isinstance(data,bytes) else s.dump(data).encode() if data is not None else None
        request=Request('https://api.nad.fun'+path,data=body,headers={'User-Agent':'Rally/1.0','Accept':'application/json',**({'Content-Type':mime or 'application/json'} if body is not None else {})})
        try:
            with build_opener(NoRedirect).open(request,timeout=24) as response:raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError()
            result=json.loads(raw)
            if not isinstance(result,dict):raise ValueError()
            return result
        except HTTPError as e:
            if e.code==429:
                try:delay=float(e.headers.get('Retry-After','30'))
                except (TypeError,ValueError,AttributeError):delay=30
                API_RETRY_AT=time.monotonic()+max(5,min(120,delay)) if math.isfinite(delay) else time.monotonic()+30
            raise s.Problem('nad.fun is busy. Try again shortly.',503,'nad_api_'+str(e.code))
        except Exception:raise s.Problem('nad.fun data is unavailable. Try again.',503,'nad_api_unavailable')

def storage_url(url):
    p=urlsplit(str(url or ''))
    if p.scheme!='https' or p.hostname!='storage.nadapp.net' or p.port not in {None,443} or p.username or p.password or p.fragment:raise s.Problem('Invalid nad.fun media reference',502)
    return p.geturl()

def state(version,token,block=None):
    token=address(token);block=block or s.rpc('eth_blockNumber',[])
    if version=='v2':
        curve=read(version,'curve','getCurve',[token],block)
        if curve['token'].lower()!=token or not curve['createdAtBlock'] or curve['creator']==s.ZERO:raise s.Problem('This token is not registered on nad.fun',404,'nad_token_unverified')
        graduated=bool(read(version,'router','isGraduated',[token],block))
        if graduated!=curve['graduated']:raise s.Problem('Token lifecycle changed. Refresh.',409)
        pair=read(version,'factory','getPair',[token,curve['quoteToken']],block)
        if pair==s.ZERO or pair!=curve['pair']:raise s.Problem('Token pool identity changed',503)
        fee=read(version,'fees','getFeeConfig',[pair],block)
        if fee['baseToken']!=token or fee['quoteToken']!=curve['quoteToken']:raise s.Problem('Token fee identity changed',503)
        denominator=curve['initialTokenReserve']-curve['minTokenReserve']
        progress=10000 if graduated else max(0,min(10000,(curve['initialTokenReserve']-curve['virtualTokenReserve'])*10000//denominator)) if denominator>0 else 0
        penalty=0 if graduated else read(version,'curve','getSnipingPenalty',[token],block)
        return {'version':version,'phase':'dex' if graduated else 'curve','graduated':graduated,'locked':False,'progressBps':progress,'pair':pair,'quoteToken':curve['quoteToken'],'nativeSupported':curve['quoteToken']==WMON,'tradeSupported':curve['quoteToken'] in {WMON,LVMON},'quoteSymbol':'MON' if curve['quoteToken']==WMON else 'LVMon' if curve['quoteToken']==LVMON else 'Unknown quote','creator':curve['creator'],'createdBlock':curve['createdAtBlock'],'block':int(block,16),'router':contract(version,'router'),'creatorFeeBps':fee['creatorFeeRate'],'protocolFeeBps':fee['dexProtocolFeeRate'] if graduated else fee['curveProtocolFeeRate'],'snipingPenaltyBps':penalty}
    if version!='v1':raise s.Problem('Unknown nad.fun token version')
    created=read(version,'curve','createdAt',[token],block)
    graduated=read(version,'curve','isGraduated',[token],block)
    if not created and not graduated:raise s.Problem('This token is not registered on nad.fun',404,'nad_token_unverified')
    if read(version,'lens','isGraduated',[token],block)!=graduated:raise s.Problem('Token lifecycle identity mismatch',503)
    locked=read(version,'curve','isLocked',[token],block)
    return {'version':version,'phase':'dex' if graduated else 'curve','graduated':graduated,'locked':locked and not graduated,'progressBps':10000 if graduated else min(10000,read(version,'lens','getProgress',[token],block)),'quoteToken':WMON,'nativeSupported':True,'tradeSupported':True,'quoteSymbol':'MON','router':contract(version,'dex' if graduated else 'router'),'block':int(block,16),'creatorFeeBps':None,'protocolFeeBps':None,'snipingPenaltyBps':None}

def remember(candidate):
    ti=candidate.get('token_info',{});token=address(ti.get('token_id'));version=str(ti.get('version','')).lower()
    if version not in FILES:raise s.Problem('Unsupported nad.fun version')
    live=state(version,token);block=hex(live['block']);prior=s.one('SELECT version,info FROM nad_tokens WHERE address=?',(token,))
    if prior and prior['version']==version:
        known=json.loads(prior['info']);name=known['name'];symbol=known['symbol'];decimals=known['decimals']
    else:name=simple(token,'name',outs=['string'],block=block);symbol=simple(token,'symbol',outs=['string'],block=block);decimals=simple(token,'decimals',outs=['uint8'],block=block)
    if decimals!=18 or name!=ti.get('name') or symbol!=ti.get('symbol'):raise s.Problem('nad.fun token identity mismatch',502)
    image=None
    if not ti.get('is_nsfw') and ti.get('image_uri'):
        try:image=storage_url(ti['image_uri'])
        except s.Problem:pass
    market=candidate.get('market_info',{});metrics=market_numbers(market)
    creator=(ti.get('creator') or {}).get('account_id')
    if version=='v2' and str(creator or '').lower()!=live['creator']:raise s.Problem('nad.fun creator identity mismatch',502)
    info={'id':token,'address':token,'chainId':143,'decimals':18,'name':name,'symbol':symbol,'logoURI':image,'venue':'nad.fun','nadfun':True,'version':version,'created':int(ti.get('created_at') or 0),'creator':creator,'description':str(ti.get('description') or '')[:500],**metrics,'holders':market.get('holder_count'),'referenceAt':s.now(),**live}
    s.write('INSERT INTO nad_tokens VALUES(?,?,?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info,observed=excluded.observed',(token,version,s.dump(info),s.now()))
    return info

def token_info(token,refresh=True):
    token=address(token);row=s.one('SELECT * FROM nad_tokens WHERE address=?',(token,))
    if not row:
        info=remember(api('/token/'+token));row=s.one('SELECT * FROM nad_tokens WHERE address=?',(token,))
    info=json.loads(row['info'])
    if refresh:
        live=state(row['version'],token);info.update(live)
        s.write('UPDATE nad_tokens SET info=?,observed=? WHERE address=?',(s.dump(info),s.now(),token))
    import launch_ingestion
    launch_ingestion.viewed([info])
    return public_info(info)

def public_info(info):
    info=dict(info)
    with MARKET_REFERENCE_LOCK:reference=MARKET_REFERENCES.get(info.get('id'))
    if reference and all(reference.get(k)==info.get(k) for k in ['name','symbol','version']) and reference['referenceAt']>=info.get('referenceAt',0):
        info.update({k:v for k,v in reference.items() if k not in ['name','symbol','version']})
    age=s.now()-info.get('referenceAt',0);info['stale']=not 0<=age<=180;info['priceAgeSeconds']=max(0,age)
    if age>900 or age<0:info['price']=None;info['marketCap']=None
    info['lastKnown']=bool(info.get('price')) and info['stale']
    return info

def references(assets):
    import launch_ingestion
    ids=list(dict.fromkeys(str(assets).split(',')))
    if not 1<=len(ids)<=60:raise s.Problem('Invalid launch references')
    ids=[address(a) for a in ids]
    entries=[public_info(json.loads(row['info'])) for row in s.rows('SELECT info FROM nad_tokens WHERE address IN ('+','.join('?' for _ in ids)+')',ids)]
    launch_ingestion.viewed(entries)
    return {'tokens':entries,'fetchedAt':s.now(),'financialTransactions':0}

def catalog(phase=None,sort='latest',query='',cursor='',limit=100):
    if phase not in (None,'','dex'):raise s.Problem('Unknown launch filter',400)
    if sort not in ('latest','cap'):raise s.Problem('Unknown launch order',400)
    import base64,launch_ingestion
    query=str(query).strip().lower()[:120]
    try:limit=int(limit)
    except (TypeError,ValueError):raise s.Problem('Invalid launch page')
    if not 1<=limit<=100:raise s.Problem('Invalid launch page')
    filters=['1=1'];args=[];snapshot=s.now();after=None
    if phase=='dex':filters.append('json_extract(info,"$.graduated")=1')
    if query:
        filters.append('(instr(lower(json_extract(info,"$.name")),?)>0 OR instr(lower(json_extract(info,"$.symbol")),?)>0 OR instr(address,?)>0)');args.extend([query]*3)
    if cursor:
        try:
            if len(cursor)>1200:raise ValueError()
            after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            if after['sort']!=sort or after['phase']!=(phase or '') or after['query']!=query or not isinstance(after['snapshot'],int) or not isinstance(after['created'],int):raise ValueError()
            address(after['address']);snapshot=after['snapshot']
            if not 0<=s.now()-snapshot<=3600:raise ValueError()
        except Exception:raise s.Problem('Launch page expired. Refresh the list.',400,'launch_cursor_invalid')
    filters.append('coalesce(json_extract(info,"$.created"),0)<=?');args.append(snapshot)
    where=' WHERE '+' AND '.join(filters);total=s.one('SELECT count(*) AS n FROM nad_tokens'+where,args)['n']
    created='coalesce(json_extract(info,"$.created"),0)'
    cap='CASE WHEN json_extract(info,"$.referenceAt") BETWEEN '+str(s.now()-900)+' AND '+str(s.now())+' THEN coalesce(CAST(json_extract(info,"$.marketCap") AS REAL),-1) ELSE -1 END'
    if after:
        if sort=='cap':
            where+=' AND ('+cap+'<? OR ('+cap+'=? AND ('+created+'<? OR ('+created+'=? AND address<?))))';args.extend([after['cap'],after['cap'],after['created'],after['created'],after['address']])
        else:where+=' AND ('+created+'<? OR ('+created+'=? AND address<?))';args.extend([after['created'],after['created'],after['address']])
    order=(cap+' DESC,' if sort=='cap' else '')+created+' DESC,address DESC'
    rows=s.rows('SELECT info,'+cap+' AS sort_cap FROM nad_tokens'+where+' ORDER BY '+order+' LIMIT ?',(*args,limit+1))
    entries=[public_info(json.loads(x['info'])) for x in rows[:limit]];next_cursor=None
    if len(rows)>limit:
        last=entries[-1];key={'sort':sort,'phase':phase or '','query':query,'snapshot':snapshot,'created':last.get('created',0),'address':last['id'],'cap':rows[limit-1]['sort_cap']}
        next_cursor=base64.urlsafe_b64encode(s.dump(key).encode()).decode().rstrip('=')
    launch_ingestion.viewed(entries[:24])
    sync=s.rows('SELECT * FROM nad_sync')
    with MARKET_REFERENCE_LOCK:health=dict(REFERENCE_HEALTH)
    return {'tokens':entries,'total':total,'nextCursor':next_cursor,'fetchedAt':max((x.get('referenceAt',0) for x in entries),default=None),'sync':sync,'error':SYNC_ERROR,'referenceHealth':health,'ingestion':launch_ingestion.health(),'source':'nad.fun · contract verified','chainId':143,'refreshSeconds':30,'sort':sort,'marketCapBasis':'total_supply'}

def hydrate_events(limit=2):
    # Persisted events also feed discovery when launches fall outside an API page.
    pending=s.rows('''SELECT lower(json_extract(fields,'$.token')) AS token FROM nad_events
        WHERE name IN ('Create','CurveCreate') AND json_extract(fields,'$.token') IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM nad_tokens t WHERE t.address=lower(json_extract(nad_events.fields,'$.token')))
        GROUP BY lower(json_extract(fields,'$.token')) ORDER BY max(block) DESC LIMIT ?''',(limit,))
    for row in pending:
        try:remember(api('/token/'+address(row['token'])))
        except s.Problem:continue

def event(version,label,log):
    for e in abi(version,label):
        if e.get('type')!='event' or e.get('anonymous'):continue
        topic='0x'+keccak(text=e['name']+'('+','.join(v.typ(i) for i in e['inputs'])+')').hex()
        if not log.get('topics') or log['topics'][0].lower()!=topic:continue
        plain=[i for i in e['inputs'] if not i.get('indexed')];idx=[i for i in e['inputs'] if i.get('indexed')]
        values=decode([v.typ(i) for i in plain],bytes.fromhex(log['data'][2:]))
        fields={i['name']:v.named(i,x) for i,x in zip(plain,values)}
        fields.update({i['name']:v.named(i,decode([v.typ(i)],bytes.fromhex(t[2:]))[0]) for i,t in zip(idx,log['topics'][1:])})
        return {'name':e['name'],'fields':fields}
    return None

def sync_once():
    """Bounded finalized event cursor + API candidates. Failure retains last good data."""
    global SYNC_ERROR
    if not SYNC_LOCK.acquire(False):return
    try:
        final=s.rpc('eth_getBlockByNumber',['finalized',False]);end=int(final['number'],16)
        for version in FILES:
            cursor=s.one('SELECT * FROM nad_sync WHERE version=?',(version,));start=cursor['block']+1 if cursor else max(0,end-2000)
            if cursor:
                canonical=s.rpc('eth_getBlockByNumber',[hex(cursor['block']),False])
                if not canonical or canonical['hash'].lower()!=cursor['block_hash'].lower():raise s.Problem('Finalized index changed. Review required.',503,'nad_index_reorg')
            stop=min(end,start+999)
            if stop<start:continue
            e=[e for e in abi(version,'curve') if e.get('type')=='event' and e['name'] in {'Create','Graduate','CurveCreate','CurveGraduate','CurveTokenLocked'}]
            topics=['0x'+keccak(text=x['name']+'('+','.join(v.typ(i) for i in x['inputs'])+')').hex() for x in e]
            logs=s.rpc('eth_getLogs',[{'address':contract(version,'curve'),'fromBlock':hex(start),'toBlock':hex(stop),'topics':[topics]}])
            for log in logs:
                if log.get('removed'):continue
                item=event(version,'curve',log)
                if not item:continue
                s.write('INSERT OR IGNORE INTO nad_events VALUES(?,?,?,?,?,?,?)',(version,log['transactionHash'],int(log['logIndex'],16),int(log['blockNumber'],16),log['blockHash'],item['name'],s.dump(item['fields'])))
                token=item['fields'].get('token')
                if token and s.one('SELECT 1 FROM nad_tokens WHERE address=?',(token.lower(),)):
                    # Discovery must not hold the event cursor behind slow reads.
                    import launch_ingestion
                    launch_ingestion.viewed([{'id':token.lower()}])
            block=s.rpc('eth_getBlockByNumber',[hex(stop),False])
            s.write('INSERT INTO nad_sync VALUES(?,?,?,?) ON CONFLICT(version) DO UPDATE SET block=excluded.block,block_hash=excluded.block_hash,updated=excluded.updated',(version,stop,block['hash'],s.now()))
        SYNC_ERROR=None
    except s.Problem as e:SYNC_ERROR=e.code
    except Exception:SYNC_ERROR='nad_sync_unavailable'
    finally:SYNC_LOCK.release()

def background():
    import launch_ingestion
    launch_ingestion.loops()

def quote(token,kind,amount,slippage=100):
    info=token_info(token,False);block=s.rpc('eth_blockNumber',[]);live=state(info['version'],info['address'],block)
    if kind not in {'buy','sell'}:raise s.Problem('Choose Buy or Sell')
    if not live['nativeSupported'] and live.get('quoteToken')!=LVMON:raise s.Problem('This quote asset is not supported.',409,'nad_quote_asset_unsupported')
    if live['locked']:raise s.Problem('This token is migrating. Try again after graduation.',409,'nad_migrating')
    if not isinstance(slippage,int) or isinstance(slippage,bool) or not 10<=slippage<=500:raise s.Problem('Choose slippage from 0.1% to 5%')
    raw=v.raw(amount,18);version=info['version']
    if version=='v2':out=read(version,'router','getAmountOut',[info['address'],raw,kind=='buy'],block)
    else:
        result=read(version,'lens','getAmountOut',[info['address'],raw,kind=='buy'],block);out=result['amountOut']
        if result['router']!=live['router']:raise s.Problem('Unrecognized nad.fun route',503,'nad_router_mismatch')
    minimum=out*(10000-slippage)//10000
    if not out or not minimum:raise s.Problem('No executable liquidity for this amount',409,'nad_no_liquidity')
    quote_symbol='MON' if live['nativeSupported'] else 'LVMon'
    return {'token':info['address'],'symbol':info['symbol'],'amount':s.units(raw,18),'amountRaw':str(raw),'receive':s.units(out,18),'receiveRaw':str(out),'minimum':s.units(minimum,18),'minimumRaw':str(minimum),'inputAsset':quote_symbol if kind=='buy' else info['symbol'],'outputAsset':info['symbol'] if kind=='buy' else quote_symbol,'slippageBps':slippage,'expires':s.now()+45,**live}

def draft(who,data,key):
    user,wallet=v.wallet(who)
    if not key or len(key)>100:raise s.Problem('A stable launch request key is required')
    name=str(data.get('name','')).strip();symbol=str(data.get('symbol','')).strip();description=str(data.get('description') or '').strip()
    if not 1<=len(name)<=32 or '\n' in name or '\r' in name or not s.re.fullmatch('[A-Za-z0-9]{1,10}',symbol) or len(description)>500:raise s.Problem('Use a name under 33 characters, an alphanumeric symbol under 11, and a description under 501.')
    media=s.one('SELECT * FROM media WHERE id=? AND owner=? AND actor=?',(data.get('media'),user,user))
    if not media or media['mime'] not in {'image/webp','image/png','image/jpeg'} or media['size']>5*1024*1024:raise s.Problem('Upload your token image first. 5 MB maximum.')
    intent={'name':name,'symbol':symbol,'description':description or None,'media':media['id']}
    for field,prefix in [('website','https://'),('twitter','https://x.com/'),('telegram','https://t.me/')]:
        value=str(data.get(field) or '').strip()
        if value and (not value.startswith(prefix) or len(value)>256 or urlsplit(value).username):raise s.Problem('Use a valid '+field+' HTTPS link')
        intent[field]=value or None
    if 'allocations' in data or 'identity' in data:
        import launchpad
        intent['launch']=launchpad.intent(who,data)
    fingerprint=s.digest(s.dump(intent));request_key=user+':'+key
    with DRAFT_LOCK:
        prior=s.one('SELECT * FROM nad_drafts WHERE request_key=?',(request_key,))
        if prior:
            payload=json.loads(prior['payload'])
            if prior['wallet']!=wallet or payload['fingerprint']!=fingerprint:raise s.Problem('Launch request key already used',409)
            if payload.get('state')=='ready':return {'id':prior['id'],**payload}
            ident=prior['id']
        else:
            if s.one('SELECT count(*) n FROM nad_drafts WHERE user_id=? AND created>?',(user,s.now()-86400))['n']>=5:raise s.Problem('Daily launch preparation limit reached',429)
            ident=s.uid();payload={'intent':intent,'fingerprint':fingerprint,'state':'preparing','version':'v2','creator':wallet}
            s.write('INSERT INTO nad_drafts VALUES(?,?,?,?,?,?)',(ident,user,wallet,request_key,s.dump(payload),s.now()))
        def save():s.write('UPDATE nad_drafts SET payload=? WHERE id=?',(s.dump(payload),ident))
        if not payload.get('imageURI'):
            result=api('/metadata/image',(s.STATE/'media'/media['path']).read_bytes(),media['mime'])
            if result.get('is_nsfw'):raise s.Problem('Choose another image',409)
            payload['imageURI']=storage_url(result.get('image_uri'));save()
        if not payload.get('metadataURI'):
            metadata={k:intent[k] for k in ['name','symbol','description','website','twitter','telegram']};metadata['image_uri']=payload['imageURI']
            result=api('/metadata/metadata',metadata);echo=result.get('metadata',{})
            if any(echo.get(k)!=value for k,value in metadata.items()) or echo.get('is_nsfw'):raise s.Problem('Token metadata does not match your launch',502)
            payload['metadataURI']=storage_url(result.get('metadata_uri'));save()
        if not payload.get('salt'):
            result=api('/token/salt',{'creator':wallet,'name':name,'symbol':symbol,'metadata_uri':payload['metadataURI'],'version':'V2'})
            salt=str(result.get('salt',''))
            if not s.re.fullmatch('0x[0-9a-fA-F]{64}',salt):raise s.Problem('Invalid token creation salt',502)
            payload.update(salt=salt,predictedToken=address(result.get('address')),state='ready');save()
        return {'id':ident,**payload}

def creation_fee(block='latest'):
    manager=contract('v2','manager')
    if not simple(manager,'isCreatorFeeRateAllowed',['uint16'],[100],['bool'],block):raise s.Problem('Creator fee configuration changed',503)
    return simple(manager,'deployFee',['address'],[WMON],block=block)

def drafts(who):
    user,wallet=v.wallet(who);items=[]
    for row in s.rows('SELECT * FROM nad_drafts WHERE user_id=? AND wallet=? ORDER BY created DESC LIMIT 10',(user,wallet)):
        p=json.loads(row['payload'])
        submitted=s.one("SELECT 1 FROM execution_records r JOIN execution_plans x ON r.plan=x.id WHERE json_extract(x.payload,'$.args.draft')=? AND r.state NOT IN ('failed','invalid')",(row['id'],))
        if p.get('state')=='ready' and not submitted:items.append({'id':row['id'],'name':p['intent']['name'],'symbol':p['intent']['symbol'],'imageURI':p['imageURI'],'intent':p['intent'],'created':row['created']})
    return {'drafts':items}

def plan(who,data):
    user,wallet=v.wallet(who);kind=data.get('kind');approval=None;created=s.now()
    if kind=='create':
        row=s.one('SELECT * FROM nad_drafts WHERE id=? AND user_id=?',(data.get('draft'),user))
        if not row or row['wallet']!=wallet:raise s.Problem('Your launch draft was not found',404)
        d=json.loads(row['payload'])
        if d.get('state')!='ready':raise s.Problem('Finish preparing token metadata first',409)
        if s.one("SELECT 1 FROM execution_records r JOIN execution_plans p ON r.plan=p.id WHERE p.user_id=? AND p.venue='nadfun' AND p.kind='create' AND json_extract(p.payload,'$.args.draft')=? AND r.state NOT IN ('failed','invalid')",(user,row['id'])):raise s.Problem('This token launch was submitted. Check Activity.',409,'nad_launch_submitted')
        version='v2';pinned=pin(version,True);value=creation_fee();target=contract(version,'router');deadline=created+180
        if s.rpc('eth_getCode',[d['predictedToken'],'latest'])!='0x':raise s.Problem('This token address is already deployed. Check Activity.',409)
        intent=d['intent'];vault=[(contract(version,'creatorVault'),10000,encode(['address'],[wallet]))];vault_pin=None
        if intent.get('launch'):
            import launchpad
            policy=intent['launch'];launchpad.identity(user,policy['identity'])
            vault_pin=launchpad.pin_allocations(policy['allocations']);vault=launchpad.vaults(policy['allocations'],wallet,policy.get('beneficiary'))
        args=(intent['name'],intent['symbol'],d['metadataURI'],WMON,100,vault,bytes.fromhex(d['salt'][2:]),0,0,deadline)
        txdata=calldata(version,'router','createWithNative',[args])
        summary={'action':'create','asset':intent['symbol'],'name':intent['name'],'token':d['predictedToken'],'amount':s.units(value,18),'inputAsset':'MON','outputAsset':intent['symbol'],'creatorFeeBps':100,'feeRecipient':wallet,'feeVault':contract(version,'creatorVault'),'initialBuy':'0','phase':'new','version':version,'metadataURI':d['metadataURI']}
        if intent.get('launch'):summary.update(allocations=intent['launch']['allocations'],identity=intent['launch']['identity'],beneficiary=intent['launch'].get('beneficiary'),vaultPin=vault_pin)
        expires=created+90
    else:
        q=quote(data.get('token'),kind,data.get('amount'),data.get('slippage',100));version=q['version'];pinned=pin(version)
        q=quote(data.get('token'),kind,data.get('amount'),data.get('slippage',100));target=q['router'];native=q.get('nativeSupported',True);value=int(q['amountRaw']) if kind=='buy' and native else 0;deadline=created+120
        if kind=='buy' and native:args=(int(q['minimumRaw']),q['token'],wallet,deadline)
        elif kind=='buy':args=(int(q['amountRaw']),int(q['minimumRaw']),q['token'],wallet,deadline);approval={'token':q['quoteToken'],'spender':target,'amountRaw':q['amountRaw']}
        else:args=(int(q['amountRaw']),int(q['minimumRaw']),q['token'],wallet,deadline);approval={'token':q['token'],'spender':target,'amountRaw':q['amountRaw']}
        label='router' if version=='v2' or q['phase']=='curve' else 'dex'
        method=('buyWithNative' if kind=='buy' else 'sellToNative') if version=='v2' and native else kind
        txdata=calldata(version,label,method,[args])
        summary={'action':kind,'asset':q['symbol'],**q};expires=q['expires']
    tx={'from':wallet,'to':target,'data':txdata,'value':hex(value),'chainId':'0x8f'}
    payload={'summary':summary,'transaction':tx,'approval':approval,'pin':pinned,'args':data,'created':created,'expires':expires,'deadline':deadline}
    ident=s.uid();s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,wallet,'nadfun',kind,s.dump(payload),expires))
    return {'id':ident,**payload}

def prepare(row,p):
    version=p['summary']['version'];pin(version,row['kind']=='create')
    if p['pin']['manifestHash']!=s.digest(s.dump(MANIFEST)):raise s.Problem('Launch interface changed. Review again.',409)
    if row['kind']=='create':
        if p['summary'].get('allocations'):
            import launchpad
            launchpad.identity(row['user_id'],p['summary']['identity'])
            if launchpad.pin_allocations(p['summary']['allocations'])!=p['summary']['vaultPin']:raise s.Problem('Fee vault configuration changed',409)
        value=creation_fee()
        if value!=int(p['transaction']['value'],16):raise s.Problem('Launch fee changed. Review a fresh transaction.',409,'nad_fee_changed')
        if s.rpc('eth_getCode',[p['summary']['token'],'latest'])!='0x':raise s.Problem('This token address is already deployed',409)
    else:
        q=quote(p['summary']['token'],row['kind'],p['summary']['amount'],p['summary']['slippageBps'])
        if q['phase']!=p['summary']['phase'] or q['router']!=p['transaction']['to']:raise s.Problem('This token migrated. Review its DEX quote.',409,'nad_phase_changed')
        if int(q['receiveRaw'])<int(p['summary']['minimumRaw']):raise s.Problem('Price moved beyond your slippage. Review a fresh quote.',409,'nad_price_changed')
    # Generic exact-amount approval, gas and balance checks run in venues.prepare.

def simulate_creation(p,block='latest'):
    tx={k:x for k,x in p['transaction'].items() if k!='chainId'}
    result=s.rpc('eth_call',[tx,block]);outputs=fn('v2','router','createWithNative')['outputs']
    token,out=decode([v.typ(o) for o in outputs],bytes.fromhex(result[2:]))
    if token!=p['summary']['token'] or out!=0:raise s.Problem('Token creation result differs from the reviewed address',409,'nad_creation_mismatch')

def chart(token,interval='60'):
    info=token_info(token,False)
    if interval not in {'1','5','15','60','240','1D'}:raise s.Problem('Invalid chart interval')
    key=info['address']+':'+interval
    with CHART_LOCK:
        cached=CHARTS.get(key)
        if cached and s.now()-cached['fetchedAt']<90:return cached
        result=_chart(info,interval)
        if len(CHARTS)>100:CHARTS.clear()
        CHARTS[key]=result
        return result

def _chart(info,interval):
    result=api('/trade/chart/'+info['address']+'?'+urlencode({'resolution':interval,'from':s.now()-86400*7,'to':s.now(),'countback':200,'chart_type':'price_usd'}))
    candles=[]
    arrays=[result.get(k,[]) for k in ['t','o','h','l','c','v']]
    if len({len(x) for x in arrays})!=1:raise s.Problem('Chart data incomplete',502)
    for t,o,h,l,c,volume in zip(*arrays):
        values=[float(x) for x in [o,h,l,c,volume]]
        if any(not math.isfinite(x) or x<0 for x in values) or min(values[:4])<values[2] or max(values[:4])>values[1]:continue
        candles.append({'time':int(t),'open':values[0],'high':values[1],'low':values[2],'close':values[3],'volume':values[4]})
    candles=sorted({c['time']:c for c in candles}.values(),key=lambda c:c['time'])[-200:]
    return {'token':info['address'],'candles':candles,'source':'nad.fun','interval':interval,'fetchedAt':s.now()}

def reconcile(row):
    if row['state'] in {'finalized','failed','invalid'}:return
    receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not block or block['hash'].lower()!=receipt['blockHash'].lower():return
    p=json.loads(row['payload']);summary=p['summary'];wallet=p['transaction']['from'];token=summary['token'];version=summary['version']
    if int(block['timestamp'],16)<p['created']-5:return
    final=s.rpc('eth_getBlockByNumber',['finalized',False]);status='finalized' if int(final['number'],16)>=int(receipt['blockNumber'],16) else 'confirmed'
    outcome={'receipt':receipt,'businessState':'venue_result_pending','token':token,'phase':summary['phase'],'events':[],'chainState':status}
    if int(receipt['status'],16)!=1:status='failed';outcome['businessState']='reverted'
    else:
        for log in receipt.get('logs',[]):
            label='curve' if log['address'].lower()==contract(version,'curve') else 'router' if log['address'].lower()==p['transaction']['to'] else None
            if label:
                try:
                    item=event(version,label,log)
                    if item:outcome['events'].append(item)
                except Exception:pass
        events=outcome['events'];transfers=[]
        for log in receipt.get('logs',[]):
            if log['address'].lower()==token and len(log.get('topics',[]))==3 and log['topics'][0].lower()==TRANSFER:
                transfers.append(('0x'+log['topics'][1][-40:].lower(),'0x'+log['topics'][2][-40:].lower(),int(log['data'],16)))
        if row['kind']=='create':
            matches=[e['fields'] for e in events if e['name']=='Create' and e['fields'].get('token')==token and e['fields'].get('creator')==wallet and e['fields'].get('tokenURI')==summary['metadataURI'] and e['fields'].get('name')==summary['name'] and e['fields'].get('symbol')==summary['asset'] and e['fields'].get('quoteToken')==WMON]
            if len(matches)==1:
                # Independent contract readback at the receipt block establishes the new identity.
                live=state(version,token,receipt['blockNumber'])
                if live['creator']==wallet and live['createdBlock']==int(receipt['blockNumber'],16):
                    outcome.update(businessState='token_created',createdToken=token,initialTokens='0',createdBlock=live['createdBlock'])
                    try:
                        draft_row=s.one('SELECT payload FROM nad_drafts WHERE id=?',(p['args']['draft'],))
                        d=json.loads(draft_row['payload']);intent=d['intent']
                        remember({'token_info':{'token_id':token,'version':'V2','name':intent['name'],'symbol':intent['symbol'],'image_uri':d['imageURI'],'description':intent['description'],'created_at':int(block['timestamp'],16),'creator':{'account_id':wallet}}})
                    except s.Problem:pass  # API indexing can lag canonical contract creation.
                    if status=='finalized':
                        import launchpad
                        try:launchpad.finalized(row,p,outcome,receipt,block)
                        except s.Problem:outcome['socialConnection']='pending_registration'
        else:
            buy=row['kind']=='buy';required=int(summary['minimumRaw']);spent=int(summary['amountRaw'])
            names={'Buy' if buy else 'Sell'} if version=='v2' else {'CurveBuy' if buy else 'CurveSell'}
            actors={wallet} if version=='v2' else {wallet,p['transaction']['to']}
            matches=[e['fields'] for e in events if e['name'] in names and e['fields'].get('token')==token and e['fields'].get('buyer' if buy else 'seller',e['fields'].get('sender')) in actors and e['fields'].get('amountIn')==spent and e['fields'].get('amountOut',0)>=required]
            delta=sum(n for src,dst,n in transfers if dst==wallet)-sum(n for src,dst,n in transfers if src==wallet)
            if buy and delta>=required and (len(matches)==1 or version=='v1' and summary['phase']=='dex'):
                outcome.update(businessState='swap_delivered',received=s.units(delta,18),receivedAsset=summary['asset'])
            elif not buy and delta==-spent and len(matches)==1:
                received=matches[0]['amountOut']
                if summary.get('nativeSupported',True):outcome.update(businessState='swap_delivered',received=s.units(received,18),receivedAsset='MON')
                else:
                    delivered=0
                    for log in receipt.get('logs',[]):
                        if log['address'].lower()==summary['quoteToken'] and len(log.get('topics',[]))==3 and log['topics'][0].lower()==TRANSFER:
                            src='0x'+log['topics'][1][-40:].lower();dst='0x'+log['topics'][2][-40:].lower();amount=int(log['data'],16)
                            delivered+=(amount if dst==wallet else 0)-(amount if src==wallet else 0)
                    if delivered==received:outcome.update(businessState='swap_delivered',received=s.units(received,18),receivedAsset=summary['outputAsset'])
            elif not buy and delta==-spent and version=='v1' and summary['phase']=='dex':
                # Isolate this transaction's native payout; a block balance delta can
                # include unrelated internal transfers and is insufficient proof.
                trace=s.rpc_response('debug_traceTransaction',[row['tx'],{'tracer':'callTracer','timeout':'5s'}])
                def paid(frame):
                    if not isinstance(frame,dict) or frame.get('error'):return 0
                    kind=str(frame.get('type','')).upper();amount=int(frame.get('value','0x0'),16) if kind in {'CALL','CREATE','CREATE2','SELFDESTRUCT'} else 0
                    net=(amount if str(frame.get('to','')).lower()==wallet else 0)-(amount if str(frame.get('from','')).lower()==wallet else 0)
                    return net+sum(paid(child) for child in frame.get('calls',[]))
                if not trace.get('error') and isinstance(trace.get('result'),dict):
                    received=paid(trace['result'])
                    if received>=required:outcome.update(businessState='swap_delivered',received=s.units(received,18),receivedAsset='MON',proof='canonical_receipt_and_transaction_trace')
                else:outcome['payoutProof']='trace_unavailable'
        try:outcome['balanceRaw']=str(simple(token,'balanceOf',['address'],[wallet],block=receipt['blockNumber']))
        except s.Problem:outcome['balanceReadback']='unavailable'
    if status=='finalized' and outcome['businessState']=='venue_result_pending':status='confirmed'
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(status,s.dump(outcome),row['id']))
