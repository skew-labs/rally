"""Feed previews and private activity links. No signing or spending authority."""
import json
import service as s
import settlement
import venues


def initialize():
    with s.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS activity_context(kind TEXT,reference TEXT,user_id TEXT,post TEXT,feed TEXT,created INTEGER,PRIMARY KEY(kind,reference))')
        db.execute('CREATE TABLE IF NOT EXISTS spot_approvals(tx TEXT PRIMARY KEY,quote_id TEXT,user_id TEXT,created INTEGER,state TEXT,receipt TEXT)')


def rank(posts, weights, watched):
    """Rank the same bounded candidates for both preview and the live timeline."""
    result=[]
    identifiers=[p['id'] for p in posts]
    likes={r['post']:r['n'] for r in s.rows("SELECT post,count(*) n FROM reactions WHERE kind='like' AND post IN ("+','.join('?' for _ in identifiers)+') GROUP BY post',identifiers)} if identifiers else {}
    for post in posts:
        parts=[weights[0]/(1+max(0,s.now()-post['created'])/3600),weights[1]*int(post['asset'] in watched),weights[2]*s.math.log1p(likes.get(post['id'],0))]
        item=dict(post)
        item['rankingReason']=['Recent post','In your watchlist','Liked by readers'][max(range(3),key=lambda i:parts[i])]
        result.append((sum(parts),item))
    return [p for _,p in sorted(result,key=lambda item:item[0],reverse=True)]


def preview(who, params):
    if who and who['grant']:s.require(who,'feed:read')
    user=who['user'] if who else None
    feed=s.one('SELECT * FROM feeds WHERE id=?',(params.get('id'),))
    if not feed:raise s.Problem('Feed not found',404)
    watched={r['asset'] for r in s.rows('SELECT asset FROM watches WHERE user_id=?',(user or '',))}
    if not user:watched=set(str(params.get('watch','')).split(',')[:114]) & set(s.GATEWAY.token_map)
    import social, algorithms
    if not social.visible(user,feed['owner']):raise s.Problem('Feed not found',404)
    guard,args=social.visibility_sql(user)
    candidates=s.rows('SELECT * FROM posts WHERE deleted=0 AND parent IS NULL'+guard+' ORDER BY created DESC,id DESC LIMIT 30',args)
    info=settlement.view(feed,user)
    limit=6 if info['access'] else 1
    viewer=who['actor'] if who and who['grant'] else user
    custom=algorithms.rank(candidates,feed,user,watched)
    ordered=custom['posts'] if custom else rank(candidates,json.loads(feed['weights']),watched)
    return {'feed':info,'posts':[s.post_view(dict(p),viewer) for p in ordered[:limit]],'latest':[s.post_view(dict(p,rankingReason='Recent post'),viewer) for p in (candidates if info['access'] else ordered)[:limit]],'previewLimit':limit,'candidateCount':len(candidates),'watchCount':len(watched)}


def validate_context(who, context):
    if context is None:return None
    s.require(who,human=True)
    if not isinstance(context,dict) or set(context)-{'post','feed'}:raise s.Problem('Invalid activity context')
    post=context.get('post');feed=context.get('feed')
    if any(value is not None and (not isinstance(value,str) or len(value)>128) for value in [post,feed]):raise s.Problem('Invalid activity context')
    if post and (not isinstance(post,str) or not s.one('SELECT 1 FROM posts WHERE id=? AND deleted=0',(post,))):raise s.Problem('Source post unavailable',404)
    if feed and (not isinstance(feed,str) or not s.one('SELECT 1 FROM feeds WHERE id=?',(feed,))):raise s.Problem('Source feed unavailable',404)
    return {'post':post,'feed':feed}


def attach(who, kind, reference, context):
    context=validate_context(who,context)
    if not context:return
    user=s.require(who,human=True)
    table={'spot':'quotes','execution':'execution_plans'}.get(kind)
    if not table or not s.one('SELECT 1 FROM '+table+' WHERE id=? AND user_id=?',(reference,user)):raise s.Problem('Activity not owned',404)
    s.write('INSERT OR IGNORE INTO activity_context VALUES(?,?,?,?,?,?)',(kind,reference,user,context['post'],context['feed'],s.now()))


def context_for(user,kind,reference):
    row=s.one('SELECT post,feed FROM activity_context WHERE kind=? AND reference=? AND user_id=?',(kind,reference,user))
    if not row:return None
    post=s.one('SELECT id,text,author,asset FROM posts WHERE id=? AND deleted=0',(row['post'],)) if row['post'] else None
    return {'post':row['post'] if post else None,'feed':row['feed'],'asset':post['asset'] if post else None,'text':post['text'][:160] if post else None,'author':s.profile(post['author'],user) if post else None}


def reconcile_spot(order):
    receipt=s.rpc('eth_getTransactionReceipt',[order['tx']])
    if not receipt:return
    canonical=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not canonical or canonical.get('hash','').lower()!=receipt.get('blockHash','').lower():return
    state='confirmed' if int(receipt['status'],16)==1 else 'failed'
    if state=='confirmed':
        final=s.rpc('eth_getBlockByNumber',['finalized',False])
        if final and int(final['number'],16)>=int(receipt['blockNumber'],16):state='finalized'
    s.write('UPDATE orders SET state=?,receipt=? WHERE id=?',(state,s.dump(receipt),order['id']))


def spot_approval(who,data):
    user=s.require(who,human=True)
    quote=s.one('SELECT * FROM quotes WHERE id=? AND user_id=?',(data.get('quote'),user))
    txhash=str(data.get('tx','')).lower()
    if not quote or not s.re.fullmatch(r'0x[0-9a-f]{64}',txhash):raise s.Problem('Approval not found',404)
    approval=json.loads(quote['payload']).get('approval')
    if not approval:raise s.Problem('This quote does not need an allowance')
    transaction=s.rpc('eth_getTransactionByHash',[txhash])
    if not transaction:return {'state':'pending','tx':txhash}
    expected='0x095ea7b3'+approval['spender'][2:].rjust(64,'0')+hex(int(quote['amount']))[2:].rjust(64,'0')
    import wallet_execution
    try:wallet_execution.verified_call(txhash,{'from':quote['wallet'],'to':approval['token'],'data':expected,'value':'0x0'},transaction)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending','tx':txhash}
        raise
    try:receipt=wallet_execution.finalized_receipt(txhash)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending','tx':txhash}
        raise
    state='confirmed' if int(receipt['status'],16)==1 else 'failed'
    if state=='confirmed':
        from eth_utils import keccak
        topic='0x'+keccak(text='Approval(address,address,uint256)').hex()
        events=[l for l in receipt.get('logs',[]) if not l.get('removed') and l['address'].lower()==approval['token'] and len(l.get('topics',[]))==3 and l['topics'][0].lower()==topic and '0x'+l['topics'][1][-40:].lower()==quote['wallet'] and '0x'+l['topics'][2][-40:].lower()==approval['spender'] and int(l.get('data','0x0'),16)==int(quote['amount'])]
        if len(events)!=1:raise s.Problem('Expected token allowance event was not verified',409)
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not block or block.get('hash','').lower()!=receipt['blockHash'].lower() or not block.get('timestamp'):raise s.Problem('Approval block time unavailable',503)
    created=int(block['timestamp'],16)
    with s.connection() as db:
        old=db.execute('SELECT user_id,quote_id FROM spot_approvals WHERE tx=?',(txhash,)).fetchone()
        if old and (old['user_id']!=user or old['quote_id']!=quote['id']):raise s.Problem('Approval already belongs to another quote',409)
        db.execute('INSERT INTO spot_approvals VALUES(?,?,?,?,?,?) ON CONFLICT(tx) DO UPDATE SET created=excluded.created,state=excluded.state,receipt=excluded.receipt',(txhash,quote['id'],user,created,state,s.dump(receipt)))
    return {'state':state,'tx':txhash}


def activity(who):
    user=s.require(who,human=True)
    errors=[]
    for kind,table,reconcile in [('spot','orders',reconcile_spot),('payment','invoices',lambda r:settlement.reconcile(r['id'])),('execution','execution_records',lambda r:venues.reconcile(r['id']))]:
        column='buyer' if kind=='payment' else 'user_id'
        for row in s.rows('SELECT * FROM '+table+' WHERE '+column+"=? AND state IN ('submitted','pending','confirmed') ORDER BY created DESC LIMIT 3",(user,)):
            try:reconcile(row)
            except Exception:errors.append(kind)
    entries=[]
    import community_tokens as ct
    for row in s.rows("SELECT * FROM community_plans WHERE owner=? AND tx IS NOT NULL ORDER BY created DESC LIMIT 30",(user,)):
        if row['state'] in {'submitted','confirmed'}:
            try:ct.reconcile(row['id']);row=s.one('SELECT * FROM community_plans WHERE id=?',(row['id'],))
            except Exception:errors.append('community')
        p=ct.plan_view(row);token=ct.public(user)
        entries.append({'id':p['id'],'kind':'community','action':p['kind'],'venue':'PancakeSwap v2','created':row['created'],'state':p['state'],'tx':p['tx'],'summary':p['summary'],'token':token['address'] if token else None})
    for row in s.rows('SELECT a.*,q.input,q.amount,q.payload FROM spot_approvals a JOIN quotes q ON q.id=a.quote_id WHERE a.user_id=? ORDER BY a.created DESC LIMIT 30',(user,)):
        p=json.loads(row['payload'])
        decimals=(s.GATEWAY.token_map.get(row['input']) or {}).get('decimals')
        amount=s.units(int(row['amount']),decimals) if decimals is not None else row['amount']+' raw units'
        entries.append({'id':row['tx'],'kind':'approval','venue':p.get('provider','Kuru'),'created':row['created'],'state':'finalized' if row['state']=='confirmed' else row['state'],'tx':row['tx'],'summary':{'input':row['input'],'amount':amount},'context':context_for(user,'spot',row['quote_id'])})
    for row in s.rows('SELECT o.*,q.payload FROM orders o JOIN quotes q ON o.quote_id=q.id WHERE o.user_id=? ORDER BY o.created DESC LIMIT 50',(user,)):
        payload=json.loads(row['payload'])
        entries.append({'id':row['id'],'kind':'spot','venue':payload.get('provider','Kuru'),'created':row['created'],'state':row['state'],'tx':row['tx'],'summary':{k:payload.get(k) for k in ['input','output','amount','receive','minimum']},'context':context_for(user,'spot',row['quote_id'])})
    for row in venues.history(who)['transactions']:
        row['context']=context_for(user,'execution',row['plan']);row['kind']='execution';entries.append(row)
    payments=settlement.history(who)
    for row in payments['purchases']:
        entries.append({**row,'kind':'payment'})
    entries.sort(key=lambda x:x['created'],reverse=True)
    return {'entries':entries[:100],'payouts':payments['payouts'],'refreshIncomplete':sorted(set(errors)),'financialSubmissions':sum(bool(x.get('tx')) for x in entries)}


def connection_status(who):
    user=s.require(who,human=True)
    items=[]
    for grant in s.rows('SELECT id,agent,scopes,expires,revoked,last_used FROM grants WHERE owner=? ORDER BY rowid DESC',(user,)):
        post=s.one('SELECT * FROM posts WHERE author=? AND deleted=0 ORDER BY created DESC,id DESC LIMIT 1',(grant['agent'],))
        items.append({**grant,'profile':s.profile(grant['agent'],user),'lastPost':s.post_view(post,user) if post else None})
    return {'connections':items}
