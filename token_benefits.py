"""Creator-owned holding tiers. Finalized, short-lived proofs; no signing authority."""
import json
import re
from decimal import Decimal, InvalidOperation
import service as s
import social

TTL=120

def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS token_benefits(owner TEXT PRIMARY KEY,token TEXT,policy TEXT,version INTEGER,updated INTEGER);
        CREATE TABLE IF NOT EXISTS holder_proofs(owner TEXT,viewer TEXT,wallet TEXT,token TEXT,balance TEXT,block INTEGER,block_hash TEXT,observed INTEGER,expires INTEGER,badge INTEGER DEFAULT 0,PRIMARY KEY(owner,viewer));
        ''')

def policy(owner):
    row=s.one('SELECT * FROM token_benefits WHERE owner=?',(owner,))
    if not row:return None
    return {**row,**json.loads(row['policy'])}

def qualification(owner,viewer):
    p=policy(owner)
    if not p or not viewer:return None
    proof=s.one('SELECT h.* FROM holder_proofs h JOIN accounts a ON a.id=h.viewer WHERE h.owner=? AND h.viewer=? AND h.wallet=a.wallet AND h.token=? AND h.expires>?',(owner,viewer,p['token'],s.now()))
    if not proof:return None
    tiers=[t for t in p['tiers'] if int(proof['balance'])>=int(t['minimumRaw'])]
    return {'tier':tiers[-1] if tiers else None,'proof':proof,'policy':p}

def access(feed,viewer):
    p=policy(feed['owner'])
    if not p:return None
    q=qualification(feed['owner'],viewer)
    if q and q['tier'] and feed['id'] in q['tier']['feeds']:return True
    return False if feed['id'] in p['gatedFeeds'] else None

def price(feed,viewer):
    q=qualification(feed['owner'],viewer)
    discount=q['tier']['discountBps'] if q and q['tier'] else 0
    original=int(feed.get('price_raw') or 0)
    # A discount is a checkout price, not a zero-value payment with no proof.
    return {'amountRaw':str(original*(10000-discount)//10000),'discountBps':discount,'originalRaw':str(original)}

def public(owner,viewer):
    if not social.visible(viewer,owner):raise s.Problem('Community not found',404)
    p=policy(owner);q=qualification(owner,viewer)
    return {'owner':owner,'token':p['token'] if p else None,'version':p['version'] if p else 0,
        'tiers':p['tiers'] if p else [],'gatedFeeds':p['gatedFeeds'] if p else [],
        'tier':q['tier'] if q else None,'verified':bool(q),'observedBlock':q['proof']['block'] if q else None,
        'expires':q['proof']['expires'] if q else None,'showBadge':bool(q and q['proof']['badge']),
        'editable':viewer==owner}

def save(who,data):
    owner=s.require(who,human=True)
    token=__import__('community_tokens').public(owner)
    if not token:raise s.Problem('Launch your community token before setting benefits',409)
    tiers=data.get('tiers');gated=data.get('gatedFeeds',[])
    owned={f['id'] for f in s.rows('SELECT id FROM feeds WHERE owner=?',(owner,))}
    if not isinstance(gated,list) or len(gated)>50 or any(not isinstance(f,str) or f not in owned for f in gated):raise s.Problem('Choose your own feeds')
    if not isinstance(tiers,list) or not 0<=len(tiers)<=5:raise s.Problem('Choose up to five tiers')
    result=[];last=-1
    for t in tiers:
        if not isinstance(t,dict):raise s.Problem('Invalid tier')
        label=t.get('label','');feeds=t.get('feeds',[]);discount=t.get('discountBps',0)
        try:
            amount=Decimal(str(t.get('minimum','')));raw=amount*10**18
            if not amount.is_finite() or raw!=int(raw) or int(raw)<=last or amount<=0 or amount>10**30:raise ValueError()
        except (InvalidOperation,ValueError,OverflowError):raise s.Problem('Holdings must increase from one tier to the next')
        if not isinstance(label,str) or not label.strip() or len(label)>28 or type(discount)is not int or not 0<=discount<=9000:raise s.Problem('Choose a short tier name and a discount up to 90%')
        if not isinstance(feeds,list) or len(feeds)>50 or any(not isinstance(f,str) or f not in owned for f in feeds):raise s.Problem('Choose your own feeds')
        last=int(raw);result.append({'label':label.strip(),'minimum':s.units(last,18),'minimumRaw':str(last),'discountBps':discount,'feeds':sorted(set(feeds))})
    payload=s.dump({'tiers':result,'gatedFeeds':sorted(set(gated))})
    with s.connection() as db:
        db.execute('INSERT INTO token_benefits VALUES(?,?,?,1,?) ON CONFLICT(owner) DO UPDATE SET token=excluded.token,policy=excluded.policy,version=version+1,updated=excluded.updated',(owner,token['address'],payload,s.now()))
    return public(owner,owner)

def refresh(who,data):
    viewer=s.require(who,human=True);owner=str(data.get('owner',''));p=policy(owner)
    if not p or not social.visible(viewer,owner):raise s.Problem('Community benefits not found',404)
    wallet=(s.one('SELECT wallet FROM accounts WHERE id=?',(viewer,)) or {}).get('wallet')
    if not wallet:raise s.Problem('Connect your wallet to check holdings',409,'wallet_required')
    old=s.one('SELECT * FROM holder_proofs WHERE owner=? AND viewer=?',(owner,viewer))
    if old and old['wallet']==wallet and old['token']==p['token'] and old['observed']>s.now()-10:return public(owner,viewer)
    block=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not block or not re.fullmatch(r'0x[0-9a-fA-F]{64}',str(block.get('hash',''))):raise s.Problem('Finalized holdings unavailable',503)
    value=s.rpc('eth_call',[{'to':p['token'],'data':'0x70a08231'+wallet[2:].rjust(64,'0')},block['number']])
    if not isinstance(value,str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}',value):raise s.Problem('Holdings unavailable',503)
    # A wallet or policy change while the read is in flight cannot grant access.
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT wallet FROM accounts WHERE id=?',(viewer,)).fetchone()
        current_policy=db.execute('SELECT token,version FROM token_benefits WHERE owner=?',(owner,)).fetchone()
        if current['wallet']!=wallet or current_policy['token']!=p['token'] or current_policy['version']!=p['version']:raise s.Problem('Community or wallet changed. Check holdings again.',409)
        db.execute('INSERT INTO holder_proofs(owner,viewer,wallet,token,balance,block,block_hash,observed,expires,badge) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,viewer) DO UPDATE SET wallet=excluded.wallet,token=excluded.token,balance=excluded.balance,block=excluded.block,block_hash=excluded.block_hash,observed=excluded.observed,expires=excluded.expires',
            (owner,viewer,wallet,p['token'],str(int(value,16)),int(block['number'],16),block['hash'],s.now(),s.now()+TTL,old['badge'] if old else 0))
    return public(owner,viewer)

def badge(who,data):
    viewer=s.require(who,human=True)
    if type(data.get('enabled'))is not bool:raise s.Problem('Choose badge visibility')
    s.write('UPDATE holder_proofs SET badge=? WHERE viewer=? AND owner=?',(int(data['enabled']),viewer,str(data.get('owner',''))))
    return public(str(data.get('owner','')),viewer)

def badges(viewer):
    out=[]
    for row in s.rows('SELECT owner FROM holder_proofs WHERE viewer=? AND badge=1 AND expires>? LIMIT 5',(viewer,s.now())):
        q=qualification(row['owner'],viewer)
        if q and q['tier']:out.append({'community':row['owner'],'label':q['tier']['label'],'expires':q['proof']['expires']})
    return out

def tick():
    # Refresh only recently active proofs, with a strict bound on provider reads.
    for row in s.rows('SELECT owner,viewer FROM holder_proofs WHERE expires<? AND observed>? ORDER BY observed LIMIT 2',(s.now()+30,s.now()-600)):
        try:refresh({'user':row['viewer'],'actor':row['viewer'],'grant':None},row)
        except Exception:pass
