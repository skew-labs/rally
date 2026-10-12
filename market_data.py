"""Public chart reads. Exact identities, bounded upstream work, no wallet access."""
import json
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
    # nad.fun's onchain-verified catalog may precede the generic spot registry.
    verified=None
    if s.re.fullmatch(r'0x[0-9a-fA-F]{40}',str(asset)):
        row=s.one('SELECT info FROM nad_tokens WHERE address=?',(str(asset).lower(),))
        if row:
            candidate=json.loads(row['info'])
            if candidate.get('chainId')==143 and candidate.get('address','').lower()==str(asset).lower() and candidate.get('graduated'):
                verified=candidate
    if not token:token=verified
    if not token:raise s.Problem('Unknown asset',404)
    if asset=='MON':return {'asset':asset,'coin':'monad','symbol':'MON','reference':'Global spot reference','kind':kind}
    price=s.GATEWAY.prices.get(asset,{})
    pair=price.get('pair') or token.get('pair') or (verified or {}).get('pair')
    if not pair or not s.re.fullmatch(r'0x[0-9a-fA-F]{40}',pair):raise s.Problem('No indexed Monad pool chart',404,'chart_unavailable')
    return {'asset':asset,'pool':pair.lower(),'token':token['address'].lower(),'symbol':token['symbol'],'reference':'Monad pool reference','kind':kind}

PERIOD_DAYS={'1D':1,'7D':7,'1M':30}
POINT_BUDGET=320

def hourly_series(rows,period='1D',scale=1,milliseconds=False):
    """Retain provider OHLC. Do not turn sampled prices or empty hours into bars."""
    end=s.now();start=(end-PERIOD_DAYS[period]*86400)//3600*3600;bars={}
    for row in rows:
        try:
            t=int(row[0]/1000) if milliseconds else int(row[0])
            o,h,l,c=(float(v)/scale for v in row[1:5])
            if t%3600 or not start<=t<=end or not all(math.isfinite(v) and v>0 for v in (o,h,l,c)):continue
            if l>min(o,c) or h<max(o,c) or l>h:continue
            bars[t]={'time':t,'open':o,'high':h,'low':l,'close':c}
        except (TypeError,ValueError,IndexError,OverflowError):continue
    if not bars:raise s.Problem('No hourly candles for this market yet',404,'chart_unavailable')
    return [bars[t] for t in sorted(bars)][-721:]

def hourly_chart(asset,kind='spot',period='1D'):
    if period not in PERIOD_DAYS:raise s.Problem('Unknown chart period')
    if not SLOTS.acquire(blocking=False):raise s.Problem('Chart requests are busy. Retry shortly.',503,'chart_busy')
    try:
        from native_market_transport import get
        end=s.now();started=time.perf_counter()
        if kind=='perps' and str(asset).isdigit():
            context=s.GATEWAY.perpl_markets(cached_only=True)
            market=next((m for m in context['markets'] if str(m['id'])==str(asset)),None)
            if not market:raise s.Problem('Unknown Perpl market',404,'chart_unavailable')
            decimals=int(market['priceDecimals'])
            if not 0<=decimals<=18:raise s.Problem('Invalid market precision',502,'chart_identity')
            ident={'asset':str(asset),'kind':kind,'symbol':market['symbol'],'marketId':market['id'],'reference':'Perpl trades'}
            start=(end-PERIOD_DAYS[period]*86400)//3600*3600
            raw=s.http_json(f'https://app.perpl.xyz/api/v1/market-data/{market["id"]}/candles/3600/{start*1000}-{end*1000}',timeout=4)
            if raw.get('r')!=3600 or not isinstance(raw.get('d'),list):raise s.Problem('Candle interval changed',502,'chart_identity')
            bars=hourly_series([[r.get('t'),r.get('o'),r.get('h'),r.get('l'),r.get('c')] for r in raw['d'] if isinstance(r,dict)],period,10**decimals,True)
            source='Perpl';source_url='https://app.perpl.xyz/';timing={'transport':'python-venue','marketCache':False}
        else:
            ident=identity(asset,kind)
            if 'pairBase' in ident:
                import perp_universe
                raw=s.http_json('https://service.leverup.xyz/v1/oracle/candles?'+urlencode({'pair_base':ident['pairBase'],'resolution':'60','from':(end-PERIOD_DAYS[period]*86400)//3600*3600,'to':end,'block_chain':'MONAD'}),headers=perp_universe.HEADERS,timeout=4)
                if str(raw.get('pairBase','')).lower()!=ident['pairBase'] or raw.get('blockChain')!='MONAD' or raw.get('executionVenue')!='POOL':raise s.Problem('Chart identity changed',502,'chart_identity')
                bars=hourly_series([[r.get('time'),r.get('open'),r.get('high'),r.get('low'),r.get('close')] for r in raw.get('candles',[])],period)
                source='LeverUp';source_url='https://app.leverup.xyz/';timing={'transport':'python-venue','marketCache':False}
            else:
                if kind=='spot' and asset=='MON':
                    price=s.GATEWAY.prices.get('MON',{});pair=price.get('pair')
                    if not pair or not s.re.fullmatch(r'0x[0-9a-fA-F]{40}',pair):raise s.Problem('No indexed MON pool',404,'chart_unavailable')
                    ident={'asset':asset,'kind':kind,'pool':pair.lower(),'token':WMON,'symbol':'MON','reference':'WMON · Monad pool'}
                if 'pool' not in ident:raise s.Problem('No hourly source for this market',404,'chart_unavailable')
                raw,timing=get('https://api.geckoterminal.com/api/v2/networks/monad/pools/'+ident['pool']+'/ohlcv/hour?'+urlencode({'aggregate':1,'limit':PERIOD_DAYS[period]*24+1,'currency':'usd','token':ident['token'],'include_empty_intervals':'false'}))
                meta=raw.get('meta',{})
                if ident['token'] not in {str(meta.get(k,{}).get('address','')).lower() for k in ('base','quote')}:raise s.Problem('Chart token identity mismatch',502,'chart_identity')
                bars=hourly_series(raw.get('data',{}).get('attributes',{}).get('ohlcv_list',[]),period)
                source='GeckoTerminal · CoinGecko';source_url='https://www.geckoterminal.com/monad/tokens/'+ident['token']
        return {**ident,'period':period,'interval':'1h','candles':bars,'source':source,'sourceURL':source_url,
                'fetchedAt':end,'lastObservation':bars[-1]['time'],'stale':end-bars[-1]['time']>=7200,
                'cached':False,'freshRead':True,**timing,'upstreamMs':round((time.perf_counter()-started)*1000,2)}
    finally:SLOTS.release()

def compact_points(values,budget=POINT_BUDGET):
    """Keep real endpoints and the extremes of each time bucket, never synthetic prices."""
    if len(values)<=budget:return values
    buckets={};start=values[0]['time'];span=max(1,values[-1]['time']-start)
    count=(budget-2)//2
    for point in values[1:-1]:
        key=min(count-1,(point['time']-start)*count//span)
        low,high=buckets.get(key,(point,point))
        buckets[key]=(point if point['value']<low['value'] else low,point if point['value']>high['value'] else high)
    selected={values[0]['time']:values[0],values[-1]['time']:values[-1]}
    for low,high in buckets.values():
        selected[low['time']]=low;selected[high['time']]=high
    return [selected[t] for t in sorted(selected)]

def series(raw,milliseconds=False,period=None):
    points={};end=s.now();start=end-PERIOD_DAYS[period]*86400 if period else 0
    for row in raw:
        try:
            t=int(row[0]/1000) if milliseconds else int(row[0]);v=float(row[1])
            if not max(0,start)<=t<=end+300 or t<=0 or not math.isfinite(v) or v<=0:continue
            points[t]=v
        except (TypeError,ValueError,IndexError,OverflowError):continue
    values=[{'time':t,'value':v} for t,v in sorted(points.items())]
    if not values:raise s.Problem('No chart observations in this period',404,'chart_unavailable')
    return compact_points(values)


def fresh_chart(asset,kind='spot',period='1D'):
    """One current provider read, without reading or writing market snapshots."""
    if period not in {'1D','7D','1M'}:raise s.Problem('Unknown chart period')
    ident=identity(asset,kind)
    if not SLOTS.acquire(blocking=False):raise s.Problem('Chart requests are busy. Retry shortly.',503,'chart_busy')
    try:
        from native_market_transport import get
        if 'pairBase' in ident:
            import perp_universe
            end=s.now();started=time.perf_counter()
            raw=s.http_json('https://service.leverup.xyz/v1/oracle/candles?'+urlencode({'pair_base':ident['pairBase'],'resolution':'60' if period=='1D' else '240','from':end-PERIOD_DAYS[period]*86400,'to':end,'block_chain':'MONAD'}),headers=perp_universe.HEADERS,timeout=4)
            if str(raw.get('pairBase','')).lower()!=ident['pairBase'] or raw.get('blockChain')!='MONAD' or raw.get('executionVenue')!='POOL':raise s.Problem('Chart identity changed',502,'chart_identity')
            observations=[[r['time'],r['close']] for r in raw.get('candles',[])]
            points=series(observations,period=period)
            timing={'transport':'python-venue','upstreamMs':round((time.perf_counter()-started)*1000,2),'marketCache':False}
            source='LeverUp';source_url='https://app.leverup.xyz/'
        elif 'coin' in ident:
            raw,timing=get('https://api.coingecko.com/api/v3/coins/'+ident['coin']+'/market_chart?'+urlencode({'vs_currency':'usd','days':{'1D':1,'7D':7,'1M':30}[period],'precision':'full'}))
            points=series(raw.get('prices',[]),True,period)
            source='CoinGecko';source_url='https://www.coingecko.com/en/coins/'+ident['coin']
        else:
            timeframe,aggregate,limit={'1D':('minute',15,96),'7D':('hour',1,168),'1M':('day',1,30)}[period]
            raw,timing=get('https://api.geckoterminal.com/api/v2/networks/monad/pools/'+ident['pool']+'/ohlcv/'+timeframe+'?'+urlencode({'aggregate':aggregate,'limit':limit,'currency':'usd','token':ident['token']}))
            meta=raw.get('meta',{})
            if ident['token'] not in {str(meta.get(k,{}).get('address','')).lower() for k in ('base','quote')}:
                raise s.Problem('Chart token identity mismatch',502,'chart_identity')
            points=series([[r[0],r[4]] for r in raw.get('data',{}).get('attributes',{}).get('ohlcv_list',[]) if isinstance(r,list) and len(r)==6],period=period)
            source='GeckoTerminal · CoinGecko';source_url='https://www.geckoterminal.com/monad/tokens/'+ident['token']
        return {**ident,'period':period,'points':points,'source':source,'sourceURL':source_url,'fetchedAt':s.now(),
                'lastObservation':points[-1]['time'],'historyStart':points[0]['time'],'historyEnd':points[-1]['time'],
                'rangeStart':s.now()-PERIOD_DAYS[period]*86400,'rangeEnd':s.now(),'pointBudget':POINT_BUDGET,
                'stale':False,'cached':False,'freshRead':True,**timing}
    finally:SLOTS.release()

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
            points=series([[r['time'],r['close']] for r in raw.get('candles',[])],period=period)
            source='LeverUp';source_url='https://app.leverup.xyz/'
        elif 'coin' in ident:
            url='https://api.coingecko.com/api/v3/coins/'+ident['coin']+'/market_chart?'+urlencode({'vs_currency':'usd','days':{'1D':1,'7D':7,'1M':30}[period],'precision':'full'})
            raw=s.http_json(url,timeout=4);points=series(raw.get('prices',[]),True,period)
            source='CoinGecko';source_url='https://www.coingecko.com/en/coins/'+ident['coin']
        else:
            timeframe='day' if period=='1M' else 'hour'
            url='https://api.geckoterminal.com/api/v2/networks/monad/pools/'+ident['pool']+'/ohlcv/'+timeframe+'?'+urlencode({'aggregate':1,'limit':{'1D':24,'7D':168,'1M':30}[period],'currency':'usd','token':ident['token']})
            raw=s.http_json(url,timeout=4)
            meta=raw.get('meta',{})
            if ident['token'] not in {str(meta.get(k,{}).get('address','')).lower() for k in ('base','quote')}:
                raise s.Problem('Chart token identity mismatch',502,'chart_identity')
            rows=raw.get('data',{}).get('attributes',{}).get('ohlcv_list',[])
            points=series([[r[0],r[4]] for r in rows if isinstance(r,list) and len(r)==6],period=period)
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
