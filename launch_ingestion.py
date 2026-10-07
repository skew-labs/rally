"""Resumable public launch discovery. Never constructs or submits transactions.

Provider pages enqueue candidates; same-block Multicall reads establish identity
and lifecycle before publication. Latest launches do not wait for history scans.
"""
import json, threading, time
from decimal import Decimal,localcontext
from urllib.parse import urlencode
from eth_abi import decode
import service as s
import nadfun as n
import market_universe as u

VISIBLE={};URGENT=set();VISIBLE_EVENT=threading.Event();LOCK=threading.Lock();VERIFY_LOCK=threading.Lock()

def initialize():
    with s.connection() as db:db.executescript('''
    CREATE TABLE IF NOT EXISTS launch_sources(name TEXT PRIMARY KEY,info TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS launch_candidates(address TEXT PRIMARY KEY,payload TEXT,
      observed INTEGER,priority INTEGER,attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,error TEXT);
    CREATE INDEX IF NOT EXISTS launch_queue ON launch_candidates(next_attempt,priority,observed);
    CREATE INDEX IF NOT EXISTS nad_created ON nad_tokens(json_extract(info,'$.created'),address);
    CREATE TABLE IF NOT EXISTS launch_event_pending(address TEXT PRIMARY KEY,next_attempt INTEGER,attempts INTEGER);
    ''')

def status(name,**fields):
    with s.connection() as db:
        row=db.execute('SELECT info FROM launch_sources WHERE name=?',(name,)).fetchone()
        value=json.loads(row['info']) if row else {};value.update(fields)
        if fields.get('state') in {'live','indexing','complete'}:value.pop('error',None)
        db.execute('INSERT OR REPLACE INTO launch_sources VALUES(?,?)',(name,s.dump(value)))
    return value

def health():
    sources={r['name']:json.loads(r['info']) for r in s.rows('SELECT * FROM launch_sources')}
    counts=s.one('SELECT count(*) AS queued,sum(attempts>0) AS retrying FROM launch_candidates')
    return {'sources':sources,'queued':counts['queued'],'retrying':counts['retrying'] or 0,
            'verified':s.one('SELECT count(*) AS n FROM nad_tokens')['n']}

def viewed(tokens):
    with LOCK:
        for token in tokens:
            VISIBLE.pop(token['id'],None);VISIBLE[token['id']]=s.now()
            if s.now()-token.get('referenceAt',0)>30:URGENT.add(token['id'])
        while len(VISIBLE)>200:VISIBLE.pop(next(iter(VISIBLE)))
        URGENT.intersection_update(VISIBLE)
        if URGENT:VISIBLE_EVENT.set()

def publish_reference(candidate,observed):
    ti=candidate.get('token_info',{});market=candidate.get('market_info',{})
    try:token=n.address(ti.get('token_id'))
    except s.Problem:return
    known=s.one('SELECT version,info FROM nad_tokens WHERE address=?',(token,))
    if not known or str(market.get('token_id','')).lower()!=token:return
    info=json.loads(known['info'])
    if [ti.get('name'),ti.get('symbol'),str(ti.get('version','')).lower()]!=[info['name'],info['symbol'],known['version']]:return
    value={'name':info['name'],'symbol':info['symbol'],'version':known['version'],
           'referenceAt':observed,**n.market_numbers(market)}
    with n.MARKET_REFERENCE_LOCK:
        if observed>=n.MARKET_REFERENCES.get(token,{}).get('referenceAt',0):n.MARKET_REFERENCES[token]=value
    # Update reference fields atomically; never overwrite a concurrent lifecycle
    # observation or attach a candidate's price to a changed token identity.
    fields={k:v for k,v in value.items() if k not in ['name','symbol','version']}
    params=[]
    for key,value in fields.items():params.extend(['$.'+key,value])
    s.write('UPDATE nad_tokens SET info=json_set(info,'+','.join('?' for _ in params)+') WHERE address=? AND version=? AND json_extract(info,\'$.name\')=? AND json_extract(info,\'$.symbol\')=? AND coalesce(json_extract(info,\'$.referenceAt\'),0)<=?',(*params,token,known['version'],info['name'],info['symbol'],observed))

def enqueue(candidates,priority=0):
    observed=s.now();accepted=0
    with s.connection() as db:
        for candidate in candidates[:100]:
            try:
                ti=candidate['token_info'];token=n.address(ti.get('token_id'))
                if str(ti.get('version','')).lower() not in n.FILES:continue
                if not isinstance(ti.get('name'),str) or len(ti['name'])>120 or not isinstance(ti.get('symbol'),str) or len(ti['symbol'])>32:continue
                payload=s.dump(candidate)
                if len(payload)>24000:continue
            except (s.Problem,KeyError,TypeError,ValueError):continue
            prior=db.execute('SELECT observed,info FROM nad_tokens WHERE address=?',(token,)).fetchone()
            changed=False
            if prior:
                known=json.loads(prior['info'])
                image=None
                if ti.get('image_uri') and not ti.get('is_nsfw'):
                    try:image=n.storage_url(ti['image_uri'])
                    except (s.Problem,ValueError):pass
                changed=any(known.get(key)!=value for key,value in [('name',ti['name']),('symbol',ti['symbol']),('logoURI',image),('description',str(ti.get('description') or '')[:500]),('website',ti.get('website')),('twitter',ti.get('twitter')),('telegram',ti.get('telegram'))])
            # A history pass need not reverify an already indexed identity.
            if prior and not changed and (priority==0 or observed-prior['observed']<90):continue
            db.execute('''INSERT INTO launch_candidates(address,payload,observed,priority) VALUES(?,?,?,?)
              ON CONFLICT(address) DO UPDATE SET payload=excluded.payload,observed=excluded.observed,
              priority=max(priority,excluded.priority)''',(token,payload,observed,priority));accepted+=1
    for candidate in candidates[:100]:publish_reference(candidate,observed)
    return accepted

def page(order='creation_time',page=1,direction='DESC',priority=0):
    data=n.api('/order/'+order+'?'+urlencode({'page':page,'limit':100,'is_nsfw':'false','direction':direction}))
    tokens=data.get('tokens');total=data.get('total_count')
    if not isinstance(tokens,list) or len(tokens)>100 or isinstance(total,bool) or not isinstance(total,int) or not 0<=total<=1_000_000:raise s.Problem('Invalid launch page',502,'launch_page_invalid')
    # A missing interior page must never advance the durable history cursor.
    if len(tokens)!=max(0,min(100,total-(page-1)*100)):raise s.Problem('Incomplete launch page',502,'launch_page_incomplete')
    enqueue(tokens,priority)
    return data

def history_once():
    row=s.one("SELECT info FROM launch_sources WHERE name='history'")
    old=json.loads(row['info']) if row else {};next_page=old.get('nextPage',1)
    if old.get('state')=='complete' and s.now()-old.get('completedAt',0)<21600:return False
    if old.get('state')=='complete':next_page=1
    try:
        data=page(page=next_page,direction='ASC');total=data['total_count']
        complete=next_page*100>=total
        status('history',state='complete' if complete else 'indexing',nextPage=next_page+1,
               pagesRead=next_page,providerTotal=total,lastSuccessAt=s.now(),lastAttemptAt=s.now(),
               **({'completedAt':s.now()} if complete else {}))
        return True
    except Exception as e:
        status('history',state='delayed',nextPage=next_page,lastAttemptAt=s.now(),error=getattr(e,'code','launch_page_unavailable'))
        return False

def event_candidate_once():
    row=s.one('''SELECT lower(json_extract(e.fields,'$.token')) AS address FROM nad_events e
      LEFT JOIN nad_tokens t ON t.address=lower(json_extract(e.fields,'$.token'))
      LEFT JOIN launch_candidates q ON q.address=lower(json_extract(e.fields,'$.token'))
      LEFT JOIN launch_event_pending p ON p.address=lower(json_extract(e.fields,'$.token'))
      WHERE e.name IN ('Create','CurveCreate') AND t.address IS NULL AND q.address IS NULL
      AND coalesce(p.next_attempt,0)<=? ORDER BY e.block DESC LIMIT 1''',(s.now(),))
    if not row:return
    token=n.address(row['address'])
    try:
        enqueue([n.api('/token/'+token)],priority=2)
        s.write('DELETE FROM launch_event_pending WHERE address=?',(token,))
    except Exception:
        prior=s.one('SELECT attempts FROM launch_event_pending WHERE address=?',(token,))
        attempts=(prior['attempts'] if prior else 0)+1
        s.write('INSERT OR REPLACE INTO launch_event_pending VALUES(?,?,?)',(token,s.now()+min(3600,30*2**min(attempts,7)),attempts))

def many_state(candidates,block):
    """All identity and lifecycle assertions of nadfun.state, batched read-only."""
    calls=[];specs=[];items=[]
    def add(token,key,version=None,label=None,name=None,args=(),out=None):
        if label:
            f=n.fn(version,label,name);target=n.contract(version,label);data=bytes.fromhex(n.calldata(version,label,name,args)[2:]);outputs=f['outputs']
        else:
            target=token;data=u.call(token,name)[2];outputs=[{'name':'','type':out}]
        calls.append((target,True,data));specs.append((token,key,outputs))
    for candidate in candidates:
        ti=candidate['token_info'];token=n.address(ti['token_id']);version=str(ti['version']).lower();items.append((token,version,candidate))
        for name,out in [('name()','string'),('symbol()','string'),('decimals()','uint8'),('totalSupply()','uint256')]:add(token,name,name=name,out=out)
        if version=='v2':
            add(token,'curve',version,'curve','getCurve',[token]);add(token,'graduated',version,'router','isGraduated',[token]);add(token,'penalty',version,'curve','getSnipingPenalty',[token])
        else:
            add(token,'reserves',version,'curve','curves',[token])
            for key,label,name in [('created','curve','createdAt'),('graduated','curve','isGraduated'),('lensGraduated','lens','isGraduated'),('locked','curve','isLocked'),('progress','lens','getProgress')]:add(token,key,version,label,name,[token])
    values=u.batch(calls,block);fields={};bad=set()
    for (token,key,outs),(ok,raw) in zip(specs,values):
        try:
            if not ok:raise ValueError()
            value=decode([n.v.typ(o) for o in outs],raw)
            fields.setdefault(token,{})[key]=n.v.named(outs[0],value[0]) if len(outs)==1 else {o['name']:n.v.named(o,x) for o,x in zip(outs,value)}
        except Exception:bad.add(token)
    extra=[];extra_tokens=[]
    for token,version,_ in items:
        if version!='v2' or token in bad:continue
        curve=fields[token]['curve']
        extra.extend([(n.contract(version,'factory'),True,bytes.fromhex(n.calldata(version,'factory','getPair',[token,curve['quoteToken']])[2:])),
                      (n.contract(version,'fees'),True,bytes.fromhex(n.calldata(version,'fees','getFeeConfig',[curve['pair']])[2:]))]);extra_tokens.append(token)
    if extra:
        result=u.batch(extra,block)
        for i,token in enumerate(extra_tokens):
            try:
                pair,fee=result[i*2:i*2+2]
                if not pair[0] or not fee[0]:raise ValueError()
                fields[token]['pair']=decode(['address'],pair[1])[0]
                f=n.fn('v2','fees','getFeeConfig')['outputs'][0]
                fields[token]['fee']=n.v.named(f,decode([n.v.typ(f)],fee[1])[0])
            except Exception:bad.add(token)
    output={}
    for token,version,candidate in items:
        if token in bad:continue
        ti=candidate['token_info'];f=fields[token]
        try:
            if f['name()']!=ti['name'] or f['symbol()']!=ti['symbol'] or f['decimals()']!=18:continue
            graduated=f['graduated']
            if version=='v2':
                curve=f['curve'];fee=f['fee'];quote=curve['quoteToken']
                if curve['token']!=token or not curve['createdAtBlock'] or curve['creator']==s.ZERO or graduated!=curve['graduated'] or f['pair']==s.ZERO or f['pair']!=curve['pair'] or fee['baseToken']!=token or fee['quoteToken']!=quote or str((ti.get('creator') or {}).get('account_id','')).lower()!=curve['creator']:continue
                denominator=curve['initialTokenReserve']-curve['minTokenReserve']
                progress=10000 if graduated else max(0,min(10000,(curve['initialTokenReserve']-curve['virtualTokenReserve'])*10000//denominator)) if denominator>0 else 0
                live={'pair':f['pair'],'quoteToken':quote,'nativeSupported':quote==n.WMON,'tradeSupported':quote in {n.WMON,n.LVMON},'quoteSymbol':'MON' if quote==n.WMON else 'LVMon' if quote==n.LVMON else 'Unknown quote','creator':curve['creator'],'createdBlock':curve['createdAtBlock'],'router':n.contract(version,'router'),'progressBps':progress,'locked':False,'creatorFeeBps':fee['creatorFeeRate'],'protocolFeeBps':fee['dexProtocolFeeRate'] if graduated else fee['curveProtocolFeeRate'],'snipingPenaltyBps':0 if graduated else f['penalty']}
            else:
                if not f['created'] and not graduated or graduated!=f['lensGraduated']:continue
                live={'quoteToken':n.WMON,'nativeSupported':True,'tradeSupported':True,'quoteSymbol':'MON','router':n.contract(version,'dex' if graduated else 'router'),'progressBps':10000 if graduated else min(10000,f['progress']),'locked':f['locked'] and not graduated,'creatorFeeBps':None,'protocolFeeBps':None,'snipingPenaltyBps':None}
            output[token]={'version':version,'phase':'dex' if graduated else 'curve','graduated':graduated,'block':int(block,16),'totalSupply':s.units(f['totalSupply()'],18),**live}
            if not graduated:
                reserve=f['curve']['virtualQuoteReserve'] if version=='v2' else f['reserves']['virtualMonReserve']
                tokens=f['curve']['virtualTokenReserve'] if version=='v2' else f['reserves']['virtualTokenReserve']
                anchor=s.GATEWAY.prices.get(live['quoteToken'],{})
                stamp=anchor.get('fetchedAt',0)
                if reserve>0 and tokens>0 and 0<=s.now()-stamp<=120 and float(anchor.get('price') or 0)>0:
                    with localcontext() as context:
                        context.prec=96
                        price=Decimal(reserve)/Decimal(tokens)*Decimal(str(anchor['price']))
                        supply=Decimal(f['totalSupply()'])/10**18
                    output[token].update(price=str(price),totalSupply=str(supply),marketCap=str(price*supply),referenceAt=stamp,
                        marketCapBasis='total_supply',priceSource='On-chain bonding-curve reserve reference',priceBlock=int(block,16))
        except (KeyError,TypeError,ValueError):continue
    return output

def store(candidate,live,observed):
    ti=candidate['token_info'];token=n.address(ti['token_id']);image=None
    if not ti.get('is_nsfw') and ti.get('image_uri'):
        try:image=n.storage_url(ti['image_uri'])
        except s.Problem:pass
    market=candidate.get('market_info',{})
    metrics=n.market_numbers(market) if str(market.get('token_id','')).lower()==token else {}
    info={'id':token,'address':token,'chainId':143,'decimals':18,'name':ti['name'],'symbol':ti['symbol'],
          'logoURI':image,'venue':'nad.fun','nadfun':True,'created':int(ti.get('created_at') or 0),'metadataVerified':True,
          'creatorSource':'nad.fun contract' if live['version']=='v2' else 'nad.fun API',
          'creator':(ti.get('creator') or {}).get('account_id'),'description':str(ti.get('description') or '')[:500],
          'website':ti.get('website'),'twitter':ti.get('twitter'),'telegram':ti.get('telegram'),
          'holders':market.get('holder_count'),'referenceAt':observed,'lifecycleAt':s.now(),**metrics,**live}
    # Never regress a price observation that arrived while verification ran.
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        prior=db.execute('SELECT info FROM nad_tokens WHERE address=?',(token,)).fetchone()
        if prior:
            old=json.loads(prior['info'])
            if old.get('block',0)>live.get('block',0):
                info.update({k:old[k] for k in ['block','phase','graduated','progressBps','locked','pair','quoteToken','nativeSupported','tradeSupported','quoteSymbol','creator','createdBlock','router','creatorFeeBps','protocolFeeBps','snipingPenaltyBps','lifecycleAt'] if k in old})
            if old.get('referenceAt',0)>info.get('referenceAt',0):
                info.update({k:old.get(k) for k in ['referenceAt','price','marketCap','totalSupply','marketCapBasis','priceSource']})
        db.execute('INSERT INTO nad_tokens VALUES(?,?,?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info,observed=excluded.observed',(token,live['version'],s.dump(info),s.now()))
        db.execute('DELETE FROM launch_candidates WHERE address=? AND observed<=?',(token,observed))
    if live['graduated']:
        # Graduations immediately enter the shared Spot identity namespace.
        with u.db() as db:db.execute('INSERT INTO assets(address,info) VALUES(?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info',(token,s.dump(info)))
        with s.LOCK:s.GATEWAY.token_map[token]=info
    return info

def verify_once(limit=64):
    if not VERIFY_LOCK.acquire(False):return 0
    try:
        pending=s.rows('SELECT * FROM launch_candidates WHERE next_attempt<=? ORDER BY priority DESC,observed ASC LIMIT ?',(s.now(),limit))
        if not pending:return 0
        try:live=many_state([json.loads(r['payload']) for r in pending],s.rpc('eth_blockNumber',[]))
        except Exception:live={}
        count=0
        for row in pending:
            try:
                if row['address'] not in live:raise ValueError()
                store(json.loads(row['payload']),live[row['address']],row['observed']);count+=1
            except Exception:
                attempts=row['attempts']+1
                s.write('UPDATE launch_candidates SET attempts=?,next_attempt=?,error=? WHERE address=? AND observed=?',
                        (attempts,s.now()+min(3600,30*2**min(attempts,7)),'identity_or_state_unavailable',row['address'],row['observed']))
        status('verification',lastAttemptAt=s.now(),state='partial' if count<len(pending) else 'live',verifiedBatch=count,batchSize=len(pending),**({'lastSuccessAt':s.now()} if count else {}))
        return count
    finally:VERIFY_LOCK.release()

def refresh_visible(limit=32):
    with LOCK:
        hot=[a for a,stamp in VISIBLE.items() if s.now()-stamp<120]
        urgent=[a for a in hot if a in URGENT]
    if urgent:hot=urgent
    if not hot:return
    rows=s.rows('SELECT info FROM nad_tokens WHERE address IN ('+','.join('?' for _ in hot)+') ORDER BY observed LIMIT ?',(*hot,limit))
    candidates=[]
    for row in rows:
        t=json.loads(row['info'])
        candidates.append({'token_info':{'token_id':t['id'],'name':t['name'],'symbol':t['symbol'],'version':t['version'],
          'creator':{'account_id':t.get('creator')},'created_at':t.get('created'),'image_uri':t.get('logoURI'),
          'description':t.get('description'),'website':t.get('website'),'twitter':t.get('twitter'),'telegram':t.get('telegram')},
          'market_info':{'token_id':t['id'],'price_usd':t.get('price'),'holder_count':t.get('holders'),'total_supply':str(int(Decimal(t.get('totalSupply') or 0)*10**18))},'_referenceAt':t.get('referenceAt',0)})
    live=many_state(candidates,s.rpc('eth_blockNumber',[]))
    graduated=[a for a,value in live.items() if value['graduated']]
    prices=u.prices(graduated) if graduated else {}
    for candidate in candidates:
        token=candidate['token_info']['token_id'];value=live.get(token)
        if not value:continue
        price=prices.get(token)
        if price:
            supply=Decimal(value['totalSupply'])
            value.update(price=str(price['price']),marketCap=str(Decimal(str(price['price']))*supply),
                         totalSupply=str(supply),referenceAt=price['fetchedAt'],priceSource=price['priceSource'],marketCapBasis='total_supply')
        store(candidate,value,candidate['_referenceAt'])
        with LOCK:URGENT.discard(token)
    status('visible',state='live' if len(live)==len(candidates) else 'partial',lastAttemptAt=s.now(),refreshed=len(live),lastSuccessAt=s.now() if live else 0)

def loops():
    initialize()
    def events():
        while True:n.sync_once();time.sleep(10)
    def verify():
        while True:
            try:verify_once()
            except Exception:pass
            time.sleep(2)
    def visible():
        while True:
            VISIBLE_EVENT.clear()
            try:refresh_visible()
            except Exception:pass
            VISIBLE_EVENT.wait(15)
    threading.Thread(target=events,daemon=True,name='launch-finalized-events').start()
    threading.Thread(target=verify,daemon=True,name='launch-identity-verification').start()
    threading.Thread(target=visible,daemon=True,name='launch-visible-prices').start()
    latest_at=cap_at=event_at=0
    while True:
        try:
            if time.monotonic()-latest_at>=30:
                try:
                    result=page(priority=2);latest_at=time.monotonic()
                    status('latest',state='live',providerTotal=result['total_count'],lastSuccessAt=s.now(),lastAttemptAt=s.now())
                except Exception as e:
                    latest_at=time.monotonic();status('latest',state='delayed',lastAttemptAt=s.now(),error=getattr(e,'code','provider_unavailable'))
            if time.monotonic()-cap_at>=90:
                try:page(order='market_cap',priority=1);status('marketCap',state='live',lastSuccessAt=s.now())
                except Exception:status('marketCap',state='delayed',lastAttemptAt=s.now())
                cap_at=time.monotonic()
            if time.monotonic()-event_at>=30:
                event_candidate_once();event_at=time.monotonic()
            history_once()
            with LOCK:
                hot=[a for a,stamp in VISIBLE.items() if s.now()-stamp<120]
            # One visible token per pass, selected by oldest lifecycle snapshot;
            # rate limiting is shared with history, latest, charts and launches.
            if hot:
                row=s.one('SELECT address,observed FROM nad_tokens WHERE address IN ('+','.join('?' for _ in hot)+') ORDER BY observed LIMIT 1',hot)
                if row and s.now()-row['observed']>120:
                    try:enqueue([n.api('/token/'+row['address'])],priority=3)
                    except Exception:pass
        except Exception:pass
        time.sleep(1)
