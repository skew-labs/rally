"""Owner-bound Agent Wallet identity relay. It never prepares transactions."""
import hashlib,json,os,re,secrets,stat
from pathlib import Path
from eth_account import Account
from eth_account.messages import encode_defunct
import service as s
import wallet_auth

COOKIE='rally_agent_device'
ACTIVE=('prepared','queued','starting','waiting','uncertain','verified')
CONFIG=Path(os.environ.get('RALLY_AGENT_BRIDGE_CONFIG',str(s.STATE/'agent-wallet-bridge.json')))

def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS agent_wallet_links(owner TEXT PRIMARY KEY,address TEXT UNIQUE,origin TEXT,verified INTEGER);
        CREATE TABLE IF NOT EXISTS agent_wallet_devices(hash TEXT PRIMARY KEY,owner TEXT,address TEXT,origin TEXT,expires INTEGER);
        CREATE TABLE IF NOT EXISTS agent_wallet_requests(id TEXT PRIMARY KEY,owner TEXT,address TEXT,origin TEXT,purpose TEXT,message TEXT,expires INTEGER,state TEXT,polling_id TEXT,notice TEXT DEFAULT '',auth_method TEXT DEFAULT '',approval_expires INTEGER,created INTEGER,updated INTEGER,revoked INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS agent_wallet_owner_requests ON agent_wallet_requests(owner,created);
        ''')

def profiles():
    if not CONFIG.exists():return {}
    if stat.S_IMODE(CONFIG.stat().st_mode)&0o077:raise RuntimeError('Agent bridge config must be private')
    data=json.loads(CONFIG.read_text())
    if not isinstance(data,dict):raise RuntimeError('Invalid agent bridge config')
    result={}
    for owner,p in data.get('profiles',{}).items():
        if not re.fullmatch(r'[a-zA-Z0-9_]{1,80}',owner) or not isinstance(p,dict):raise RuntimeError('Invalid agent bridge owner')
        address=str(p.get('address','')).lower()
        if not re.fullmatch(r'0x[0-9a-f]{40}',address) or address==s.ZERO or p.get('origin')!='https://rallydot.com':raise RuntimeError('Invalid paired agent identity')
        result[owner]={**p,'address':address}
    return result

def owner_for(who,device,origin):
    if who:
        owner=s.require(who,human=True)
        account=s.one('SELECT kind FROM accounts WHERE id=?',(owner,))
        if not account or account['kind']!='person':raise s.Problem('Use your personal account',403)
        return owner
    if device:
        row=s.one('SELECT * FROM agent_wallet_devices WHERE hash=? AND expires>? AND origin=?',(s.digest(device),s.now(),origin))
        if row:return row['owner']
    raise s.Problem('Sign in once to pair your agent wallet on this device',401,'agent_pairing_required')

def paired(who,device,origin):
    owner=owner_for(who,device,origin);profile=profiles().get(owner)
    if not profile or profile['origin']!=origin:raise s.Problem('Pair a MetaMask Agent Wallet runtime with your account first',409,'agent_bridge_unpaired')
    if not who:
        row=s.one('SELECT * FROM agent_wallet_devices WHERE hash=? AND owner=? AND address=? AND origin=? AND expires>?',(s.digest(device),owner,profile['address'],origin,s.now()))
        if not row:raise s.Problem('Pair your agent wallet again',401,'agent_pairing_required')
    return owner,profile

def config(who,device,origin):
    try:owner,p=paired(who,device,origin)
    except s.Problem as e:return {'provider':'metamask','available':False,'connected':False,'reason':e.code,'chainId':143}
    link=s.one('SELECT * FROM agent_wallet_links WHERE owner=? AND address=? AND origin=?',(owner,p['address'],origin))
    return {'provider':'metamask','available':True,'connected':bool(link),'address':p['address'],'chainId':143,'mode':'guard','signing':'paired_runtime'}

def snapshot(row):
    return {'id':row['id'],'address':row['address'],'purpose':row['purpose'],'message':row['message'],'messageHash':hashlib.sha256(row['message'].encode()).hexdigest(),'chainId':143,'expires':row['expires'],'state':row['state'],'pollingId':row['polling_id'],'notice':row['notice'],'authMethod':row['auth_method'],'approvalExpires':row['approval_expires'],'revoked':bool(row['revoked'])}

def request_for(who,device,origin,ident):
    owner,p=paired(who,device,origin)
    row=s.one('SELECT * FROM agent_wallet_requests WHERE id=? AND owner=? AND address=? AND origin=?',(str(ident),owner,p['address'],origin))
    if not row:raise s.Problem('Connection request not found',404)
    return row

def prepare(who,device,origin):
    owner,p=paired(who,device,origin)
    purpose='link_wallet' if who else 'sign_in'
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM agent_wallet_requests WHERE owner=? AND origin=? AND state IN (?,?,?,?,?,?) ORDER BY created DESC LIMIT 1',(owner,origin,*ACTIVE)).fetchone()
        if row:
            if row['expires']<=s.now() and row['state'] in {'prepared','queued','verified'}:
                db.execute("UPDATE agent_wallet_requests SET state='expired',updated=? WHERE id=?",(s.now(),row['id']))
            else:return snapshot(row)
        ident,address,msg,expires=wallet_auth._proof({'address':p['address']},origin,'Connect this agent wallet to your Rally account.' if who else 'Sign in to Rally with your paired agent wallet.')
        db.execute('INSERT INTO agent_wallet_requests(id,owner,address,origin,purpose,message,expires,state,created,updated) VALUES(?,?,?,?,?,?,?,\'prepared\',?,?)',(ident,owner,address,origin,purpose,msg,expires,s.now(),s.now()))
        return snapshot(db.execute('SELECT * FROM agent_wallet_requests WHERE id=?',(ident,)).fetchone())

def start(who,device,origin,data):
    row=request_for(who,device,origin,data.get('id'))
    if row['revoked']:raise s.Problem('Connection removed',409)
    if data.get('messageHash')!=hashlib.sha256(row['message'].encode()).hexdigest():raise s.Problem('Connection message changed',409)
    if row['expires']<=s.now():raise s.Problem('Connection request expired',409)
    s.write("UPDATE agent_wallet_requests SET state='queued',updated=? WHERE id=? AND state='prepared'",(s.now(),row['id']))
    return snapshot(request_for(who,device,origin,row['id']))

def status(who,device,origin,ident):
    row=request_for(who,device,origin,ident);result=snapshot(row)
    if row['expires']<=s.now() and row['state'] in {'prepared','queued','verified'}:result['state']='expired'
    return result

def notice(ident,data):
    if data.get('kind')!='AWAITING_MFA':return
    polling=str(data.get('pollingId',''))
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',polling):raise RuntimeError('Missing pending request identity')
    message=str(data.get('message',''))[:1600]
    if any(x in message for x in ['eyJ','ory_rt_','privy_app_secret','Bearer ']):message='Approve the existing request in MetaMask.'
    expires=data.get('expiresAt');expiry=None
    if isinstance(expires,str):
        try:
            from datetime import datetime
            expiry=int(datetime.fromisoformat(expires.replace('Z','+00:00')).timestamp())
        except ValueError:pass
    s.write("UPDATE agent_wallet_requests SET state='waiting',polling_id=?,notice=?,auth_method=?,approval_expires=?,updated=? WHERE id=? AND state IN ('starting','waiting','uncertain')",(polling,message,str(data.get('authMethod',''))[:50],expiry,s.now(),ident))

def verified(ident,signature):
    row=s.one('SELECT * FROM agent_wallet_requests WHERE id=?',(ident,))
    if not row or row['revoked'] or row['expires']<=s.now() or row['state'] not in {'starting','waiting','uncertain'}:raise s.Problem('Connection request is no longer valid',409)
    if not re.fullmatch(r'0x[0-9a-fA-F]{130}',str(signature)):raise s.Problem('Invalid agent signature',401)
    try:address=Account.recover_message(encode_defunct(text=row['message']),signature=signature).lower()
    except Exception:raise s.Problem('Could not verify the agent signature',401)
    if address!=row['address']:raise s.Problem('Agent signature does not match the paired wallet',401)
    p=profiles().get(row['owner'])
    if not p or p['address']!=address or p['origin']!=row['origin']:raise s.Problem('Paired wallet changed',409)
    s.write("UPDATE agent_wallet_requests SET state='verified',updated=? WHERE id=? AND revoked=0 AND expires>? AND state IN ('starting','waiting','uncertain')",(s.now(),ident,s.now()))

def complete(who,device,origin,ident):
    row=request_for(who,device,origin,ident);owner=row['owner']
    token=None;ticket=secrets.token_urlsafe(40)
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM agent_wallet_requests WHERE id=?',(ident,)).fetchone()
        if row['state']=='completed' and who:return {'connected':True,'address':row['address']},None,None
        if row['state']!='verified' or row['revoked'] or row['expires']<=s.now():raise s.Problem('Complete the existing MetaMask approval first',409)
        existing=db.execute('SELECT owner FROM agent_wallet_links WHERE address=?',(row['address'],)).fetchone()
        primary=db.execute('SELECT id FROM accounts WHERE wallet=? AND id!=?',(row['address'],owner)).fetchone()
        if existing and existing['owner']!=owner or primary:raise s.Problem('This agent wallet belongs to another account',409)
        db.execute('INSERT INTO agent_wallet_links VALUES(?,?,?,?) ON CONFLICT(owner) DO UPDATE SET address=excluded.address,origin=excluded.origin,verified=excluded.verified',(owner,row['address'],origin,s.now()))
        db.execute('INSERT INTO agent_wallet_devices VALUES(?,?,?,?,?)',(s.digest(ticket),owner,row['address'],origin,s.now()+30*86400))
        if row['purpose']=='sign_in':
            token=secrets.token_urlsafe(40);db.execute('INSERT INTO sessions VALUES(?,?,?)',(s.digest(token),owner,s.now()+7*86400))
        db.execute("UPDATE agent_wallet_requests SET state='completed',updated=? WHERE id=?",(s.now(),ident))
    return {'connected':True,'address':row['address']},token,ticket

def disconnect(who,origin):
    owner=s.require(who,human=True)
    with s.connection() as db:
        db.execute('DELETE FROM agent_wallet_links WHERE owner=? AND origin=?',(owner,origin))
        db.execute('DELETE FROM agent_wallet_devices WHERE owner=? AND origin=?',(owner,origin))
        db.execute("UPDATE agent_wallet_requests SET revoked=1,state=CASE WHEN state IN ('prepared','queued','verified','completed') THEN 'revoked' ELSE state END,updated=? WHERE owner=? AND origin=?",(s.now(),owner,origin))
    return {'connected':False}
