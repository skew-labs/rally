"""UI-only fixtures; imported exclusively by the disposable preview server."""
import os,json
assert os.environ.get('RALLY_TESTING')=='1'
def install():
    import service as s,community_tokens,market_universe
    token='0x'+'a'*40
    paired={'owner':'reader','address':token,'vault':'0x'+'f'*40,'name':'QA Community','symbol':'TEST','logoURI':'/assets/community-rally.png','buybackBps':2000,'burnBps':10000,'stats':{},'venue':'PancakeSwap v2','community':'monad','asset':s.GATEWAY.token_map[token]}
    original=community_tokens.public
    community_tokens.public=lambda owner:paired if owner=='reader' else original(owner)
    s.write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient) VALUES(?,?,?,?,?,?,?,?,?)',('qa-subscription','reader','QA Early discovery','[100,0,0]','[]',s.now(),'2500000',1,'0x'+'c'*40))
    rows=[]
    for i in range(85):
        address='0x'+format(i+100,'040x')
        rows.append({'id':address,'address':address,'name':'QA Token '+str(i),'symbol':'QA'+str(i),'chainId':143,'decimals':18,'logoURI':'/assets/MON.png','price':1+i/100,'change':80-i,'volume':i*100,'fetchedAt':s.now(),'stale':False})
    def catalog(params):
        q=params.get('query','').lower();items=[r for r in rows if q in (r['symbol']+' '+r['name']+' '+r['address']).lower()]
        items.sort(key=market_universe.gainer_key if params.get('sort')=='gainers' else lambda r:-r['volume'])
        offset=int(params.get('offset',0));limit=int(params.get('limit',40));end=offset+limit
        return {'tokens':items[offset:end],'total':len(items),'nextOffset':end if end<len(items) else None,'fetchedAt':s.now(),'active':len(items),'assets':len(items),'indexedPools':85,'sources':[]}
    market_universe.catalog=catalog
