"""Bounded 24-hour nad.fun metrics, collected off the list request path."""
import json, math, threading
from decimal import Decimal
import service as s

LOCK=threading.Lock()
VALUES={};QUEUE={};RETRY={}
TTL=600


def initialize():
    with s.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS nad_metrics(address TEXT PRIMARY KEY,info TEXT NOT NULL,stamp INTEGER NOT NULL)')
        rows=db.execute('SELECT address,info FROM nad_metrics WHERE stamp>=? ORDER BY stamp DESC LIMIT 256',(s.now()-TTL,)).fetchall()
    with LOCK:
        VALUES.update({r['address']:json.loads(r['info']) for r in rows})


def queue(tokens):
    with LOCK:
        for t in tokens[:8]:
            if not t.get('nadfun'):continue
            QUEUE[t['id']]=s.now()
        while len(QUEUE)>64:QUEUE.pop(next(iter(QUEUE)))


def parse(data):
    rows=[r for r in data.get('metrics',[]) if r.get('timeframe')=='1D']
    if len(rows)!=1:raise ValueError('Missing daily metrics')
    row=rows[0]
    if isinstance(row.get('percent'),bool):raise ValueError('Invalid change')
    change=float(row['percent']);volume=Decimal(str(row['volume']['total']))
    if not math.isfinite(change) or not volume.is_finite() or volume<0 or volume>Decimal('1e30'):raise ValueError('Invalid metrics')
    return {'change':change,'volume':str(volume),'changeWindow':'24h','volumeWindow':'24h',
            'metricsAt':s.now(),'metricsSource':'nad.fun 1D trading metrics'}


def overlay(info):
    with LOCK:value=VALUES.get(info.get('id'))
    if value and 0<=s.now()-value['metricsAt']<=TTL:
        return {**info,**value}
    return info


def refresh_once():
    import nadfun as n
    with LOCK:
        now=s.now()
        for a,stamp in list(QUEUE.items()):
            if now-stamp>600:QUEUE.pop(a,None)
        token=next((a for a in sorted(QUEUE,key=lambda a:-QUEUE[a]) if now-VALUES.get(a,{}).get('metricsAt',0)>=120 and RETRY.get(a,0)<=now),None)
        if not token:return False
        QUEUE.pop(token)
    if not s.one('SELECT 1 FROM nad_tokens WHERE address=?',(token,)):return False
    try:
        value=parse(n.api('/trade/metrics/'+n.address(token)+'?timeframes=1D'))
        s.write('INSERT INTO nad_metrics VALUES(?,?,?) ON CONFLICT(address) DO UPDATE SET info=excluded.info,stamp=excluded.stamp',(token,s.dump(value),value['metricsAt']))
        with LOCK:
            VALUES[token]=value;RETRY.pop(token,None)
            while len(VALUES)>256:VALUES.pop(min(VALUES,key=lambda a:VALUES[a]['metricsAt']))
        return True
    except Exception:
        with LOCK:
            RETRY[token]=s.now()+120
            while len(RETRY)>256:RETRY.pop(next(iter(RETRY)))
        return False
