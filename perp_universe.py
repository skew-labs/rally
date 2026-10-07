"""Whole venue catalogs, scoped to markets whose execution stays on Monad."""
import json, math, os, threading, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
import service as s
import market_universe as u

LOCK=threading.Lock();CACHE={};CONFIG={};CONFIG_AT={};BUSY=threading.Lock()
KEEP_SECONDS=900
HERMES_BLOCKED_UNTIL=0
POOL='0xea1b8e4ab7f14f7dca68c5b214303b13078fc5ec'
PINGU='0xe5cdf1b3b36b9799b33e5c6f8c4c8b03848c6470'
HEADERS={'User-Agent':'Mozilla/5.0','Origin':'https://app.leverup.xyz','Referer':'https://app.leverup.xyz/'}
BLOCKERS=[{'venue':'Bean','state':'adapter_pending','reason':'Public mainnet market reader and order interface need verification'},
 {'venue':'Monday Trade','state':'access_required','reason':'Official mainnet market API requires Monday key and HMAC; public SDK deployment and order acceptance remain unverified','sourceURL':'https://docs.monday.trade/perp-trading-apis/introduction'},
 {'venue':'Narwhal','state':'unavailable','reason':'Current app redirects away from perpetual trading'},
 {'venue':'OBSDN','state':'restricted','reason':'Provider displays a region restriction'},
 {'venue':'HelloTrade','state':'gated_alpha','reason':'Provider requires alpha access'},
 {'venue':'Blinq','state':'prediction','reason':'Price prediction markets, not continuous perpetuals'},
 {'venue':'Purps','state':'spot','reason':'Current public app offers spot trading'}]

def positive(value):
    try:v=float(value)
    except (ValueError,TypeError):return None
    return v if math.isfinite(v) and v>0 else None

def leverup():
    from eth_abi import decode
    if time.time()-CONFIG_AT.get('LeverUp',0)>600:
        items=[];total=None;page=0
        while total is None or len(items)<total:
            raw=s.http_json('https://service.leverup.xyz/v1/pairs?'+urlencode({'block_chain':'MONAD','is_ready_to_display':'true','size':100,'page':page,'volume_time_range':'ONE_DAY'}),headers=HEADERS,timeout=6)
            total=int(raw['totalElements'])
            if not 0<=total<=5000 or page>50:raise ValueError('Invalid venue pagination')
            part=raw['content']
            if not part and len(items)<total:raise ValueError('Incomplete venue page')
            items+=part;page+=1
        if len({x['base'].lower() for x in items})!=total:raise ValueError('Duplicate venue pages')
        CONFIG['LeverUp']=items;CONFIG_AT['LeverUp']=time.time()
    items=CONFIG['LeverUp'];selected=[p for p in items if p.get('executionVenue')=='POOL']
    raw=s.http_json('https://service.leverup.xyz/v1/oracle/quotes/latest',{'blockChain':'MONAD','pairBases':[p['base'] for p in selected]},headers=HEADERS,timeout=5)
    if raw.get('blockChain')!='MONAD':raise ValueError('Wrong venue chain')
    markets=[]
    for p in selected:
        ident=p['base'].lower();v=raw.get('quotes',{}).get(ident,{})
        try:price=positive(int(v['price'])/10**18) if v.get('price') else None;published=int(v.get('publishTime',0))
        except (ValueError,TypeError,OverflowError):price=None;published=0
        stale=not price or bool(v.get('stale',True)) or not s.now()-60<=published<=s.now()+5
        markets.append({'id':'leverup:'+ident,'venue':'LeverUp','symbol':p['pairName'],'baseSymbol':p['symbol'],'pairBase':ident,'category':p['pairType'],'open':p['status']=='AVAILABLE' and not stale,'mark':price,'last':None,'priceSource':'LeverUp oracle','observationAt':published,'stale':stale,'volume':positive(p.get('volumeUSD')),'priceDecimals':p['priceDisplayDecimals'],'lotDecimals':10,'execution':'wallet_transactions','sourceURL':'https://app.leverup.xyz/','collateral':'USDC / LVUSD','chainId':143,'isDegenPair':p.get('isDegenPair',False)})
    return {'venue':'LeverUp','markets':markets,'state':'wallet_flow_connected','reason':'USDC open and full-close adapter; funded execution acceptance pending','total':len(markets),'excludedCrossChain':len(items)-len(selected),'sourceURL':'https://developer-docs.leverup.xyz/','observedAt':s.now()}

def pingu():
    from eth_abi import decode
    block=s.rpc('eth_blockNumber',[])
    if time.time()-CONFIG_AT.get('Pingu',0)>600:
        ok,raw=u.batch([u.call(PINGU,'getMarketList()')],block)[0]
        if not ok:raise ValueError('Market list unavailable')
        names=list(decode(['string[]'],raw)[0])
        if not names or len(names)>500:raise ValueError('Invalid market list')
        outputs=u.batch([u.call(PINGU,'getMany(string[])',[names],['string[]'])],block)
        abi='(string,string,address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,bytes32,bool,bool,uint256,uint256)[]'
        if not outputs[0][0]:raise ValueError('Market config unavailable')
        configs=decode([abi],outputs[0][1])[0]
        if len(configs)!=len(names):raise ValueError('Market config mismatch')
        CONFIG['Pingu']=[{'name':n,'label':v[0],'category':v[1],'feed':'0x'+v[10].hex(),'reduceOnly':v[12],'maxLeverage':v[3],'feeBps':v[5],'maxPriceAge':v[9]} for n,v in zip(names,configs)]
        CONFIG_AT['Pingu']=time.time()
    configs=CONFIG['Pingu'];feed_ids=list(dict.fromkeys(p['feed'] for p in configs if p['feed']!='0x'+'0'*64))
    import pyth_oracle,pingu as adapter
    try:prices=pyth_oracle.onchain(feed_ids,max_age=KEEP_SECONDS,block=block)
    except Exception:prices={}
    try:health=adapter.health(block)
    except Exception:health={'ready':False,'newOrdersPaused':None,'processingPaused':None,'keeperRecent':None}
    markets=[]
    for p in configs:
        value=prices.get(p['feed'],{});symbol=p['name'].replace('-','/');stale=not value.get('price') or s.now()-value.get('time',0)>60;execution_stale=not value.get('price') or s.now()-value.get('time',0)>p['maxPriceAge']
        markets.append({'id':'pingu:'+p['name'],'venue':'Pingu','symbol':symbol,'baseSymbol':p['name'].split('-')[0],'name':p['label'],'category':p['category'],'open':health['ready'] and not p['reduceOnly'] and not execution_stale,'reduceOnly':p['reduceOnly'],'mark':value.get('price'),'last':None,'observationAt':value.get('time',0),'stale':stale,'executionPriceStale':execution_stale,'priceSource':'Pyth on Monad','maxLeverage':p['maxLeverage'],'feeBps':p['feeBps'],'priceDecimals':6,'execution':'wallet_transactions' if health['ready'] else 'keeper_unverified','orderAdapter':True,'executionBlocker':None if health['ready'] else 'No recent approved keeper fill verified','sourceURL':'https://pingu.exchange/','chainId':143,'feedId':p['feed'],'blockNumber':int(block,16)})
    return {'venue':'Pingu','markets':markets,'state':'wallet_flow_connected' if health['ready'] else 'keeper_unverified','reason':None if health['ready'] else 'Order/cancel/full-close adapter connected; new requests wait for verified keeper activity','health':health,'total':len(markets),'observedAt':s.now()}

def hermes(ids):
    global HERMES_BLOCKED_UNTIL
    if not ids:return {}
    key=os.environ.get('RALLY_PYTH_API_KEY','')
    if time.time()<HERMES_BLOCKED_UNTIL and not key:raise s.Problem('Pyth API access required',503,'oracle_access_required')
    try:
        raw=s.http_json('https://hermes.pyth.network/v2/updates/price/latest?'+urlencode([('ids[]',i.removeprefix('0x')) for i in ids]),headers={'User-Agent':'Rally/1.0',**({'Authorization':'Bearer '+key} if key else {})},timeout=6)
    except s.Problem as error:
        if error.code=='provider_401':HERMES_BLOCKED_UNTIL=time.time()+3600
        raise
    result={}
    for v in raw.get('parsed',[]):
        key='0x'+v['id'].removeprefix('0x').lower();p=v['price'];t=int(p['publish_time']);price=positive(int(p['price'])*10**int(p['expo']))
        if key in ids and s.now()-60<=t<=s.now()+10 and price:result[key]={'price':price,'time':t}
    return result

def drake():
    import drake as adapter,pyth_oracle
    raw=adapter.CONFIG;items=raw['instruments']
    try:prices=pyth_oracle.onchain([p['pythFeedId'].lower() for p in items.values()],max_age=KEEP_SECONDS)
    except Exception:prices={}
    access={}
    if os.environ.get('RALLY_PYTH_API_KEY','').strip():
        try:access=hermes([p['pythFeedId'].lower() for p in items.values()])
        except Exception:pass
    ready=bool(access)
    markets=[]
    for key,p in items.items():
        v=prices.get(p['pythFeedId'].lower(),{});available=p['pythFeedId'].lower() in access
        markets.append({'id':'drake:'+key,'venue':'Drake','symbol':p['symbol'],'baseSymbol':p['symbol'].split('/')[0],'open':available,'mark':v.get('price'),'last':None,'observationAt':v.get('time',0),'stale':not v.get('price') or s.now()-v.get('time',0)>60,'priceSource':'Pyth on Monad','priceDecimals':6,'lotDecimals':4,'collateral':'AUSD','execution':'wallet_transactions' if available else 'oracle_access_required','orderAdapter':True,'executionBlocker':None if available else 'Signed Pyth updates require provider access','sourceURL':'https://drake.exchange/','chainId':143,'feedId':p['pythFeedId']})
    return {'venue':'Drake','markets':markets,'state':'wallet_flow_connected' if ready else 'oracle_access_required','reason':None if ready else 'Portfolio/order/cancel/full-close adapter connected; signed Pyth updates require provider access','total':len(markets),'observedAt':s.now()}

def display_market(m):
    """A retained price keeps its actual timestamp and never authorizes an order."""
    m=dict(m)
    try:stamp=int(m.get('observationAt',0))
    except (TypeError,ValueError):stamp=0
    age=s.now()-stamp;valid=positive(m.get('mark')) and -5<=age<=KEEP_SECONDS
    m['mark']=positive(m.get('mark')) if valid else None
    m['stale']=bool(m.get('stale')) or not valid or age>60
    m['priceAgeSeconds']=max(0,age) if stamp else None
    m['lastKnown']=bool(m['mark']) and m['stale']
    if not valid:m['last']=None
    if m['stale']:m['open']=False
    return m

def merge_markets(current,previous):
    old={m['id']:m for m in previous};result=[]
    for m in current:
        m=dict(m);prior=old.get(m['id'],{})
        # Matching venue ID plus feed/pair identity, never a symbol match.
        same=all(m.get(k)==prior.get(k) for k in ('venue','chainId','feedId','pairBase','symbol'))
        reference=display_market(prior)
        if same and reference.get('mark') and (not positive(m.get('mark')) or m.get('observationAt',0)<reference.get('observationAt',0) or m.get('observationAt',0)>s.now()+5):
            for field in ('mark','last','observationAt','priceSource','blockNumber'):m[field]=reference.get(field)
            m.update(stale=True,open=False)
        result.append(display_market(m))
    return result

def save_snapshot(name,value):
    # Public market snapshots only; never wallet material or signed payloads.
    with u.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS market_snapshots(venue TEXT PRIMARY KEY,info TEXT NOT NULL)')
        c.execute('INSERT OR REPLACE INTO market_snapshots VALUES(?,?)',(name,s.dump(value)))

def restore():
    with u.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS market_snapshots(venue TEXT PRIMARY KEY,info TEXT NOT NULL)')
        rows=c.execute('SELECT venue,info FROM market_snapshots').fetchall()
    with LOCK:
        for row in rows:
            if row['venue'] not in {'LeverUp','Pingu','Drake','Perpl'}:continue
            try:value=json.loads(row['info'])
            except (ValueError,TypeError):continue
            value['markets']=[display_market(dict(m,stale=True,open=False)) for m in value.get('markets',[])];value['state']='warming'
            CACHE[row['venue']]=value

def read_venue(name,fn):
    started=time.monotonic()
    with LOCK:previous=CACHE.get(name,{})
    try:
        value=fn();value['markets']=merge_markets(value['markets'],previous.get('markets',[]))
        value.update(lastSuccessAt=s.now(),lastAttemptAt=s.now(),consecutiveFailures=0,durationSeconds=round(time.monotonic()-started,3))
        success=True
    except Exception:
        value={**previous,'venue':name,'state':'prices_delayed','reason':'Public market reader delayed; last observations retained','markets':[display_market(dict(m,stale=True,open=False)) for m in previous.get('markets',[])],'lastAttemptAt':s.now(),'consecutiveFailures':previous.get('consecutiveFailures',0)+1,'durationSeconds':round(time.monotonic()-started,3)}
        success=False
    with LOCK:CACHE[name]=value
    if success:
        try:save_snapshot(name,value)
        except Exception:pass
    return success

def refresh():
    if not BUSY.acquire(False):return
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda x:read_venue(*x),[('LeverUp',leverup),('Pingu',pingu),('Drake',drake)]))
    finally:BUSY.release()

def perpl():
    context=s.GATEWAY.perpl_markets(cached_only=True)
    return {'venue':'Perpl','markets':[dict(m,venue='Perpl',baseSymbol=m['symbol'],execution='wallet_transactions',priceSource='Perpl mark',stale=s.now()-context['fetchedAt']>60,observationAt=context['fetchedAt'],chainId=143) for m in context['markets']],'observedAt':context['fetchedAt'],'state':'wallet_flow_connected','total':len(context['markets'])}

def catalog():
    try:
        # Public list reads never wait for the provider or its refresh lock.
        # Financial builders continue to require a fresh Perpl context.
        value=perpl();stale=s.now()-value['observedAt']>60
        markets=[display_market(m) for m in value['markets']]
        sources=[{'venue':'Perpl','state':'prices_delayed' if stale else 'wallet_flow_connected','total':len(markets),'observedAt':value['observedAt']}]
    except Exception:
        with LOCK:value=CACHE.get('Perpl',{})
        markets=[display_market(dict(m,stale=True,open=False)) for m in value.get('markets',[])];sources=[{'venue':'Perpl','state':'prices_delayed' if markets else 'unavailable','reason':'Waiting for provider context','observedAt':value.get('observedAt',0)}]
    with LOCK:values=[v for k,v in CACHE.items() if k!='Perpl']
    for value in values:
        stale=s.now()-value.get('observedAt',0)>60
        rows=[display_market(dict(m,stale=True,open=False) if stale else m) for m in value.get('markets',[])];markets.extend(rows)
        sources.append({**{k:v for k,v in value.items() if k!='markets'},'freshPrices':sum(bool(m['mark']) and not m['stale'] for m in rows),'lastKnownPrices':sum(m['lastKnown'] for m in rows)})
    return {'markets':markets,'sources':sources+BLOCKERS,'fetchedAt':s.now(),'priceUpdatedAt':max((m.get('observationAt',0) for m in markets if m.get('mark')),default=0),'freshPrices':sum(bool(m['mark']) and not m['stale'] for m in markets),'lastKnownPrices':sum(m['lastKnown'] for m in markets),'venue':'Monad','chainId':143,'execution':'venue_specific','financialTransactions':0}

def background():
    try:restore()
    except Exception:pass
    def loop(name,fn):
        failures=0
        while True:
            started=time.monotonic()
            try:success=read_venue(name,fn)
            except Exception:success=False
            failures=0 if success else min(failures+1,3)
            time.sleep(max(1,15*2**failures-(time.monotonic()-started)))
    for name,fn in [('LeverUp',leverup),('Pingu',pingu),('Drake',drake)]:
        threading.Thread(target=loop,args=(name,fn),daemon=True,name='perp-'+name.lower()).start()
    # Parent stays alive; one venue's retries cannot delay the other workers.
    while True:
        time.sleep(30)
