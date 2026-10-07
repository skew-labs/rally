"""Progressive public quote comparison, sharing bounded work for each exact pair."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
import service as s
import route_quotes as q

EXECUTOR=ThreadPoolExecutor(max_workers=4,thread_name_prefix='public-routes-rpc')
FAST_EXECUTOR=ThreadPoolExecutor(max_workers=2,thread_name_prefix='public-routes-http')
EVENTS={};DEADLINE=12

def compare(who,data):
    if who and who['grant']:s.require(who,'markets:read')
    a,b,amount=q.inputs(data);key=(a['id'],b['id'],amount)
    with q.LOCK:
        value=q.CACHE.get(key)
        if value and value['expires']>s.now():return dict(value,cached=True)
        if not q.SLOTS.acquire(blocking=False):raise s.Problem('Quotes are busy. Try again.',503)
        import extra_routes, v2_routes
        providers=[('KyberSwap',q.kyber),*v2_routes.REFERENCE_PROVIDERS,('Uniswap v3',q.uniswap),*extra_routes.REFERENCE_PROVIDERS,('Kuru',q.kuru)]
        ident=s.uid();event=threading.Event();EVENTS[ident]=event
        value={'id':ident,'input':a['id'],'output':b['id'],'amountRaw':str(amount),'routes':[{'provider':name,'state':'checking','executable':False} for name,_ in providers],'best':None,'quotedAt':s.now(),'expires':s.now()+20,'comparison':'output_before_network_gas','transaction':None,'complete':False}
        if len(q.CACHE)>200:
            for k in list(q.CACHE):
                if q.CACHE[k]['expires']<=s.now():q.CACHE.pop(k,None)
        q.CACHE[key]=value
    def call(name,fn):
        try:result=fn(a,b,amount)
        except Exception as exc:result={'provider':name,'state':'unavailable','code':exc.code if isinstance(exc,s.Problem) else 'provider_unavailable','executable':False}
        with q.LOCK:
            latest=q.CACHE.get(key)
            if latest and latest['id']==ident and not latest['complete'] and latest['expires']>s.now():
                routes=[result if r['provider']==name else r for r in latest['routes']]
                routes.sort(key=lambda r:int(r.get('outputRaw','0')),reverse=True)
                best=next((r['provider'] for r in routes if r['state']=='quoted'),None)
                complete=all(r['state']!='checking' for r in routes)
                q.CACHE[key]={**latest,'routes':routes,'best':best,'complete':complete}
                if best or complete:event.set()
    def run():
        try:
            # HTTP providers must not queue behind contract graph discovery.
            futures=[(FAST_EXECUTOR if name in {'KyberSwap','Kuru'} else EXECUTOR).submit(call,name,fn) for name,fn in providers]
            wait(futures,timeout=DEADLINE)
            with q.LOCK:
                latest=q.CACHE.get(key)
                if latest and latest['id']==ident and not latest['complete']:
                    q.CACHE[key]={**latest,'complete':True,'routes':[dict(r,state='unavailable',code='provider_timeout') if r['state']=='checking' else r for r in latest['routes']]}
                event.set()
            for future in futures:future.cancel()
            # Keep admission occupied until actual workers finish, bounding late work.
            wait(futures)
        finally:
            q.SLOTS.release()
            with q.LOCK:EVENTS.pop(ident,None)
    threading.Thread(target=run,daemon=True,name='public-route-comparison').start()
    event.wait(.9)
    with q.LOCK:return dict(q.CACHE[key])

def status(who,ident):
    if who and who['grant']:s.require(who,'markets:read')
    with q.LOCK:
        value=next((v for v in q.CACHE.values() if v['id']==ident),None)
        if not value or value['expires']<=s.now():raise s.Problem('Quotes expired. Refresh routes.',409,'quotes_expired')
        return dict(value)
