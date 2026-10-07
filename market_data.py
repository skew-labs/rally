"""Public chart reads. Exact identities, bounded upstream work, no wallet access."""
import math
import threading
import time
from urllib.parse import urlencode
import service as s

COINS={1:('BTC','bitcoin'),10:('MON','monad'),20:('ETH','ethereum'),31:('SOL','solana'),40:('HYPE','hyperliquid'),50:('ZEC','zcash'),60:('LIT','lighter'),70:('VVV','venice-token'),90:('PUMP','pump-fun'),100:('NEAR','near'),110:('UNI','uniswap')}
WMON='0x3bd359c1119da7da1d913d1c4d2b7c461115433a'
CACHE={};LOCK=threading.Lock();INFLIGHT={};SLOTS=threading.BoundedSemaphore(2)

def identity(asset,kind):
    if kind=='perps' and ':' in str(asset):
        import perp_universe as perps
        market=next((m for m in perps.catalog()['markets'] if m['id']==asset),None)
        if not market:raise s.Problem('Unknown market',404)
        if market['venue']=='LeverUp':return {'asset':asset,'pairBase':market['pairBase'],'symbol':market['baseSymbol'],'reference':'LeverUp oracle reference','kind':kind}
        coin=next((v for v in COINS.values() if v[0]==market['baseSymbol']),None)
        if not coin:raise s.Problem('No chart source for this market',404,'chart_unavailable')
        return {'asset':asset,'coin':coin[1],'symbol':coin[0],'reference':'Global spot reference','kind':kind}
    if kind=='perps':
        try:ident=int(asset)
        except (ValueError,TypeError):raise s.Problem('Unknown market',404)
        coin=COINS.get(ident)
        if not coin:raise s.Problem('Unknown market',404)
        return {'asset':str(ident),'coin':coin[1],'symbol':coin[0],'reference':'Global spot reference','kind':kind}
    if kind!='spot':raise s.Problem('Unknown chart kind')
    token=s.GATEWAY.token_map.get(asset)
    if not token:raise s.Problem('Unknown asset',404)
    if asset=='MON':return {'asset':asset,'coin':'monad','symbol':'MON','reference':'Global spot reference','kind':kind}
    price=s.GATEWAY.prices.get(asset,{})
    pair=price.get('pair')
    if not pair or not s.re.fullmatch(r'0x[0-9a-fA-F]{40}',pair):raise s.Problem('No indexed Monad pool chart',404,'chart_unavailable')
    return {'asset':asset,'pool':pair.lower(),'token':token['address'].lower(),'symbol':token['symbol'],'reference':'Monad pool reference','kind':kind}

def series(raw,milliseconds=False):
    points={}
    for row in raw:
        try:
            t=int(row[0]/1000) if milliseconds else int(row[0]);v=float(row[1])
            if not 0<t<=s.now()+300 or not math.isfinite(v) or v<=0:continue
            points[t]=v
        except (TypeError,ValueError,IndexError):continue
    values=[{'time':t,'value':v} for t,v in sorted(points.items())]
    if not values:raise s.Problem('No chart observations for this asset',404,'chart_unavailable')
    return values[-3000:]

def chart(asset,kind='spot',period='1D'):
    if period not in {'1D','7D','1M'}:raise s.Problem('Unknown chart period')
    ident=identity(asset,kind);key=(kind,asset,ident.get('pool'),period)
    with LOCK:
        cached=CACHE.get(key)
        if cached and s.now()-cached['fetchedAt']<120:return dict(cached,cached=True,stale=False)
        event=INFLIGHT.get(key);leader=event is None
        if leader:event=INFLIGHT[key]=threading.Event()
    if not leader:
        if not event.wait(5):raise s.Problem('Chart is loading. Try again.',503)
        with LOCK:value=CACHE.get(key)
        if value and s.now()-value['fetchedAt']<3600:return dict(value,cached=True,stale=s.now()-value['fetchedAt']>=120)
        raise s.Problem('Chart provider unavailable',503)
    acquired=False
    try:
        acquired=SLOTS.acquire(timeout=.2)
        if not acquired:raise s.Problem('Charts are busy. Try again.',503)
        if 'pairBase' in ident:
            import perp_universe
            end=s.now();days={'1D':1,'7D':7,'1M':30}[period]
            raw=s.http_json('https://service.leverup.xyz/v1/oracle/candles?'+urlencode({'pair_base':ident['pairBase'],'resolution':'60' if period=='1D' else '240','from':end-days*86400,'to':end,'block_chain':'MONAD'}),headers=perp_universe.HEADERS,timeout=4)
            if str(raw.get('pairBase','')).lower()!=ident['pairBase'] or raw.get('blockChain')!='MONAD' or raw.get('executionVenue')!='POOL':raise s.Problem('Chart identity changed',502,'chart_identity')
            points=series([[r['time'],r['close']] for r in raw.get('candles',[])])
            source='LeverUp';source_url='https://app.leverup.xyz/'
        elif 'coin' in ident:
            url='https://api.coingecko.com/api/v3/coins/'+ident['coin']+'/market_chart?'+urlencode({'vs_currency':'usd','days':{'1D':1,'7D':7,'1M':30}[period],'precision':'full'})
            raw=s.http_json(url,timeout=4);points=series(raw.get('prices',[]),True)
            source='CoinGecko';source_url='https://www.coingecko.com/en/coins/'+ident['coin']
        else:
            timeframe='day' if period=='1M' else 'hour'
            url='https://api.geckoterminal.com/api/v2/networks/monad/pools/'+ident['pool']+'/ohlcv/'+timeframe+'?'+urlencode({'aggregate':1,'limit':{'1D':24,'7D':168,'1M':30}[period],'currency':'usd','token':ident['token']})
            raw=s.http_json(url,timeout=4)
            meta=raw.get('meta',{})
            if ident['token'] not in {str(meta.get(k,{}).get('address','')).lower() for k in ('base','quote')}:
                raise s.Problem('Chart token identity mismatch',502,'chart_identity')
            rows=raw.get('data',{}).get('attributes',{}).get('ohlcv_list',[])
            points=series([[r[0],r[4]] for r in rows if isinstance(r,list) and len(r)==6])
            source='GeckoTerminal · CoinGecko';source_url='https://www.geckoterminal.com/monad/pools/'+ident['pool']
        value={**ident,'period':period,'points':points,'source':source,'sourceURL':source_url,'fetchedAt':s.now(),'lastObservation':points[-1]['time'],'stale':False}
        with LOCK:
            if len(CACHE)>=160:
                oldest=min(CACHE,key=lambda k:CACHE[k]['fetchedAt']);CACHE.pop(oldest,None)
            CACHE[key]=value
        return value
    except Exception:
        if cached and s.now()-cached['fetchedAt']<3600:return dict(cached,cached=True,stale=True)
        raise
    finally:
        if acquired:SLOTS.release()
        with LOCK:INFLIGHT.pop(key,None);event.set()

def perpl_background():
    while True:
        try:
            s.GATEWAY.perpl_markets()
            import perp_universe
            perp_universe.read_venue('Perpl',perp_universe.perpl)
        except Exception:pass
        time.sleep(5)

def background():
    threading.Thread(target=perpl_background,daemon=True,name='perpl-context').start()
    # Public data cadence is independent of settlement reconciliation.
    tick=0
    while True:
        # spot_prices owns the shared priority lane. Avoid duplicate HTTP scans
        # that compete with live quotes and erase partial successful updates.
        if tick%8==0:
            try:
                import venues
                venues.predictions()
            except Exception:pass
        tick+=1;time.sleep(15)
