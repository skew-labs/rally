"""Persistent Monad discovery. Catalogs never imply an executable quote."""
import json, math, re, sqlite3, threading, time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import urlencode
import service as s

FACTORIES={'Uniswap V2':'0x182a927119d56008d921126764bf884221b10f59',
 'PancakeSwap V2':'0x02a84c1b3bbd7401a5f7fa98a384ebc70bb5749e',
 'LFJ V1':'0xe32d45c2b1c17a0fe0de76f1ebfa7c44b7810034',
 'Purps V2':'0xafe4d3eb898591ace6285176b26f0f5beb894447',
 'OctoSwap V1':'0xce104732685b9d7b2f07a09d828f6b19786cda32'}
DB=s.STATE/'market-universe.sqlite3';LOCK=threading.RLock();READY=False
PRICE_CURSOR=0;POOL_CURSOR=0;SEARCH={};REFRESH_LOCK=threading.Lock();QUERY_SLOTS=threading.BoundedSemaphore(2);PAGES={}
DEX_SLOTS=threading.BoundedSemaphore(2);DEX_RATE_LOCK=threading.Lock();DEX_NEXT=0;DEX_RETRY_AT=0
VIEWED={}

def priority_ids():
    with LOCK:
        for a in list(VIEWED):
            if s.now()-VIEWED[a]>300:VIEWED.pop(a,None)
        return list(VIEWED)

def references(value):
    """Cached exact-identity refresh for visible rows. Never blocks on a provider."""
    ids=list(dict.fromkeys(str(value).split(',')))
    if len(ids)>60 or any(a!='MON' and not re.fullmatch('0x[0-9a-f]{40}',a) for a in ids):raise s.Problem('Invalid asset references')
    tokens=[]
    with s.LOCK:
        for a in ids:
            identity=s.GATEWAY.token_map.get(a)
            if not identity:continue
            price=s.GATEWAY.prices.get(a,{})
            stamp=price.get('fetchedAt',0);age=s.now()-stamp
            tokens.append({**identity,**price,'price':price.get('price') if -5<=age<=900 else None,'stale':not 0<=age<=120,'priceAgeSeconds':max(0,age) if stamp else None})
    with LOCK:
        for a in ids:
            if a in s.GATEWAY.token_map:
                VIEWED.pop(a,None);VIEWED[a]=s.now()
        while len(VIEWED)>256:VIEWED.pop(next(iter(VIEWED)))
    return {'tokens':tokens,'fetchedAt':s.now(),'priceUpdatedAt':max((t.get('fetchedAt',0) for t in tokens if t.get('price')),default=0),'financialTransactions':0}

@lru_cache(maxsize=40000)
def decoded_metadata(raw):
    # Only immutable identity metadata is retained; prices are read each pass.
    return json.loads(raw)

def db():
    global READY
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row
    with LOCK:
        if not READY:
            c.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS pools(address TEXT PRIMARY KEY,venue TEXT,token0 TEXT,token1 TEXT);
            CREATE TABLE IF NOT EXISTS assets(address TEXT PRIMARY KEY,info TEXT,price TEXT,updated INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sources(name TEXT PRIMARY KEY,info TEXT);
            ''');READY=True
    return c

def source(name,**values):
    with db() as c:
        row=c.execute('SELECT info FROM sources WHERE name=?',(name,)).fetchone()
        value=json.loads(row['info']) if row else {};value.update(values)
        c.execute('INSERT OR REPLACE INTO sources VALUES(?,?)',(name,s.dump(value)))

def delayed(name):
    # A monitoring write must not terminate a long-lived reader.
    try:source(name,state='delayed',lastAttemptAt=s.now())
    except Exception:pass

def batch(calls,block):
    from eth_abi import encode,decode
    from eth_utils import keccak
    data='0x'+keccak(text='aggregate3((address,bool,bytes)[])').hex()[:8]+encode(['(address,bool,bytes)[]'],[calls]).hex()
    raw=s.rpc('eth_call',[{'to':s.MULTICALL,'data':data,'gas':hex(15_000_000)},block])
    result=decode(['(bool,bytes)[]'],bytes.fromhex(raw[2:]))[0]
    if len(result)!=len(calls):raise s.Problem('Discovery response changed',502)
    return result

def call(address,signature,args=(),types=()):
    from eth_utils import keccak
    from eth_abi import encode
    return (address,True,keccak(text=signature)[:4]+encode(list(types),list(args)))

def metadata(addresses,block=None):
    from eth_abi import decode
    block=block or s.rpc('eth_blockNumber',[]);result=[]
    for i in range(0,len(addresses),32):
        part=addresses[i:i+32];values=batch([call(a,f) for a in part for f in ['decimals()','symbol()','name()']],block)
        for j,a in enumerate(part):
            fields=values[j*3:j*3+3]
            try:
                if not all(ok for ok,_ in fields):continue
                decimals=decode(['uint256'],fields[0][1])[0]
                if not 0<=decimals<=36:continue
                def label(raw):
                    value=decode(['string'],raw)[0] if len(raw)!=32 else raw.rstrip(b'\0').decode('utf8')
                    return re.sub(r'[\x00-\x1f\x7f]','',value)
                symbol=label(fields[1][1]);name=label(fields[2][1])
                if not 0<len(symbol)<=32 or not 0<len(name)<=120:continue
                item={'id':a,'address':a,'symbol':symbol,'name':name,'decimals':decimals,'chainId':143,'metadataVerified':True,'metadataBlock':int(block,16)}
                result.append(item)
            except Exception:continue
        with db() as c:
            accepted={x['id'] for x in result}
            for a in part:
                if a not in accepted:c.execute('UPDATE assets SET updated=-1 WHERE address=? AND info IS NULL',(a,))
            for item in [x for x in result if x['id'] in part]:
                old=c.execute('SELECT info FROM assets WHERE address=?',(item['id'],)).fetchone()
                item={**(json.loads(old['info']) if old and old['info'] else {}),**item}
                c.execute('INSERT INTO assets(address,info) VALUES(?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info',(item['id'],s.dump(item)))
                s.GATEWAY.token_map[item['id']]={**s.GATEWAY.token_map.get(item['id'],{}),**item}
    return result

def resolve(address):
    address=str(address).lower()
    if address=='mon' or address==s.ZERO:return s.GATEWAY.token_map['MON']
    if not re.fullmatch('0x[0-9a-f]{40}',address):raise s.Problem('Enter a Monad token address')
    with db() as c:row=c.execute('SELECT info FROM assets WHERE address=?',(address,)).fetchone()
    if row and row['info']:
        item=json.loads(row['info']);s.GATEWAY.token_map[address]={**s.GATEWAY.token_map.get(address,{}),**item};return s.GATEWAY.token_map[address]
    block=s.rpc('eth_blockNumber',[])
    if s.rpc('eth_getCode',[address,block]) in {'0x','0x0'}:raise s.Problem('No token contract on Monad',404)
    items=metadata([address],block)
    if not items:raise s.Problem('Unsupported token metadata',422)
    return items[0]

def restore():
    with db() as c:
        for r in c.execute('SELECT info,price,updated FROM assets WHERE info IS NOT NULL'):
            item=json.loads(r['info']);s.GATEWAY.token_map[item['id']]={**s.GATEWAY.token_map.get(item['id'],{}),**item}
            if r['price']:
                value=json.loads(r['price'])
                with s.LOCK:
                    if value.get('fetchedAt',0)>=s.GATEWAY.prices.get(item['id'],{}).get('fetchedAt',0):s.GATEWAY.prices[item['id']]=value

def index_factories():
    from eth_abi import decode
    block=s.rpc('eth_blockNumber',[])
    for venue,address in FACTORIES.items():
        try:
            code=s.rpc('eth_getCode',[address,block])
            if code in {'0x','0x0'}:source(venue,state='unavailable',error='Factory not deployed');continue
            import hashlib
            codehash=hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()
            with db() as c:r=c.execute('SELECT info FROM sources WHERE name=?',(venue,)).fetchone()
            old=json.loads(r['info']) if r else {}
            if old.get('codeHash') and old['codeHash']!=codehash:raise ValueError('Factory code changed')
            ok,raw=batch([call(address,'allPairsLength()')],block)[0]
            if not ok:raise ValueError('Factory enumeration unavailable')
            count=decode(['uint256'],raw)[0]
            if not 0<=count<=500_000:raise ValueError('Factory count invalid')
            cursor=int(old.get('cursor',0));source(venue,total=count,cursor=cursor,block=int(block,16),factory=address,codeHash=codehash,state='indexing')
            # Each committed cursor is resumable. Partial work is never called complete.
            while cursor<count:
                end=min(cursor+96,count)
                pairs=batch([call(address,'allPairs(uint256)',[i],['uint256']) for i in range(cursor,end)],block)
                if not all(ok and len(v)==32 for ok,v in pairs):raise ValueError('Incomplete pool page')
                addresses=[decode(['address'],v)[0].lower() for _,v in pairs]
                tokens=batch([call(a,f) for a in addresses for f in ['token0()','token1()']],block)
                if not all(ok and len(v)==32 for ok,v in tokens):raise ValueError('Incomplete pool tokens')
                with db() as c:
                    for i,a in enumerate(addresses):
                        t0,t1=[decode(['address'],v)[0].lower() for _,v in tokens[i*2:i*2+2]]
                        c.execute('INSERT OR REPLACE INTO pools VALUES(?,?,?,?)',(a,venue,t0,t1))
                        for t in [t0,t1]:c.execute('INSERT OR IGNORE INTO assets(address) VALUES(?)',(t,))
                cursor=end;source(venue,cursor=cursor,state='complete' if cursor==count else 'indexing',observedAt=s.now())
            source(venue,state='complete',observedAt=s.now())
        except Exception:source(venue,state='partial',error='Factory read unavailable; saved cursor retained',observedAt=s.now())

def enrich(limit=256):
    with db() as c:addresses=[r[0] for r in c.execute('SELECT address FROM assets WHERE info IS NULL AND updated>=0 LIMIT ?',(limit,))]
    if addresses:metadata(addresses)

def token_lists():
    raw=s.http_json('https://raw.githubusercontent.com/monad-crypto/token-list/main/tokenlist-mainnet.json',timeout=8)
    addresses=[]
    for t in raw.get('tokens',[]):
        a=str(t.get('address','')).lower()
        if t.get('chainId')!=143 or not re.fullmatch('0x[0-9a-f]{40}',a) or a==s.ZERO:continue
        addresses.append(a)
        with db() as c:c.execute('INSERT OR IGNORE INTO assets(address) VALUES(?)',(a,))
    metadata(addresses)
    with db() as c:
        for t in raw.get('tokens',[]):
            a=str(t.get('address','')).lower();r=c.execute('SELECT info FROM assets WHERE address=?',(a,)).fetchone()
            if not r or not r['info']:continue
            item=json.loads(r['info'])
            if item['symbol']!=t.get('symbol') or item['decimals']!=t.get('decimals'):continue
            logo=str(t.get('logoURI',''))
            if logo.startswith('https://'):item['logoURI']=logo
            c.execute('UPDATE assets SET info=? WHERE address=?',(s.dump(item),a));s.GATEWAY.token_map[a]={**s.GATEWAY.token_map.get(a,{}),**item}
    source('Monad token list',state='complete',total=len(addresses),observedAt=s.now(),timestamp=raw.get('timestamp'))

def publish_prices(output):
    """Publish each successful batch. Failed/older reads cannot erase prices."""
    accepted={};observed=s.now()
    with s.LOCK:
        for a,v in output.items():
            try:number=float(v['price']);stamp=int(v['fetchedAt'])
            except (KeyError,ValueError,TypeError):continue
            if not math.isfinite(number) or number<=0 or not 0<stamp<=observed+5:continue
            old=s.GATEWAY.prices.get(a,{})
            if old.get('fetchedAt',0)>stamp:continue
            # Preserve the more liquid reference while it is fresh.
            if old.get('pair')!=v.get('pair') and observed-old.get('fetchedAt',0)<120 and old.get('liquidity',0)>v.get('liquidity',0):continue
            accepted[a]=v
        # Persist before exposing the new snapshot, including after restarts.
        with db() as c:
            for a,v in accepted.items():c.execute('UPDATE assets SET price=?,updated=? WHERE address=?',(s.dump(v),v['fetchedAt'],a))
        s.GATEWAY.prices.update(accepted)
        wrapped=s.GATEWAY.prices.get('0x3bd359c1119da7da1d913d1c4d2b7c461115433a')
        if wrapped:s.GATEWAY.prices['MON']=wrapped
        if accepted:s.GATEWAY.prices_at=max(s.GATEWAY.prices_at,max(v['fetchedAt'] for v in accepted.values()))
    return accepted

def dex_batch(part):
    """One shared read budget across discovery, search and priority prices."""
    global DEX_NEXT,DEX_RETRY_AT
    import spot_prices
    with DEX_SLOTS:
        with DEX_RATE_LOCK:
            if time.monotonic()<DEX_RETRY_AT:raise s.Problem('Price provider cooling down',503,'provider_backoff')
            delay=DEX_NEXT-time.monotonic()
            if delay>0:time.sleep(delay)
            DEX_NEXT=time.monotonic()+.3
        try:raw=s.http_json('https://api.dexscreener.com/tokens/v1/monad/'+','.join(part),timeout=4)
        except s.Problem as error:
            if error.code=='provider_429':
                with DEX_RATE_LOCK:DEX_RETRY_AT=time.monotonic()+30
            raise
        if not isinstance(raw,list):raise ValueError('Invalid token price response')
        values=spot_prices.dex_prices(raw,part)
        publish_prices(values)
        return values

def prices(addresses):
    addresses=list(dict.fromkeys(a.lower() for a in addresses if re.fullmatch('0x[0-9a-fA-F]{40}',a)))
    output={};failures=0
    def read(part):
        try:return dex_batch(part),False
        except Exception:return {},True
    with ThreadPoolExecutor(max_workers=2) as pool:
        for values,failed in pool.map(read,[addresses[i:i+25] for i in range(0,len(addresses),25)]):output.update(values);failures+=failed
    source('DexScreener',state='partial' if failures else 'live',lastAttemptAt=s.now(),failedBatches=failures,requested=len(addresses),priced=len(output),**({'lastSuccessAt':s.now()} if output else {}))
    return output

def refresh_prices():
    global PRICE_CURSOR
    if not REFRESH_LOCK.acquire(False):return
    try:
        with db() as c:
            cold=[r[0] for r in c.execute('SELECT address FROM assets WHERE info IS NOT NULL AND (price IS NULL OR updated<?) ORDER BY address LIMIT 75 OFFSET ?',(s.now()-300,PRICE_CURSOR))]
        PRICE_CURSOR=PRICE_CURSOR+75 if len(cold)==75 else 0
        prices(cold)
    finally:REFRESH_LOCK.release()

def search(query):
    q=str(query).strip()[:120]
    if not q:return
    with LOCK:
        if time.monotonic()-SEARCH.get(q,0)<30:return
        SEARCH[q]=time.monotonic()
        if len(SEARCH)>128:SEARCH.pop(next(iter(SEARCH)))
    if not QUERY_SLOTS.acquire(False):raise s.Problem('Search is busy. Try again.',503)
    try:
        if re.fullmatch('0x[0-9a-fA-F]{40}',q):resolve(q);prices([q.lower()]);return
        raw=s.http_json('https://api.dexscreener.com/latest/dex/search?'+urlencode({'q':q}),timeout=5)
        addresses=list(dict.fromkeys(str(p.get('baseToken',{}).get('address','')).lower() for p in raw.get('pairs',[]) if p.get('chainId')=='monad'))
        addresses=[a for a in addresses if re.fullmatch('0x[0-9a-f]{40}',a)]
        if addresses:metadata(addresses[:64]);prices(addresses[:64])
    finally:QUERY_SLOTS.release()

def pool_prices(limit=128,hot_only=False):
    """Read reserve prices for indexed V2 pools, including unlisted tokens.

    A reserve ratio is a pool reference only. Orders always get a fresh router
    quote. Tiny pools are kept in discovery but excluded from live price rows.
    """
    global POOL_CURSOR
    from eth_abi import decode
    from decimal import Decimal,localcontext
    wmon='0x3bd359c1119da7da1d913d1c4d2b7c461115433a'
    quotes={wmon:None,s.USDC:None,'0x00000000efe302beaa2b3e6e1b18d08d69a9012a':None};quote_times={}
    for a in [wmon,s.USDC,'0x00000000efe302beaa2b3e6e1b18d08d69a9012a']:
        value=s.GATEWAY.prices.get(a,{})
        if 0<=s.now()-value.get('fetchedAt',0)<120:quotes[a]=value.get('price');quote_times[a]=value['fetchedAt']
    with db() as c:
        if hot_only:rows=c.execute("SELECT DISTINCT p.* FROM pools p JOIN assets a ON json_extract(a.price,'$.pair')=p.address WHERE a.price IS NOT NULL AND a.updated>? ORDER BY p.address LIMIT 256",(s.now()-86400,)).fetchall()
        else:rows=c.execute('SELECT * FROM pools WHERE token0 IN (?,?,?) OR token1 IN (?,?,?) ORDER BY address LIMIT ? OFFSET ?',(*quotes,*quotes,limit,POOL_CURSOR)).fetchall()
    if not rows:
        if not hot_only:POOL_CURSOR=0
        return
    if not hot_only:POOL_CURSOR=POOL_CURSOR+limit if len(rows)==limit else 0
    block=s.rpc('eth_blockNumber',[]);outputs={}
    for i in range(0,len(rows),128):
        part=rows[i:i+128]
        try:values=batch([call(r['address'],'getReserves()') for r in part],block)
        except Exception:continue
        for r,(ok,raw) in zip(part,values):
            if not ok:continue
            try:r0,r1,_=decode(['uint112','uint112','uint32'],raw)
            except Exception:continue
            if not r0 or not r1:continue
            for a,b,ra,rb in [(r['token0'],r['token1'],r0,r1),(r['token1'],r['token0'],r1,r0)]:
                t=s.GATEWAY.token_map.get(a);counter=s.GATEWAY.token_map.get(b);quote=quotes.get(b)
                if not t or not counter or not quote:continue
                with localcontext() as context:
                    context.prec=96
                    depth=Decimal(rb)/10**counter['decimals']*Decimal(str(quote))
                    price=depth/(Decimal(ra)/10**t['decimals'])
                if depth<25:continue
                price=float(price);liquidity=float(depth*2)
                if not math.isfinite(price) or price<=0 or not math.isfinite(liquidity):continue
                old=outputs.get(a,s.GATEWAY.prices.get(a,{}))
                if old.get('pair','').lower()!=r['address'] and s.now()-old.get('fetchedAt',0)<120 and old.get('liquidity',0)>=liquidity:continue
                stamp=min(s.now(),quote_times.get(b,0))
                outputs[a]={**old,'price':price,'liquidity':liquidity,'pair':r['address'],'venue':r['venue'],'source':'https://monadvision.com/address/'+r['address'],'priceSource':'On-chain V2 reserve reference','blockNumber':int(block,16),'fetchedAt':stamp}
        publish_prices(outputs)

def uncached_catalog(params):
    q=str(params.get('query','')).strip()[:120];scope=params.get('scope','active')
    try:offset=max(0,int(params.get('offset',0)));limit=max(1,min(100,int(params.get('limit',60))))
    except (ValueError,TypeError):raise s.Problem('Invalid market page')
    if q:
        with db() as c:known=c.execute("SELECT 1 FROM assets WHERE info IS NOT NULL AND (address=? OR lower(json_extract(info,'$.symbol')) LIKE ? OR lower(json_extract(info,'$.name')) LIKE ?) LIMIT 1",(q.lower(),'%'+q.lower()+'%','%'+q.lower()+'%')).fetchone()
        if not known and len(q)>=3:search(q)
    # Keep baseline identity/launch metadata and indexed identities in one namespace.
    baseline=s.GATEWAY.markets();tokens={t['id']:t for t in baseline['tokens'] if not t.get('nadfun') or t.get('phase')=='dex'}
    with db() as c:
        rows=c.execute('SELECT info,price,updated FROM assets WHERE info IS NOT NULL').fetchall()
        pool_count=c.execute('SELECT count(*) FROM pools').fetchone()[0]
        pending=c.execute('SELECT count(*) FROM assets WHERE info IS NULL AND updated>=0').fetchone()[0]
        sources=[dict(name=r['name'],**json.loads(r['info'])) for r in c.execute('SELECT * FROM sources')]
    for r in rows:
        item=decoded_metadata(r['info']);ident=item['id'];value=json.loads(r['price']) if r['price'] else {};current=s.GATEWAY.prices.get(ident,{})
        if current.get('fetchedAt',0)>value.get('fetchedAt',0):value=current
        if value:
            with s.LOCK:s.GATEWAY.prices[ident]=value
        stamp=value.get('fetchedAt',0);age=s.now()-stamp
        t={**tokens.get(ident,{}),**item,**value,'stale':not 0<=age<=120,'priceAgeSeconds':max(0,age) if stamp else None}
        if age>900:t['price']=None
        s.GATEWAY.token_map[ident]={**s.GATEWAY.token_map.get(ident,{}),**item};tokens[ident]=t
    all_tokens=list(tokens.values())
    for t in all_tokens:
        try:v=float(t.get('price') or 0)
        except (TypeError,ValueError):v=0
        t['price']=v if math.isfinite(v) and v>0 else None
    if q:all_tokens=[t for t in all_tokens if q.lower() in (t['symbol']+' '+t['name']+' '+t['address']).lower()]
    active=sum((t.get('price') or 0)>0 and not t.get('stale') for t in all_tokens)
    selected=all_tokens if scope=='all' else [t for t in all_tokens if (t.get('price') or 0)>0 and not t.get('stale')]
    selected.sort(key=lambda t: (not((t.get('price') or 0)>0 and not t.get('stale')), -float(t.get('volume') or 0), t['id']))
    return {'tokens':selected[offset:offset+limit],'total':len(selected),'active':active,'lastKnown':sum(bool(t.get('price')) and bool(t.get('stale')) for t in all_tokens),'assets':len(all_tokens),'offset':offset,'nextOffset':offset+limit if offset+limit<len(selected) else None,'indexedPools':pool_count,'pendingMetadata':pending,'sources':sources,'fetchedAt':s.now(),'priceUpdatedAt':max((t.get('fetchedAt',0) for t in all_tokens if t.get('price')),default=0),'source':'Monad factories · DexScreener','financialTransactions':0}

def catalog(params):
    key=tuple(str(params.get(k,'')) for k in ['query','scope','offset','limit'])
    with LOCK:cached=PAGES.get(key)
    if cached and time.monotonic()-cached[0]<5:return cached[1]
    value=uncached_catalog(params)
    with LOCK:
        if len(PAGES)>128:PAGES.pop(next(iter(PAGES)))
        PAGES[key]=(time.monotonic(),value)
    return value

def background():
    try:restore()
    except Exception:delayed('Catalog')
    try:token_lists()
    except Exception:delayed('Monad token list')
    try:index_factories()
    except Exception:delayed('Factory scan')
    tick=0
    while True:
        try:enrich(256)
        except Exception:delayed('Metadata')
        try:refresh_prices()
        except Exception:delayed('Discovery prices')
        try:pool_prices()
        except Exception:delayed('Reserve scan')
        if tick%120==119:
            try:token_lists();index_factories()
            except Exception:delayed('Factory scan')
        tick+=1;time.sleep(15)
