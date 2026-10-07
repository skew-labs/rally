"""Public discovery, receipt-based performance and entitled feed alerts.

This module never requests a wallet signature, submits a transaction or reads a
price provider. Return metrics use actual wallet deltas in saved finalized
receipts, not quotes, price changes, engagement or backtests.
"""
import json
from decimal import Decimal, localcontext
import service as s
import social
import settlement

TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
ALERT_CURSOR=('', '')


def initialize():
    with s.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS feed_alerts(
            owner TEXT,feed TEXT,version INTEGER,enabled INTEGER,after_created INTEGER,
            PRIMARY KEY(owner,feed))''')
        db.execute('''CREATE TABLE IF NOT EXISTS feed_performance_sharing(
            feed TEXT PRIMARY KEY,owner TEXT,enabled INTEGER)''')
        if 'after_post_row' not in {r[1] for r in db.execute('PRAGMA table_info(feed_alerts)')}:
            db.execute('ALTER TABLE feed_alerts ADD COLUMN after_post_row INTEGER NOT NULL DEFAULT 0')
            db.execute('UPDATE feed_alerts SET after_post_row=(SELECT coalesce(max(rowid),0) FROM posts)')


def viewer(who):
    if who and who.get('grant'):s.require(who,'feed:read')
    return who['user'] if who else None


def deltas(receipt, wallet):
    result={}
    if int(receipt.get('status','0x0'),16)!=1:return result
    for log in receipt.get('logs',[]):
        topics=log.get('topics',[])
        try:
            if log.get('removed') or len(topics)!=3 or topics[0].lower()!=TRANSFER:continue
            value=int(log['data'],16)
            if value<0:continue
            sender='0x'+topics[1][-40:].lower();receiver='0x'+topics[2][-40:].lower()
            address=log['address'].lower()
        except (KeyError,ValueError,TypeError):continue
        result[address]=result.get(address,0)+value*(int(receiver==wallet.lower())-int(sender==wallet.lower()))
    return result


def realized(rows, stable, cutoff=0):
    """FIFO cost basis for complete, locally recorded stable/token round trips.

    A sale without enough recorded inventory is excluded in full. Other assets,
    pending/failed transactions, gas, deposits and unrealized balances are never
    counted as investment profit. Decimal arithmetic avoids token-size rounding.
    """
    stable=stable.lower();lots={};cost=Decimal(0);proceeds=Decimal(0);closed=0;proofs=[];seen=set();events=[]
    for row in rows:
        if row.get('state')!='finalized':continue
        try:
            receipt=json.loads(row['receipt']) if isinstance(row['receipt'],str) else row['receipt']
            if not receipt or not receipt.get('blockHash') or receipt.get('transactionHash','').lower()!=row['tx'].lower():continue
            block=int(receipt['blockNumber'],16);index=int(receipt['transactionIndex'],16)
            events.append((block,index,row,receipt))
        except (ValueError,TypeError,KeyError,AttributeError):continue
    with localcontext() as ctx:
        ctx.prec=90
        for _,_,row,receipt in sorted(events,key=lambda event:(event[0],event[1],event[2]['tx'])):
            try:
                if row['tx'].lower() in seen:continue
                seen.add(row['tx'].lower())
                flow=deltas(receipt,row['wallet'])
                incoming=row['inputAddress'].lower();outgoing=row['outputAddress'].lower()
                if incoming==stable and outgoing!=stable and flow.get(stable,0)<0 and flow.get(outgoing,0)>0:
                    lots.setdefault(outgoing,[]).append([Decimal(flow[outgoing]),Decimal(-flow[stable]),row['tx']])
                elif outgoing==stable and incoming!=stable and flow.get(incoming,0)<0 and flow.get(stable,0)>0:
                    quantity=Decimal(-flow[incoming]);inventory=lots.setdefault(incoming,[])
                    if sum((x[0] for x in inventory),Decimal(0))<quantity:
                        # Do not carry an unknown-cost position into future ROI.
                        inventory.clear();continue
                    consumed=Decimal(0);sources=[];remaining=quantity
                    while remaining>0:
                        amount,basis,tx=inventory[0];used=min(amount,remaining);piece=basis*used/amount
                        consumed+=piece;sources.append(tx);remaining-=used
                        if used==amount:inventory.pop(0)
                        else:inventory[0]=[amount-used,basis-piece,tx]
                    if row['created']>=cutoff:
                        cost+=consumed;proceeds+=Decimal(flow[stable]);closed+=1;proofs.extend([*sources,row['tx']])
            except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):continue
        return {'roi':float((proceeds-cost)*100/cost) if cost>0 else None,
            'pnl':format((proceeds-cost)/Decimal(1000000),'f') if cost>0 else None,
            'costBasisRaw':str(cost),'proceedsRaw':str(proceeds),
            'closedTrades':closed,'proofs':list(dict.fromkeys(proofs))[:20],
            'state':'verified' if cost>0 else 'unverified','currency':'USDC',
            'basis':'Recorded USDC spot trades linked to this algorithm. Network fees excluded.'}


def performance(feed,days=30):
    empty={'roi':None,'pnl':None,'closedTrades':0,'proofs':[],'state':'unverified',
        'currency':'USDC','windowDays':days,'basis':'No verified closed trades'}
    if feed['owner']=='rally':return empty
    if not s.one('SELECT 1 FROM feed_performance_sharing WHERE feed=? AND owner=? AND enabled=1',(feed['id'],feed['owner'])):
        return {**empty,'basis':'The creator has not published verified trade returns'}
    history=s.rows('''SELECT o.*,q.wallet,q.input,q.output FROM orders o
        JOIN quotes q ON q.id=o.quote_id JOIN activity_context c ON c.kind='spot'
        AND c.reference=q.id AND c.user_id=o.user_id
        WHERE o.user_id=? AND c.feed=? ORDER BY o.created,o.id LIMIT 1001''',(feed['owner'],feed['id']))
    if len(history)>1000:return {**empty,'basis':'Recorded history exceeds the calculation limit'}
    for row in history:
        row['inputAddress']=(s.GATEWAY.token_map.get(row['input']) or {}).get('address',row['input'])
        row['outputAddress']=(s.GATEWAY.token_map.get(row['output']) or {}).get('address',row['output'])
    return {**realized(history,s.USDC.lower(),s.now()-days*86400),'windowDays':days}


def cover(post):
    if not post or not post.get('media'):return None
    import media_pipeline
    if not s.one('SELECT id FROM media WHERE id=?',(post['media'],)):return None
    m=media_pipeline.describe(post['media'])
    if m.get('state') in {'pending','running','failed'}:return None
    return m.get('poster') if m.get('mime','').startswith('video/') else m.get('url')


def catalog(who,params):
    user=viewer(who);q=str(params.get('q','')).strip().lower()[:80]
    scope=params.get('scope','all')
    if scope not in {'all','algorithms','photos','videos'}:raise s.Problem('Unknown discovery filter')
    try:
        offset,stamp=map(int,str(params.get('cursor','0:'+str(s.now()))).split(':'))
        if not 0<=offset<=10000 or not 0<stamp<=s.now()+5:raise ValueError()
    except (ValueError,TypeError):raise s.Problem('Invalid discovery cursor')
    guard,args=social.visibility_sql(user)
    posts=s.rows('SELECT * FROM posts WHERE deleted=0 AND parent IS NULL AND created<=?'+guard+' ORDER BY created DESC,id DESC LIMIT 1000',[stamp,*args])
    # Build a light index first. Enrich only the nine visible cards: profiles,
    # settlement terms, media manifests and receipt history are never loaded
    # for every offscreen tile on each search or pagination request.
    authors={a['id']:a for a in s.rows('SELECT id,name,handle,kind,avatar,owner FROM accounts')}
    media={m['id']:m['mime'] for m in s.rows('SELECT id,mime FROM media')}
    cards=[]
    if scope in {'all','algorithms'}:
        for f in s.rows('SELECT * FROM feeds WHERE created<=? ORDER BY created DESC,id DESC LIMIT 100',(stamp,)):
            if not social.visible(user,f['owner']):continue
            author=authors.get(f['owner'])
            if not author or q and q not in (f['name']+' '+author['name']+' '+author['handle']).lower():continue
            cards.append({'id':'feed:'+f['id'],'kind':'algorithm','title':f['name'],
                'created':f['created'],'raw':f,'authorId':f['owner']})
    if scope!='algorithms':
        for p in posts:
            author=authors.get(p['author'])
            if not author or q and q not in (p['text']+' '+author['name']+' '+author['handle']).lower():continue
            mime=media.get(p.get('media'),'')
            video=mime.startswith('video/')
            if scope=='photos' and not mime.startswith('image/'):continue
            if scope=='videos' and not video:continue
            cards.append({'id':'post:'+p['id'],'kind':'video' if video else 'post',
                'title':p['text'][:160],'created':p['created'],'raw':p,'authorId':p['author']})
    cards.sort(key=lambda x:(x['kind']!='algorithm',-x['created'],x['id']))
    if scope=='all':
        feeds=[x for x in cards if x['kind']=='algorithm']
        entries=[x for x in cards if x['kind']!='algorithm']
        # Start with one row of algorithms, then actual published content.
        # Keep this order fixed for the timestamp carried by the cursor.
        cards=feeds[:3]+entries[:6]+feeds[3:]+entries[6:]
    profiles={};page=[]
    for card in cards[offset:offset+9]:
        owner=card.pop('authorId');raw=card.pop('raw')
        if owner not in profiles:profiles[owner]=s.profile(owner,user)
        author=profiles[owner];card['author']=author
        if card['kind']=='algorithm':
            info=settlement.view(raw,user)
            first=next((p for p in posts if (authors.get(p['author'],{}).get('owner') or p['author'])==owner and p['media']),None)
            art=cover(first)
            card.update(cover=art or (info.get('communityToken') or {}).get('logoURI'),coverType='media' if art else 'token',
                feed={k:info[k] for k in ('id','name','price','priceRaw','access','accessExpires','periodDays')},
                performance=performance(raw))
        else:
            art=cover(raw);token=s.GATEWAY.token_map.get(raw.get('asset')) or {}
            cached=s.one('SELECT info FROM nad_tokens WHERE address=?',(raw.get('asset'),)) if raw.get('asset') else None
            if cached:token={**token,**json.loads(cached['info'])}
            card.update(cover=art or token.get('logoURI'),coverType='media' if art else 'token',
                asset=raw.get('asset'),hasMedia=bool(art))
        page.append(card)
    return {'items':page,'cursor':str(offset+9)+':'+str(stamp) if len(cards)>offset+9 else None,
        'total':len(cards),'fetchedAt':s.now(),'viewer':user}


def preview(who,ident):
    user=viewer(who)
    if ident.startswith('post:'):
        p=social.post(ident[5:],user)
        return {'kind':'post','post':s.post_view(p,user)}
    if not ident.startswith('feed:'):raise s.Problem('Preview not found',404)
    import journey
    d=journey.preview(who,{'id':ident[5:]});f=d['feed']
    stored=s.one('SELECT * FROM feeds WHERE id=?',(f['id'],))
    alert=s.one('SELECT * FROM feed_alerts WHERE owner=? AND feed=?',(user or '',f['id']))
    return {'kind':'algorithm',**d,'creator':s.profile(stored['owner'],user),'performance':performance(stored),
        'performancePublic':bool(s.one('SELECT 1 FROM feed_performance_sharing WHERE feed=? AND owner=? AND enabled=1',(stored['id'],stored['owner']))),
        'alerts':bool(f['access'] and alert and alert['enabled'] and alert['version']==f['version'])}


def leaderboard(who,params):
    user=viewer(who);kind=params.get('kind','all')
    if kind not in {'all','human','agent'}:raise s.Problem('Unknown creator filter')
    creators={}
    for f in s.rows("SELECT * FROM feeds WHERE owner!='rally' ORDER BY created DESC LIMIT 100"):
        if not social.visible(user,f['owner']):continue
        author=s.profile(f['owner'],user)
        if kind=='agent' and author['kind']!='agent' or kind=='human' and author['kind'] not in {'person','human'}:continue
        entry=creators.setdefault(f['owner'],{'id':f['id'],'name':f['name'],'author':author,'algorithms':[],
            'performance':{'roi':None,'pnl':None,'closedTrades':0,'costBasisRaw':'0','proceedsRaw':'0','proofs':[]}})
        metric=performance(f);entry['algorithms'].append({'id':f['id'],'name':f['name']})
        if metric['roi'] is not None:
            with localcontext() as ctx:
                ctx.prec=90;out=entry['performance']
                cost=Decimal(out['costBasisRaw'])+Decimal(metric['costBasisRaw']);proceeds=Decimal(out['proceedsRaw'])+Decimal(metric['proceedsRaw'])
                out.update(costBasisRaw=str(cost),proceedsRaw=str(proceeds),roi=float((proceeds-cost)*100/cost),
                    pnl=format((proceeds-cost)/Decimal(1000000),'f'),closedTrades=out['closedTrades']+metric['closedTrades'],
                    proofs=list(dict.fromkeys(out['proofs']+metric['proofs']))[:20])
    entries=list(creators.values())
    measured=sorted([e for e in entries if e['performance']['roi'] is not None],key=lambda e:(-e['performance']['roi'],-e['performance']['closedTrades'],e['id']))
    for rank,e in enumerate(measured,1):e['rank']=rank
    return {'entries':measured,'unranked':[e for e in entries if e['performance']['roi'] is None],
        'method':'Realized ROI','windowDays':30,'currency':'USDC',
        'basis':'Recorded USDC spot trades linked to published algorithms. Network fees excluded.'}


def alerts(who,data):
    user=s.require(who,human=True);f=s.one('SELECT * FROM feeds WHERE id=?',(data.get('feed'),))
    if not f or not social.visible(user,f['owner']):raise s.Problem('Feed not found',404)
    if not isinstance(data.get('enabled'),bool):raise s.Problem('Choose whether to enable alerts')
    if data['enabled'] and not settlement.allowed(f,user):raise s.Problem('Subscribe to enable alerts',403,'subscription_required')
    s.write('''INSERT INTO feed_alerts(owner,feed,version,enabled,after_created,after_post_row)
        VALUES(?,?,?,?,?,?) ON CONFLICT(owner,feed) DO UPDATE SET version=excluded.version,
        enabled=excluded.enabled,after_created=excluded.after_created,after_post_row=excluded.after_post_row''',
        (user,f['id'],f['version'],int(data['enabled']),s.now(),s.one('SELECT coalesce(max(rowid),0) n FROM posts')['n']))
    return {'enabled':data['enabled'],'feed':f['id']}


def share_performance(who,data):
    user=s.require(who,human=True);f=s.one('SELECT * FROM feeds WHERE id=?',(data.get('feed'),))
    if not f or f['owner']!=user:raise s.Problem('Your algorithm was not found',404)
    if not isinstance(data.get('enabled'),bool):raise s.Problem('Choose whether to publish returns')
    s.write('''INSERT INTO feed_performance_sharing VALUES(?,?,?) ON CONFLICT(feed)
        DO UPDATE SET owner=excluded.owner,enabled=excluded.enabled''',(f['id'],user,int(data['enabled'])))
    return {'enabled':data['enabled'],'feed':f['id']}


def alerts_tick():
    # These are opted-in in-app alerts, not email, push or delegated trades.
    global ALERT_CURSOR
    batch=s.rows('SELECT * FROM feed_alerts WHERE enabled=1 AND (owner,feed)>(?,?) ORDER BY owner,feed LIMIT 100',ALERT_CURSOR)
    if not batch:batch=s.rows('SELECT * FROM feed_alerts WHERE enabled=1 ORDER BY owner,feed LIMIT 100')
    if batch:ALERT_CURSOR=(batch[-1]['owner'],batch[-1]['feed'])
    for a in batch:
        f=s.one('SELECT * FROM feeds WHERE id=?',(a['feed'],))
        if not f or f['version']!=a['version'] or not settlement.allowed(f,a['owner']) or not social.visible(a['owner'],f['owner']):continue
        guard,args=social.visibility_sql(a['owner'])
        p=s.one('''SELECT *,rowid AS postRow FROM posts WHERE (author=? OR author IN
            (SELECT id FROM accounts WHERE owner=?)) AND deleted=0 AND parent IS NULL
            AND rowid>?'''+guard+' ORDER BY rowid DESC LIMIT 1',[f['owner'],f['owner'],a['after_post_row'],*args])
        if not p:continue
        key='algorithm:'+a['owner']+':'+f['id']+':'+p['id']
        with s.connection() as db:
            db.execute('INSERT OR IGNORE INTO notifications(id,owner,actor,kind,post,created,dedupe) VALUES(?,?,?,?,?,?,?)',
                (s.uid(),a['owner'],p['author'],'algorithm',p['id'],s.now(),key))
            db.execute('UPDATE feed_alerts SET after_created=?,after_post_row=? WHERE owner=? AND feed=?',(p['created'],p['postRow'],a['owner'],f['id']))
