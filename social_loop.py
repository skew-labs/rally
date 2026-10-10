"""Immutable observed signals, opt-in receipt-backed fills, and watched-market alerts."""
import json
import math
import time
from decimal import Decimal
from urllib.parse import quote
import service as s
import social
MARKET_CURSOR=('', '')
MIGRATION_CURSOR=('', '')


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS signals(post TEXT PRIMARY KEY,owner TEXT,asset TEXT,terms TEXT,entry TEXT,observed INTEGER,expires INTEGER,state TEXT DEFAULT 'active',last TEXT,updated INTEGER);
        CREATE TABLE IF NOT EXISTS signal_points(post TEXT,observed INTEGER,price TEXT,source TEXT,PRIMARY KEY(post,observed));
        CREATE TABLE IF NOT EXISTS trade_shares(post TEXT PRIMARY KEY,owner TEXT,reference TEXT UNIQUE,proof TEXT,created INTEGER,withdrawn INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS market_alerts(owner TEXT,asset TEXT,enabled INTEGER,threshold INTEGER,anchor TEXT,last_at INTEGER,phase TEXT,migration_block INTEGER,PRIMARY KEY(owner,asset));
        CREATE INDEX IF NOT EXISTS signals_due ON signals(state,expires);
        CREATE INDEX IF NOT EXISTS signals_owner ON signals(owner,observed);
        CREATE INDEX IF NOT EXISTS alerts_owner ON market_alerts(enabled,owner,asset);
        ''')


def reference(asset):
    """Read the shared cache only. Reject stale, future, mismatched identities."""
    meta=s.GATEWAY.token_map.get(asset) or {}
    price=(getattr(s.GATEWAY,'prices',{}) or {}).get(asset) or {}
    if asset.startswith('0x'):
        import nadfun
        with nadfun.MARKET_REFERENCE_LOCK:cached=dict(nadfun.MARKET_REFERENCES.get(asset) or {})
        row=s.one('SELECT info FROM nad_tokens WHERE address=?',(asset,))
        if row:meta={**meta,**json.loads(row['info'])}
        if cached:price={**cached,'fetchedAt':cached.get('referenceAt'),'source':'nad.fun'}
        elif meta.get('referenceAt'):price={**meta,'fetchedAt':meta['referenceAt'],'source':'nad.fun'}
    stamp=price.get('fetchedAt',price.get('referenceAt',0));value=price.get('price')
    try:
        value=Decimal(str(value));stamp=int(stamp)
        if not value.is_finite() or not Decimal('1e-30')<=value<=Decimal('1e30') or not 0<=s.now()-stamp<=180:return None
        if price.get('id',asset)!=asset or price.get('chainId',143)!=143:return None
    except (ValueError,TypeError,ArithmeticError):return None
    return {'asset':asset,'price':str(value),'observedAt':stamp,'source':str(price.get('priceSource') or price.get('source') or price.get('venue') or 'Monad market reference')[:80],'symbol':meta.get('symbol',asset),'chainId':143}


def signal_terms(data,asset):
    if data is None:return None
    if not isinstance(data,dict) or not asset:raise s.Problem('Choose a token for your signal')
    direction=data.get('direction','up');hours=data.get('hours',24)
    if direction not in {'up','down'} or type(hours)is not int or not 1<=hours<=720:raise s.Problem('Choose a direction and a duration from 1 hour to 30 days')
    try:
        target=Decimal(str(data.get('target')));stop=Decimal(str(data.get('invalidation')))
        if not target.is_finite() or not stop.is_finite() or min(target,stop)<=0 or max(target,stop)>Decimal('1e30'):raise ValueError()
    except (ValueError,ArithmeticError):raise s.Problem('Enter a target and invalidation price in USD')
    return {'direction':direction,'target':str(target),'invalidation':str(stop),'hours':hours}


def attach(db,ident,who,terms,asset):
    if not terms:return
    ref=reference(asset)
    if not ref:raise s.Problem('A fresh price is needed to publish this signal',409,'price_unavailable')
    target,stop,entry=map(Decimal,[terms['target'],terms['invalidation'],ref['price']])
    if not (stop<entry<target if terms['direction']=='up' else target<entry<stop):raise s.Problem('Target and invalidation must be on opposite sides of the current price')
    db.execute('INSERT INTO signals(post,owner,asset,terms,entry,observed,expires,last,updated) VALUES(?,?,?,?,?,?,?,?,?)',(ident,who['actor'],asset,s.dump(terms),s.dump(ref),ref['observedAt'],s.now()+terms['hours']*3600,s.dump(ref),s.now()))
    db.execute('INSERT INTO signal_points VALUES(?,?,?,?)',(ident,ref['observedAt'],ref['price'],ref['source']))


def signal_view(row):
    entry=json.loads(row['entry']);last=json.loads(row['last']);terms=json.loads(row['terms'])
    change=(Decimal(last['price'])/Decimal(entry['price'])-1)*100
    return {'post':row['post'],'asset':row['asset'],'state':row['state'],'entry':entry,'latest':last,'terms':terms,
        'expires':row['expires'],'priceChangePercent':float(change),'stale':s.now()-last['observedAt']>180,
        'basis':'Observed price movement, not a trade return','points':s.rows('SELECT observed,price FROM signal_points WHERE post=? ORDER BY observed DESC LIMIT 60',(row['post'],))[::-1]}


def enrich(post):
    sig=s.one('SELECT * FROM signals WHERE post=?',(post['id'],))
    if sig:post['signal']=signal_view(sig)
    trade=s.one('SELECT proof FROM trade_shares WHERE post=? AND withdrawn=0',(post['id'],))
    if trade:post['verifiedTrade']=json.loads(trade['proof'])
    return post


def track_record(who,owner):
    user=who['user'] if who else None
    if who and who.get('grant'):s.require(who,'feed:read')
    if not social.visible(user,owner):raise s.Problem('Profile not found',404)
    stats=s.rows('SELECT s.state,count(*) n,sum(p.deleted) withdrawn FROM signals s JOIN posts p ON p.id=s.post WHERE s.owner=? GROUP BY s.state',(owner,))
    counts={state:sum(r['n'] for r in stats if r['state']==state) for state in ['active','target_reached','invalidated','expired']}
    rows=s.rows('SELECT s.* FROM signals s JOIN posts p ON p.id=s.post WHERE s.owner=? AND p.deleted=0 ORDER BY s.observed DESC LIMIT 30',(owner,))
    return {'owner':owner,'counts':counts,'withdrawn':sum(r['withdrawn'] for r in stats),'total':sum(counts.values()),
        'signals':[signal_view(r) for r in rows], 'basis':'Observed crossings only. Deleted calls remain in counts.'}


def tick_signals():
    import push_delivery as push
    for row in s.rows("SELECT * FROM signals WHERE state='active' ORDER BY updated LIMIT 100"):
        ref=reference(row['asset']);state='active';last=json.loads(row['last']);terms=json.loads(row['terms'])
        if ref and ref['observedAt']>last['observedAt'] and ref['observedAt']<=row['expires']:
            price=Decimal(ref['price']);up=terms['direction']=='up'
            if price>=Decimal(terms['target']) if up else price<=Decimal(terms['target']):state='target_reached'
            elif price<=Decimal(terms['invalidation']) if up else price>=Decimal(terms['invalidation']):state='invalidated'
            last=ref
            s.write('INSERT OR IGNORE INTO signal_points VALUES(?,?,?,?)',(row['post'],ref['observedAt'],ref['price'],ref['source']))
        if state=='active' and s.now()>=row['expires']:state='expired'
        changed=s.write("UPDATE signals SET state=?,last=?,updated=? WHERE post=? AND state='active'",(state,s.dump(last),s.now(),row['post']))
        if changed and state!='active':
            account=s.one('SELECT owner FROM accounts WHERE id=?',(row['owner'],)) or {}
            for owner in {account.get('owner') or row['owner'],*[r['user_id'] for r in s.rows("SELECT user_id FROM reactions WHERE post=? AND kind='save'",(row['post'],))]}:
                push.emit(owner,'signal','signal:'+row['post']+':'+owner,'Signal update',last['symbol']+' · '+state.replace('_',' '),'/?view=post&post='+row['post'],post=row['post'])
    # Keep the original reference and newest 600 observations per signal.
    s.write('DELETE FROM signal_points WHERE observed!=(SELECT observed FROM signals WHERE post=signal_points.post) AND observed<coalesce((SELECT p.observed FROM signal_points p WHERE p.post=signal_points.post ORDER BY p.observed DESC LIMIT 1 OFFSET 599),0)')
    # Retain entry and closing point while bounding high-frequency samples.
    s.write('DELETE FROM signal_points WHERE observed<? AND observed NOT IN (SELECT observed FROM signals WHERE post=signal_points.post) AND post IN (SELECT post FROM signals WHERE state!=\'active\')',(s.now()-90*86400,))


def fill(user,reference_id):
    """Only saved, reconciled, finalized records owned by this account qualify."""
    import discovery
    row=s.one('SELECT o.*,q.wallet,q.input,q.output,q.amount,q.payload FROM orders o JOIN quotes q ON q.id=o.quote_id WHERE o.id=? AND o.user_id=?',(reference_id,user))
    if row:
        receipt=json.loads(row['receipt'] or '{}');payload=json.loads(row['payload']);delta=discovery.deltas(receipt,row['wallet'])
        if row['state']!='finalized' or int(receipt.get('status','0x0'),16)!=1 or receipt.get('transactionHash','').lower()!=str(row['tx']).lower() or not receipt.get('blockHash'):raise s.Problem('This trade is not a verified finalized fill',409)
        a=s.GATEWAY.token_map.get(row['input']);b=s.GATEWAY.token_map.get(row['output'])
        if not a or not b:raise s.Problem('Token identity is unavailable',409)
        if a['address'].lower()!=s.ZERO and delta.get(a['address'].lower(),0)>=0:raise s.Problem('No spent input balance was verified',409)
        if b['address'].lower()!=s.ZERO and delta.get(b['address'].lower(),0)<=0:raise s.Problem('No delivered output balance was verified',409)
        if a['address'].lower()==s.ZERO:
            try:
                if int(payload.get('transaction',{}).get('value','0x0'),16)<int(row['amount']):raise ValueError()
            except (ValueError,TypeError):raise s.Problem('Native input identity unavailable',409)
        asset=row['output'] if row['output'] not in {'MON',s.USDC} else row['input'];side='buy' if asset==row['output'] else 'sell'
        token=s.GATEWAY.token_map[asset];raw=delta.get(token['address'].lower(),0)
        received=delta.get(b['address'].lower(),0)
        if not raw or side=='buy' and raw<=0 or side=='sell' and raw>=0:raise s.Problem('No delivered token balance was verified',409)
        # Native output is not inferred from a quote or receipt gas delta.
        return {'asset':asset,'symbol':token['symbol'],'side':side,'quantity':s.units(abs(raw),token['decimals']),
            'received':s.units(received,b['decimals']) if received>0 else None,'receivedSymbol':b['symbol'] if received>0 else None,
            'venue':payload.get('provider','Kuru'),'tx':row['tx'],'block':int(receipt['blockNumber'],16),'created':row['created'],'chainId':143,'kind':'spot'}
    row=s.one('SELECT r.*,p.wallet,p.venue,p.kind,p.payload FROM execution_records r JOIN execution_plans p ON p.id=r.plan WHERE r.id=? AND r.user_id=?',(reference_id,user))
    if not row:raise s.Problem('Your trade was not found',404)
    out=json.loads(row['outcome'] or '{}');p=json.loads(row['payload']);summary=p.get('summary',{});receipt=out.get('receipt') or {}
    if row['state']!='finalized' or int(receipt.get('status','0x0'),16)!=1 or receipt.get('transactionHash','').lower()!=str(row['tx']).lower() or not receipt.get('blockHash'):raise s.Problem('This trade is not finalized',409)
    if row['venue']=='nadfun' and row['kind'] in {'buy','sell'} and out.get('businessState')=='swap_delivered':
        asset=summary['token'];qty=out['received'] if row['kind']=='buy' else summary['amount']
        return {'asset':asset,'symbol':summary['symbol'],'side':row['kind'],'quantity':qty,'received':out['received'],'receivedSymbol':summary['outputAsset'],'venue':'nad.fun','tx':row['tx'],'block':int(receipt['blockNumber'],16),'created':row['created'],'chainId':143,'kind':'spot'}
    if row['venue']=='perpl' and row['kind']=='order' and out.get('businessState') in {'filled','partial_fill'}:
        try:
            if Decimal(str(out['fillQuantity']))<=0 or Decimal(str(out['entryPrice']))<=0:raise ValueError()
        except (KeyError,ValueError,ArithmeticError):raise s.Problem('Fill quantity or price unavailable',409)
        return {'asset':'','marketId':summary['marketId'],'symbol':summary['market'],'side':'buy' if summary['direction']=='long' else 'sell','quantity':out['fillQuantity'],'fillPrice':out['entryPrice'],'label':('Reduced ' if summary.get('reduceOnly') else 'Opened ')+summary['direction'],'venue':'Perpl','tx':row['tx'],'block':int(receipt['blockNumber'],16),'created':row['created'],'chainId':143,'kind':'perps'}
    raise s.Problem('This venue has no eligible verified fill',409,'share_fill_unsupported')


def share(who,data):
    owner=s.require(who,human=True);ref=str(data.get('trade',''));proof=fill(owner,ref)
    text=data.get('text','')
    if not isinstance(text,str) or len(text)>1000:raise s.Problem('Keep your trade caption under 1,000 characters')
    text=text.strip() or proof['side'].capitalize()+' · '+proof['symbol']+' · '+proof['venue']
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM trade_shares WHERE reference=?',(ref,)).fetchone()
        if old:
            if old['owner']!=owner or old['withdrawn']:raise s.Problem('This fill was already shared or withdrawn',409)
            ident=old['post']
        else:
            if db.execute('SELECT count(*) FROM trade_shares WHERE owner=? AND created>?',(owner,s.now()-86400)).fetchone()[0]>=30:raise s.Problem('Daily sharing limit reached',429)
            ident=s.uid();db.execute('INSERT INTO posts(id,author,text,asset,created) VALUES(?,?,?,?,?)',(ident,owner,text,proof['asset'] or None,s.now()))
            db.execute('INSERT INTO trade_shares(post,owner,reference,proof,created) VALUES(?,?,?,?,?)',(ident,owner,ref,s.dump(proof),s.now()))
    import push_delivery as push
    for follower in s.rows('SELECT user_id FROM follows WHERE target=? LIMIT 1000',(owner,)):
        push.emit(follower['user_id'],'trade','trade:'+ident+':'+follower['user_id'],'Shared trade',proof['symbol']+' · '+proof['venue'],'/?view=post&post='+ident,actor=owner,post=ident)
    return s.post_view(s.one('SELECT * FROM posts WHERE id=?',(ident,)),owner)


def withdraw(who,data):
    owner=s.require(who,human=True)
    with s.connection() as db:
        changed=db.execute('UPDATE trade_shares SET withdrawn=1 WHERE post=? AND owner=?',(data.get('post'),owner)).rowcount
        if changed:db.execute('UPDATE posts SET deleted=1 WHERE id=? AND author=?',(data.get('post'),owner))
    return {'withdrawn':bool(changed)}


def shareable(who):
    user=s.require(who,human=True);items=[]
    ids=s.rows("SELECT id,created FROM orders WHERE user_id=? AND state='finalized' UNION ALL SELECT id,created FROM execution_records WHERE user_id=? AND state='finalized' ORDER BY created DESC LIMIT 40",(user,user))
    for row in ids:
        try:proof=fill(user,row['id'])
        except (s.Problem,ValueError,KeyError):continue
        shared=s.one('SELECT post,withdrawn FROM trade_shares WHERE reference=?',(row['id'],))
        items.append({'id':row['id'],**proof,'sharedPost':shared['post'] if shared else None,'withdrawn':bool(shared and shared['withdrawn'])})
    return {'trades':items}


def alerts(who,data=None):
    owner=s.require(who,human=True)
    if data is not None:
        asset=str(data.get('asset',''));enabled=data.get('enabled');threshold=data.get('thresholdBps',500)
        if type(enabled)is not bool or type(threshold)is not int or not 100<=threshold<=10000:raise s.Problem('Choose a price change between 1% and 100%')
        if enabled and not s.one('SELECT 1 FROM watches WHERE user_id=? AND asset=?',(owner,asset)):raise s.Problem('Add this token to your watchlist first',409)
        if asset not in s.GATEWAY.token_map and not s.one('SELECT 1 FROM nad_tokens WHERE address=?',(asset,)):raise s.Problem('Unknown Monad token')
        if enabled and not s.one('SELECT 1 FROM market_alerts WHERE owner=? AND asset=?',(owner,asset)) and s.one('SELECT count(*) n FROM market_alerts WHERE owner=? AND enabled=1',(owner,))['n']>=30:raise s.Problem('Alert limit reached',429)
        ref=reference(asset)
        s.write('INSERT INTO market_alerts(owner,asset,enabled,threshold,anchor,last_at) VALUES(?,?,?,?,?,?) ON CONFLICT(owner,asset) DO UPDATE SET enabled=excluded.enabled,threshold=excluded.threshold,anchor=excluded.anchor,last_at=excluded.last_at',(owner,asset,int(enabled),threshold,s.dump(ref) if ref else None,s.now()))
    return {'alerts':s.rows('SELECT asset,enabled,threshold,last_at,migration_block FROM market_alerts WHERE owner=?',(owner,))}


def tick_markets():
    import push_delivery as push
    global MARKET_CURSOR,MIGRATION_CURSOR
    query='SELECT m.* FROM market_alerts m JOIN watches w ON w.user_id=m.owner AND w.asset=m.asset WHERE m.enabled=1'
    rows=s.rows(query+' AND (m.owner,m.asset)>(?,?) ORDER BY m.owner,m.asset LIMIT 100',MARKET_CURSOR)
    if not rows:rows=s.rows(query+' ORDER BY m.owner,m.asset LIMIT 100')
    if rows:MARKET_CURSOR=(rows[-1]['owner'],rows[-1]['asset'])
    for row in rows:
        ref=reference(row['asset']);anchor=json.loads(row['anchor'] or 'null')
        if not ref:continue
        if not anchor:s.write('UPDATE market_alerts SET anchor=?,last_at=? WHERE owner=? AND asset=?',(s.dump(ref),s.now(),row['owner'],row['asset']));continue
        move=(Decimal(ref['price'])/Decimal(anchor['price'])-1)*10000
        if abs(move)>=row['threshold'] and s.now()-row['last_at']>=300:
            push.emit(row['owner'],'price','price:'+row['owner']+':'+row['asset']+':'+str(ref['observedAt']),ref['symbol']+' price alert',str(round(move/100,2))+'% since your last alert','/?view=token&token='+quote(row['asset']))
            s.write('UPDATE market_alerts SET anchor=?,last_at=? WHERE owner=? AND asset=?',(s.dump(ref),s.now(),row['owner'],row['asset']))
    # Watch one candidate per tick. A provider's migration label is only a hint.
    query='SELECT m.*,t.info FROM market_alerts m JOIN nad_tokens t ON t.address=m.asset JOIN watches w ON w.user_id=m.owner AND w.asset=m.asset WHERE m.enabled=1 AND m.phase IS NOT \'dex\''
    candidates=s.rows(query+' AND (m.owner,m.asset)>(?,?) ORDER BY m.owner,m.asset LIMIT 1',MIGRATION_CURSOR)
    if not candidates:candidates=s.rows(query+' ORDER BY m.owner,m.asset LIMIT 1')
    for row in candidates:
        MIGRATION_CURSOR=(row['owner'],row['asset'])
        import nadfun
        info=json.loads(row['info']);block=s.rpc('eth_getBlockByNumber',['finalized',False])
        live=nadfun.state(info.get('version','v2'),row['asset'],block['number'])
        if row['phase']=='curve' and live['phase']=='dex':
            push.emit(row['owner'],'migration','migration:'+row['owner']+':'+row['asset'],info.get('symbol','Token')+' migrated','DEX migration verified at finalized block '+str(live['block']),'/?view=token&token='+quote(row['asset']))
        s.write('UPDATE market_alerts SET phase=?,migration_block=? WHERE owner=? AND asset=?',(live['phase'],live['block'],row['owner'],row['asset']))


def background():
    import token_benefits,algorithm_league,discovery
    while True:
        for task in (tick_signals,tick_markets,token_benefits.tick,algorithm_league.tick,discovery.alerts_tick):
            try:task()
            except Exception as error:
                __import__('logging').getLogger(__name__).warning('Social task %s failed: %s',task.__name__,type(error).__name__)
        time.sleep(15)
