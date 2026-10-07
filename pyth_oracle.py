"""Public on-chain references and fresh signed Hermes payloads. No signer."""
import os,re
from decimal import Decimal
from urllib.parse import urlencode
import service as s
import extra_routes as e

# Monad's Pyth deployment, resolved from Pingu's official PythUpdater contract.
PYTH='0x2880ab155794e7179c9ee2e38200202908c17b43'

def feed(value):
    value=str(value).lower()
    if not re.fullmatch('0x[0-9a-f]{64}',value):raise s.Problem('Invalid oracle feed',502,'oracle_identity')
    return value

def price(value,max_age=60):
    p,confidence,exponent,published=value
    if not -36<=exponent<=18 or p<=0 or confidence<0 or confidence*100>p or not s.now()-max_age<=published<=s.now()+5:return None
    number=Decimal(p)*Decimal(10)**exponent
    if not number.is_finite() or number<=0:return None
    return {'price':float(number),'time':published,'confidence':str(Decimal(confidence)*Decimal(10)**exponent),'source':'Pyth on Monad'}

def onchain(ids,max_age=60,block=None):
    ids=list(dict.fromkeys(feed(x) for x in ids))
    if len(ids)>150:raise s.Problem('Too many oracle feeds',422)
    block=block or s.rpc('eth_blockNumber',[]);result={}
    calls=[e.request(PYTH,'getPriceUnsafe(bytes32)',['bytes32'],[bytes.fromhex(x[2:])]) for x in ids]
    for i in range(0,len(calls),48):
        try:values=e.batch(calls[i:i+48],block)
        except Exception:continue
        for ident,(ok,raw) in zip(ids[i:i+48],values):
            if not ok:continue
            try:value=price(e.decoded(['(int64,uint64,int32,uint256)'],raw)[0],max_age)
            except Exception:continue
            if value:result[ident]={**value,'block':int(block,16)}
    return result

def signed(ident,max_age=12):
    ident=feed(ident);key=os.environ.get('RALLY_PYTH_API_KEY','').strip()
    if not key:raise s.Problem('Pyth Hermes access is required for Drake orders.',503,'oracle_access_required')
    raw=s.http_json('https://hermes.pyth.network/v2/updates/price/latest?'+urlencode([('ids[]',ident[2:]),('encoding','hex'),('parsed','true')]),headers={'Authorization':'Bearer '+key,'User-Agent':'Rally/1.0'},timeout=6)
    entries=raw.get('parsed',[]);binary=raw.get('binary',{})
    if len(entries)!=1 or feed('0x'+entries[0].get('id','').removeprefix('0x'))!=ident or binary.get('encoding')!='hex':raise s.Problem('Oracle feed identity changed',502,'oracle_identity')
    p=entries[0]['price'];reference=price((int(p['price']),int(p['conf']),int(p['expo']),int(p['publish_time'])),max_age)
    updates=binary.get('data')
    if not reference or not isinstance(updates,list) or not 1<=len(updates)<=4 or any(not isinstance(x,str) or not re.fullmatch('(?:0x)?(?:[0-9a-fA-F]{2}){1,40000}',x) for x in updates):raise s.Problem('A fresh signed oracle update is unavailable',503,'stale_price')
    return [bytes.fromhex(x.removeprefix('0x')) for x in updates],reference
