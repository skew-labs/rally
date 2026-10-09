"""Shared Rally services. External agents use the same authorization as the web app."""
import base64
import csv
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('RALLY_STATE_DIR', str(ROOT / 'private')))
STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
(STATE / 'media').mkdir(mode=0o700, exist_ok=True)
DB = STATE / 'rally.sqlite3'
ZERO = '0x' + '0'*40
USDC = '0x754704bc059f8c67012fed69bc8a327a5aafb603'
FLOW = '0xb3e6778480b2e488385e8205ea05e20060b813cb'
FLOW_INNER = '0x2f84fb8982073f39ba47c7fcc29119af074abbcb'  # Observed entry-point getRouter(), 2026-10-01.
MULTICALL = '0xca11bde05977b3631167028862be2a173976ca11'
SCOPES = {'feed:read', 'posts:write', 'replies:write', 'media:upload', 'markets:read'}
LOCK = threading.RLock()
RPC_URL = os.environ.get('RALLY_RPC_URL', 'https://rpc.monad.xyz').strip()
RPC_NETWORK_LOCK = threading.Lock()
RPC_CHECKED_AT = 0.0
RPC_REQUEST_LOCK = threading.Lock()
RPC_REQUEST_AT = 0.0


class Problem(Exception):
    def __init__(self, message, status=400, code='invalid_request'):
        super().__init__(message)
        self.status, self.code = status, code


def uid(): return uuid.uuid4().hex
def now(): return int(time.time())
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def dump(value): return json.dumps(value, separators=(',', ':'), allow_nan=False)
def units(raw,decimals):
    digits=str(int(raw)).rjust(decimals+1,'0')
    return digits if not decimals else (digits[:-decimals]+'.'+digits[-decimals:]).rstrip('0').rstrip('.')


@contextmanager
def connection():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:yield db
    finally:db.close()


def rows(sql, args=()):
    with connection() as db: return [dict(x) for x in db.execute(sql, args)]


def one(sql, args=()):
    data = rows(sql, args)
    return data[0] if data else None


def write(sql, args=()):
    with connection() as db: return db.execute(sql, args).rowcount


def initialize():
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,handle TEXT UNIQUE,name TEXT,pw TEXT,kind TEXT,owner TEXT,bio TEXT DEFAULT '',avatar TEXT DEFAULT '',wallet TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user_id TEXT,expires INTEGER);
        CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY,owner TEXT,agent TEXT,hash TEXT UNIQUE,scopes TEXT,expires INTEGER,revoked INTEGER DEFAULT 0,last_used INTEGER);
        CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY,author TEXT,text TEXT,media TEXT,asset TEXT,community TEXT,parent TEXT,source TEXT,created INTEGER,deleted INTEGER DEFAULT 0,idem TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS reactions(user_id TEXT,post TEXT,kind TEXT,PRIMARY KEY(user_id,post,kind));
        CREATE TABLE IF NOT EXISTS follows(user_id TEXT,target TEXT,PRIMARY KEY(user_id,target));
        CREATE TABLE IF NOT EXISTS communities(id TEXT PRIMARY KEY,name TEXT,description TEXT);
        CREATE TABLE IF NOT EXISTS members(user_id TEXT,community TEXT,PRIMARY KEY(user_id,community));
        CREATE TABLE IF NOT EXISTS feeds(id TEXT PRIMARY KEY,owner TEXT,name TEXT,weights TEXT,assets TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS settings(user_id TEXT PRIMARY KEY,feed TEXT DEFAULT 'latest');
        CREATE TABLE IF NOT EXISTS watches(user_id TEXT,asset TEXT,PRIMARY KEY(user_id,asset));
        CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,owner TEXT,actor TEXT,path TEXT,mime TEXT,size INTEGER,created INTEGER);
        CREATE TABLE IF NOT EXISTS uploads(hash TEXT PRIMARY KEY,owner TEXT,actor TEXT,expires INTEGER,used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY,user_id TEXT,address TEXT,message TEXT,expires INTEGER,used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY,user_id TEXT,wallet TEXT,input TEXT,output TEXT,amount TEXT,payload TEXT,expires INTEGER);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user_id TEXT,quote_id TEXT UNIQUE,tx TEXT UNIQUE,state TEXT,receipt TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY,name TEXT,redirects TEXT);
        CREATE TABLE IF NOT EXISTS agent_clients(owner TEXT,client TEXT,agent TEXT,PRIMARY KEY(owner,client));
        CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY,user_id TEXT,agent TEXT,client TEXT,redirect TEXT,challenge TEXT,scopes TEXT,expires INTEGER,used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT,owner TEXT,actor TEXT,object_id TEXT,created INTEGER);
        CREATE INDEX IF NOT EXISTS posts_timeline ON posts(created DESC,id DESC) WHERE deleted=0 AND parent IS NULL;
        CREATE INDEX IF NOT EXISTS posts_threads ON posts(parent,created) WHERE deleted=0;
        CREATE INDEX IF NOT EXISTS posts_author ON posts(author,created);
        CREATE INDEX IF NOT EXISTS reactions_post ON reactions(post,kind);
        CREATE INDEX IF NOT EXISTS follows_target ON follows(target);
        CREATE INDEX IF NOT EXISTS accounts_owner ON accounts(owner);
        CREATE INDEX IF NOT EXISTS media_owner ON media(owner);
        ''')
        if 'grant_id' not in [x[1] for x in db.execute('PRAGMA table_info(uploads)')]:
            db.execute('ALTER TABLE uploads ADD COLUMN grant_id TEXT')
        if 'grant_id' not in [x[1] for x in db.execute('PRAGMA table_info(audit)')]:
            db.execute('ALTER TABLE audit ADD COLUMN grant_id TEXT')
        db.execute('UPDATE posts SET asset=? WHERE asset=?',('MON',ZERO))
        db.execute('INSERT OR IGNORE INTO watches SELECT user_id,? FROM watches WHERE asset=?',('MON',ZERO))
        db.execute('DELETE FROM watches WHERE asset=?',(ZERO,))
        db.execute('INSERT OR IGNORE INTO accounts(id,handle,name,pw,kind,created,avatar) VALUES(?,?,?,?,?,?,?)', ('rally','rally','Rally',None,'service',now(),'/assets/favicon.svg'))
        for item in [('monad','Monad builders','Building on Monad'),('studio','The studio','People, agents and creative work')]:
            db.execute('INSERT OR IGNORE INTO communities VALUES(?,?,?)', item)
        for ident, name, weights in [('latest','Latest',[100,0,0]),('community','Watchlist',[30,60,10]),('signals','Popular',[30,10,60])]:
            db.execute('INSERT OR IGNORE INTO feeds(id,owner,name,weights,assets,created) VALUES(?,?,?,?,?,?)',(ident,'rally',name,dump(weights),'[]',now()))
        for ident,old,name in [('community','Community','Watchlist'),('signals','Signals','Popular')]:
            db.execute('UPDATE feeds SET name=? WHERE id=? AND owner=? AND name=?',(name,ident,'rally',old))
        # Curated source links, not fabricated people, engagement or agent activity.
        for ident,text,asset,url in [
            ('source-usdt0','USDT0 and XAUt0 are live on Monad','0x01bff41798a0bcf287b996046ca68b395dbc1071','https://blog.usdt0.to/usdt0-and-xaut0-are-now-live-on-monad'),
            ('source-kuru','Kuru Flow: Monad liquidity in one route','MON','https://docs.kuru.io/kuru-flow/flow-overview'),
            ('source-perpl','Perpl markets','MON','https://docs.perpl.xyz')]:
            db.execute('INSERT OR IGNORE INTO posts(id,author,text,asset,source,created) VALUES(?,?,?,?,?,?)',(ident,'rally',text,asset,url,now()))
    os.chmod(DB, 0o600)
    import settlement
    settlement.initialize()
    import venues
    venues.initialize()
    import journey
    journey.initialize()
    import nadfun
    nadfun.initialize()
    import social, algorithms, oauth_sessions, wallet_auth, privy_auth
    social.initialize(); algorithms.initialize(); oauth_sessions.initialize(); wallet_auth.initialize(); privy_auth.initialize()
    import media_pipeline
    media_pipeline.initialize()
    import community_tokens
    community_tokens.initialize()
    import launchpad
    launchpad.initialize()
    import nad_revenue
    nad_revenue.initialize()


def profile(ident, viewer=None):
    p = one('SELECT id,handle,name,kind,owner,bio,avatar,created FROM accounts WHERE id=? OR handle=?',(ident,ident))
    if not p: raise Problem('Profile not found',404)
    import social, community_tokens, launchpad
    if not social.visible(viewer,p['id']):raise Problem('Profile not found',404)
    p['followers'] = one('SELECT count(*) n FROM follows WHERE target=?',(p['id'],))['n']
    p['following'] = bool(viewer and one('SELECT 1 FROM follows WHERE user_id=? AND target=?',(viewer,p['id'])))
    if p['owner']: p['operator'] = one('SELECT id,handle,name FROM accounts WHERE id=?',(p['owner'],))
    p['communityToken']=community_tokens.public(p['owner'] or p['id'])
    p['launchTokens']=launchpad.owned(p['id'])
    return p


def identity(cookie='', bearer=''):
    if bearer:
        grant = one('SELECT * FROM grants WHERE hash=? AND revoked=0 AND expires>?',(digest(bearer),now()))
        if not grant: raise Problem('Connection expired or revoked',401,'invalid_token')
        write('UPDATE grants SET last_used=? WHERE id=?',(now(),grant['id']))
        return {'user':grant['owner'],'actor':grant['agent'],'scopes':set(json.loads(grant['scopes'])),'grant':grant['id']}
    if cookie:
        session = one('SELECT * FROM sessions WHERE hash=? AND expires>?',(digest(cookie),now()))
        if session: return {'user':session['user_id'],'actor':session['user_id'],'scopes':SCOPES,'grant':None}
    return None


def require(who, scope=None, human=False):
    if not who: raise Problem('Sign in to continue',401,'sign_in_required')
    if scope and scope not in who['scopes']: raise Problem('This connection does not have permission',403,'scope_required')
    if human and who['grant']: raise Problem('Your account must approve this action',403)
    return who['user']


def password_hash(password, salt=None):
    if not isinstance(password,str) or len(password)<10 or len(password)>256: raise Problem('Use a password of at least 10 characters')
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()
    return salt + ':' + value


def session_for(user):
    token = secrets.token_urlsafe(40)
    write('INSERT INTO sessions VALUES(?,?,?)',(digest(token),user,now()+86400*7))
    return token


def login(data, register=False):
    handle = str(data.get('handle','')).lower().strip()
    password = data.get('password','')
    if not re.fullmatch(r'[a-z0-9_]{3,24}',handle): raise Problem('Use 3–24 letters, numbers or underscores')
    if register:
        hashed = password_hash(password)
        ident = uid()
        try: write('INSERT INTO accounts(id,handle,name,pw,kind,created) VALUES(?,?,?,?,?,?)',(ident,handle,str(data.get('name') or handle)[:48],hashed,'person',now()))
        except sqlite3.IntegrityError: raise Problem('That username is taken',409)
        write('INSERT INTO follows VALUES(?,?)',(ident,'rally'))
        return profile(ident), session_for(ident)
    p = one('SELECT * FROM accounts WHERE handle=?',(handle,))
    if not p or not p['pw']:
        password_hash(str(password) if len(str(password))>=10 else 'invalid_password')
        raise Problem('Username or password is incorrect',401)
    if not hmac.compare_digest(password_hash(password,p['pw'].split(':')[0]),p['pw']): raise Problem('Username or password is incorrect',401)
    return profile(p['id']),session_for(p['id'])


def audit(event,who,object_id):
    write('INSERT INTO audit(event,owner,actor,object_id,created,grant_id) VALUES(?,?,?,?,?,?)',(event,who['user'],who['actor'],object_id,now(),who['grant']))


def post_view(p,viewer=None):
    import social
    if not social.visible(viewer,p['author']):raise Problem('Post not found',404)
    p['author'] = profile(p['author'],viewer)
    if p.get('asset'):
        launch=one('SELECT info FROM nad_tokens WHERE address=?',(p['asset'],))
        if launch:
            p['assetInfo']=json.loads(launch['info'])
            if now()-p['assetInfo'].get('referenceAt',0)>180:p['assetInfo']['price']=None
    for kind in ('like','save'):
        p[kind+'d' if kind=='like' else 'saved'] = bool(viewer and one('SELECT 1 FROM reactions WHERE user_id=? AND post=? AND kind=?',(viewer,p['id'],kind)))
    p['likes'] = one("SELECT count(*) n FROM reactions WHERE post=? AND kind='like'",(p['id'],))['n']
    p['replies'] = one('SELECT count(*) n FROM posts WHERE parent=? AND deleted=0',(p['id'],))['n']
    if p['media']:
        import media_pipeline
        p['media'] = media_pipeline.describe(p['media']) if one('SELECT id FROM media WHERE id=?',(p['media'],)) else None
    return social.extras(p,viewer)


def get_feed(who,params):
    viewer = who['user'] if who else None
    if who and who['grant']: require(who,'feed:read')
    mode=params.get('mode','for-you');feed_id=params.get('feed','latest');community=params.get('community');author=params.get('author');cursor=params.get('cursor')
    import social
    guard,args=social.visibility_sql(viewer)
    bump='created';bump_args=[]
    if author:
        profile(author,viewer)
        bump='max(created,coalesce((SELECT max(r.created) FROM reposts r WHERE r.post=posts.id AND r.owner=?),0))';bump_args=[author]
    elif mode=='following' and viewer:
        bump='max(created,coalesce((SELECT max(r.created) FROM reposts r WHERE r.post=posts.id AND r.owner IN (SELECT target FROM follows WHERE user_id=?)),0))';bump_args=[viewer]
    sql='SELECT posts.*,'+bump+' AS feedAt FROM posts WHERE deleted=0 AND parent IS NULL'+guard
    if community:sql+=' AND community=?';args.append(community)
    if author:sql+=' AND (author=? OR id IN (SELECT post FROM reposts WHERE owner=?))';args.extend([author,author])
    if mode=='following':
        require(who);sql+=' AND (author IN (SELECT target FROM follows WHERE user_id=?) OR id IN (SELECT post FROM reposts WHERE owner IN (SELECT target FROM follows WHERE user_id=?)))';args.extend([viewer,viewer])
    if mode=='saved':
        require(who,human=True);sql+=" AND id IN (SELECT post FROM reactions WHERE user_id=? AND kind='save')";args.append(viewer)
    if mode=='agents':sql+=" AND author IN (SELECT id FROM accounts WHERE kind='agent')"
    if cursor:
        try:ts,ident=cursor.split(':',1);ts=int(ts)
        except Exception:raise Problem('Invalid page cursor')
        sql+=' AND (feedAt<? OR (feedAt=? AND id<?))';args.extend([ts,ts,ident])
    data=rows(sql+' ORDER BY feedAt DESC,id DESC LIMIT 31',bump_args+args)
    has_more=len(data)>30;data=data[:30]
    f=one('SELECT * FROM feeds WHERE id=?',(feed_id,))
    if f and not social.visible(viewer,f['owner']):raise Problem('Feed not found',404)
    if f and mode=='for-you':
        from settlement import allowed
        if not allowed(f,viewer):raise Problem('Subscribe to use this feed',403,'subscription_required')
    algorithm_run=None
    if f and feed_id!='latest' and mode=='for-you':
        weights=json.loads(f['weights']);watched=set(x['asset'] for x in rows('SELECT asset FROM watches WHERE user_id=?',(viewer or '',)))
        if not viewer:watched=set(str(params.get('watch','')).split(',')[:114]) & set(GATEWAY.token_map)
        from journey import rank
        import algorithms
        custom=algorithms.rank(data,f,viewer,watched,record=bool(viewer) and params.get('observe')!='0')
        if custom:data=custom['posts'];algorithm_run=custom['run']
        else:data=rank(data,weights,watched)
    last=rows(sql+' ORDER BY feedAt DESC,id DESC LIMIT 30',bump_args+args)[-1] if has_more else None
    viewed=[]
    for p in data:
        if p['feedAt']>p['created']:
            if author:rep=one('SELECT owner FROM reposts WHERE post=? AND owner=? ORDER BY created DESC LIMIT 1',(p['id'],author))
            else:rep=one('SELECT owner FROM reposts WHERE post=? AND owner IN (SELECT target FROM follows WHERE user_id=?) ORDER BY created DESC LIMIT 1',(p['id'],viewer))
            if rep and social.visible(viewer,rep['owner']):p['repostedBy']=profile(rep['owner'],viewer)
        viewed.append(post_view(p,who['actor'] if who and who['grant'] else viewer))
    return {'algorithmRun':algorithm_run,'posts':viewed,'cursor':str(last['feedAt'])+':'+last['id'] if last else None}


def publish(who,data,key=''):
    require(who,'replies:write' if data.get('parent') else 'posts:write')
    text=str(data.get('text','')).strip();media=data.get('media');parent=data.get('parent');asset=data.get('asset');community=data.get('community')
    if not community and not parent:
        import community_tokens
        own=community_tokens.public(who['user'])
        if own:
            community=own['community']
            if not asset:community_tokens.register_asset(who['user']);asset=own['address']
    if len(text)>4000 or not(text or media):raise Problem('Add text, a photo or a video')
    if media and not one('SELECT 1 FROM media WHERE id=? AND owner=? AND actor=?',(media,who['user'],who['actor'])):raise Problem('Media does not belong to this profile',403)
    if parent:
        import social
        social.post(parent,who['user'])
    if community and not one('SELECT 1 FROM members WHERE user_id=? AND community=?',(who['user'],community)):raise Problem('Join this community before posting',403)
    if asset and asset not in GATEWAY.token_map:
        import nadfun
        row=one('SELECT info FROM nad_tokens WHERE address=?',(asset,))
        if not row:raise Problem('Unknown Monad asset')
        GATEWAY.token_map[asset]=json.loads(row['info'])
    if one('SELECT count(*) n FROM posts WHERE author=? AND created>?',(who['actor'],now()-86400))['n']>=100:raise Problem('Daily posting limit reached',429)
    idem=who['actor']+':'+key if key and len(key)<=128 else None
    ident=uid()
    try:write('INSERT INTO posts(id,author,text,media,asset,community,parent,created,idem) VALUES(?,?,?,?,?,?,?,?,?)',(ident,who['actor'],text,media,asset,community,parent,now(),idem))
    except sqlite3.IntegrityError:
        existing=one('SELECT * FROM posts WHERE idem=?',(idem,))
        if not existing or any(existing[k]!=(v or None) for k,v in [('media',media),('asset',asset),('community',community),('parent',parent)]) or existing['text']!=text:raise Problem('Request key already used for another post',409)
        return post_view(existing,who['actor'])
    if parent:
        import social
        social.notify(who['actor'],social.post(parent,who['user'])['author'],'reply',ident)
    audit('post.publish',who,ident)
    return post_view(one('SELECT * FROM posts WHERE id=?',(ident,)),who['actor'])


def new_grant(who,data):
    owner=require(who,human=True)
    name=str(data.get('name','')).strip();handle=str(data.get('handle','')).lower()
    brand_avatars={'codex':'/assets/agent-openai.svg','claude':'/assets/agent-claude.png','hermes':'/assets/agent-hermes.png','muse':'/assets/agent-meta.svg','grok':'/assets/agent-grok.svg'}
    provider=data.get('provider','')
    if not isinstance(provider,str) or provider and provider not in brand_avatars:raise Problem('Choose a supported agent')
    avatar=brand_avatars.get(provider,'')
    scopes=set(data.get('scopes',[]))
    if not name or not re.fullmatch(r'[a-z0-9_]{3,24}',handle) or not scopes or not scopes<=SCOPES:raise Problem('Choose a name, username and permissions')
    ident,agent,token=uid(),uid(),secrets.token_urlsafe(40)
    if one('SELECT count(*) n FROM grants WHERE owner=? AND revoked=0',(owner,))['n']>=20:raise Problem('Connection limit reached',429)
    with connection() as db:
        try:db.execute('INSERT INTO accounts(id,handle,name,kind,owner,avatar,created) VALUES(?,?,?,?,?,?,?)',(agent,handle,name[:48],'agent',owner,avatar,now()))
        except sqlite3.IntegrityError:raise Problem('That username is taken',409)
        db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,?)',(ident,owner,agent,digest(token),dump(sorted(scopes)),now()+86400*30,0,None))
    audit('connection.create',who,ident)
    return {'id':ident,'agent':profile(agent),'token':token,'scopes':sorted(scopes),'expires':now()+86400*30}


def upload_file(who,body,mime):
    require(who,'media:upload')
    if not body or len(body)>25*1024*1024:raise Problem('Choose a file under 25 MB',413)
    if one('SELECT coalesce(sum(size),0) n FROM media WHERE owner=?',(who['user'],))['n']+len(body)>250*1024*1024:raise Problem('Media storage limit reached',413)
    ident=uid()
    if mime in {'image/jpeg','image/png','image/webp'}:
        from PIL import Image,ImageOps
        try:
            im=Image.open(io.BytesIO(body))
            if im.width*im.height>20_000_000:raise ValueError('Image dimensions exceed limit')
            im.verify()
            im=Image.open(io.BytesIO(body));im=ImageOps.exif_transpose(im)
            im.thumbnail((2560,2560));im=im.convert('RGB')
            output=io.BytesIO();im.save(output,'WEBP',quality=88);body=output.getvalue();mime='image/webp'
        except Exception:raise Problem('This image could not be opened')
        ext='.webp'
    elif mime in {'video/mp4','video/webm'}:
        import media_pipeline
        value=media_pipeline.enqueue(ident,who['user'],who['actor'],body,mime)
        audit('media.upload',who,ident)
        return value
    else:raise Problem('Choose a JPG, PNG, WebP, MP4 or WebM file')
    path=STATE/'media'/(ident+ext);path.write_bytes(body);os.chmod(path,0o600)
    write('INSERT INTO media VALUES(?,?,?,?,?,?,?)',(ident,who['user'],who['actor'],path.name,mime,len(body),now()))
    audit('media.upload',who,ident)
    return {'id':ident,'url':'/media/'+ident,'mime':mime,'state':'ready','size':len(body)}


def http_json(url,data=None,headers=None,timeout=12):
    request=Request(url,data=dump(data).encode() if data is not None else None,headers={'User-Agent':'Rally/1.0','Accept':'application/json',**({'Content-Type':'application/json'} if data is not None else {}),**(headers or {})})
    try:
        with urlopen(request,timeout=timeout) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise Problem('Provider response was too large',502)
            return json.loads(raw)
    except HTTPError as exc:raise Problem('Provider unavailable. Try again shortly.',503,'provider_'+str(exc.code))
    except Problem:raise
    except Exception:raise Problem('Market data is temporarily unavailable',503,'provider_unavailable')


def verify_rpc_network():
    global RPC_CHECKED_AT
    with RPC_NETWORK_LOCK:
        if RPC_CHECKED_AT and time.monotonic()-RPC_CHECKED_AT<300:return
        endpoint=urlsplit(RPC_URL)
        if endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment or any(c.isspace() for c in RPC_URL):
            raise Problem('RPC configuration requires a valid HTTPS endpoint',503,'rpc_configuration')
        response=http_json(RPC_URL,{'jsonrpc':'2.0','id':1,'method':'eth_chainId','params':[]})
        try:valid=not response.get('error') and int(response.get('result',''),16)==143
        except (TypeError,ValueError):valid=False
        if not valid:raise Problem('Configured RPC is not Monad mainnet',503,'wrong_network')
        RPC_CHECKED_AT=time.monotonic()

def rpc_response(method,params):
    global RPC_REQUEST_AT
    verify_rpc_network()
    # Share a bounded request budget across background collection and wallet reads.
    with RPC_REQUEST_LOCK:
        delay=.25-(time.monotonic()-RPC_REQUEST_AT)
        if delay>0:time.sleep(delay)
        RPC_REQUEST_AT=time.monotonic()
    for attempt in range(3):
        try:return http_json(RPC_URL,{'jsonrpc':'2.0','id':1,'method':method,'params':params})
        except Problem as e:
            if e.code!='provider_429' or attempt==2 or method.startswith(('eth_send','personal_')):raise
            time.sleep(1+attempt)

def rpc(method,params):
    result=rpc_response(method,params)
    if result.get('error'):raise Problem('Network could not complete the request',502)
    return result.get('result')

def rpc_call_batch(calls,block):
    """Read-only quotes with a gas bound per path; one failure cannot drain peers."""
    global RPC_REQUEST_AT
    if not 1<=len(calls)<=8 or any(set(c)-{'to','data','gas'} for c in calls):raise Problem('Invalid read batch')
    verify_rpc_network()
    payload=[{'jsonrpc':'2.0','id':i+1,'method':'eth_call','params':[c,block]} for i,c in enumerate(calls)]
    with RPC_REQUEST_LOCK:
        delay=.25-(time.monotonic()-RPC_REQUEST_AT)
        if delay>0:time.sleep(delay)
        RPC_REQUEST_AT=time.monotonic()
    raw=http_json(RPC_URL,payload)
    if not isinstance(raw,list) or len(raw)!=len(calls) or {r.get('id') for r in raw if isinstance(r,dict)}!=set(range(1,len(calls)+1)):raise Problem('Read batch identity changed',502,'quote_identity')
    return [r for _,r in sorted((r['id'],r) for r in raw)]

def flow_version():
    from eth_utils import keccak
    call='0x'+keccak(text='getRouter()').hex()[:8]
    result=rpc('eth_call',[{'to':FLOW,'data':call},'latest'])
    if not isinstance(result,str) or not re.fullmatch(r'0x0{24}[0-9a-fA-F]{40}',result) or '0x'+result[-40:].lower()!=FLOW_INNER:raise Problem('Router changed. Integration review required.',503,'router_changed')
    code=rpc('eth_getCode',[FLOW,'latest'])
    if not code or code=='0x':raise Problem('Router contract unavailable',503)
    return {'router':FLOW_INNER,'entrypointCodeHash':digest(code.lower())}


class Gateway:
    def __init__(self):
        token_file=ROOT/'config/tokens.json'
        raw=json.loads(token_file.read_text())['tokens']
        self.tokens=[{'id':'MON','symbol':'MON','name':'Monad','address':ZERO,'decimals':18,'logoURI':'/assets/MON.png','chainId':143}]+[{**x,'id':x['address'].lower()} for x in raw if x['address'].lower()!=ZERO]
        self.token_map={x['id']:x for x in self.tokens}
        self.prices={};self.prices_at=0;self.error=None;self.perpl_lock=threading.Lock();self.perpl=None;self.perpl_at=0;self.perpl_snapshot=None
        self.keys={};self.quote_lock=threading.Lock();self.last_quote=0
        self.pool_cache={};self.pool_lock=threading.Lock();self.last_pool=0
        self.balance_cache={};self.balance_lock=threading.Lock()
        self.protocols=json.loads((ROOT/'config/protocols.json').read_text())
        assert self.protocols['kuru']['addresses']['KuruFlowEntryPoint'].lower()==FLOW
    def portfolio(self,wallet):
        import wallet_assets
        return wallet_assets.portfolio(self,wallet)
    def warm(self):
        import market_universe
        return market_universe.prices([t['address'] for t in self.tokens if t['id']!='MON'])
    def markets(self,include_launches=True):
        launches=[json.loads(x['info']) for x in rows('SELECT info FROM nad_tokens ORDER BY observed DESC LIMIT 150')] if include_launches else []
        self.token_map.update({x['id']:x for x in launches})
        launch_map={x['id']:x for x in launches}
        with LOCK:
            tokens=[{**t,**launch_map.get(t['id'],{}),**self.prices.get(t['id'],{}),'stale':now()-self.prices.get(t['id'],{}).get('fetchedAt',0)>120} for t in self.tokens]
            known={t['id'] for t in tokens}
            extra=sorted(({**self.token_map[a],**v,'stale':now()-v.get('fetchedAt',0)>120} for a,v in self.prices.items() if a not in known and a in self.token_map),key=lambda t:-(t.get('volume') or 0))[:200]
            tokens.extend(extra);known.update(t['id'] for t in extra)
            tokens += [dict(t,price=None if now()-t['referenceAt']>180 else t.get('price'),stale=now()-t['referenceAt']>180) for t in launches if t['id'] not in known]
            for t in tokens:
                stamp=t.get('referenceAt',0) if t.get('nadfun') and t.get('phase')!='dex' else t.get('fetchedAt',0)
                age=now()-stamp;t['priceAgeSeconds']=max(0,age) if stamp else None
                t['stale']=bool(t.get('stale')) or age<0 or age>120
                if age>900 or age<0:t['price']=None
            return {'tokens':tokens,'fetchedAt':self.prices_at,'priceUpdatedAt':max((t.get('fetchedAt',0) for t in tokens if t.get('price')),default=0),'source':'DexScreener · Monad pools','error':self.error}
    def perpl_markets(self,cached_only=False):
        if not cached_only:
          with self.perpl_lock:
            if now()-self.perpl_at>15:
                value=http_json('https://app.perpl.xyz/api/v1/pub/context',timeout=4)
                if not isinstance(value.get('markets'),list):raise Problem('Perpl response changed',502)
                self.perpl=value;self.perpl_at=now()
                self.perpl_snapshot=(value,self.perpl_at)
        # Snapshot the pair atomically; refresh never mutates a published value.
        value,observed=self.perpl_snapshot or (self.perpl,self.perpl_at)
        if value is None:raise Problem('Perpl context is warming',503)
        return {'markets':[{'id':m['id'],'symbol':m['name'],'open':m['config']['is_open'],'mark':int(m['state']['mrk'])/(10**m['config']['price_decimals']),'last':int(m['state']['lst'])/(10**m['config']['price_decimals']),'priceDecimals':m['config']['price_decimals'],'lotDecimals':m['config']['size_decimals']} for m in value['markets']], 'fetchedAt':observed,'venue':'Perpl','collateral':'AUSD','execution':'wallet_transactions'}
    def perps(self):
        import perp_universe
        return perp_universe.catalog()
    def pool_chart(self,asset):
        t=self.token_map.get(asset);p=self.prices.get(asset,{})
        if not t or not p.get('pair'):raise Problem('No indexed pool chart for this asset',404)
        pair=p['pair'];cache_key=asset+':'+pair
        with self.pool_lock:
            cached=self.pool_cache.get(cache_key)
            if cached and now()-cached['at']<300:
                if cached.get('error'):raise Problem('Pool chart is temporarily unavailable',503)
                return cached['value']
            time.sleep(max(0,2.1-(time.monotonic()-self.last_pool)))
            try:
                data=http_json('https://api.geckoterminal.com/api/v2/networks/monad/pools/'+pair)['data']
                if data['relationships']['base_token']['data']['id'].lower()!='monad_'+t['address'].lower():raise Problem('Pool chart identity did not match',502)
                value={'asset':asset,'pair':pair,'provider':'GeckoTerminal · CoinGecko','url':'https://www.geckoterminal.com/monad/pools/'+pair+'?embed=1&info=0&swaps=0&light_chart=0&chart_type=price&resolution=1h&bg_color=101114'}
                self.pool_cache[cache_key]={'at':now(),'value':value};return value
            except Exception:
                self.pool_cache[cache_key]={'at':now(),'error':True};raise Problem('Pool chart is temporarily unavailable',503)
            finally:self.last_pool=time.monotonic()
    def quote(self,who,data):
        user=require(who,human=True);wallet=one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
        if not wallet:raise Problem('Connect and verify your wallet first',409,'wallet_required')
        input_id=str(data.get('input',''));output_id=str(data.get('output',''))
        a=self.token_map.get(input_id);b=self.token_map.get(output_id)
        if not a or not b or a['id']==b['id']:raise Problem('Choose two different Monad assets')
        try:
            raw_value=str(data.get('amount',''))
            if len(raw_value)>80:raise ValueError()
            with localcontext() as context:
                context.prec=96
                value=Decimal(raw_value)
                if not value.is_finite() or value<=0 or value>Decimal('1000000000000'):raise ValueError()
                amount_decimal=value*(10**a['decimals']);amount=int(amount_decimal)
                if amount<1 or amount_decimal!=amount:raise ValueError()
        except (InvalidOperation,ValueError,OverflowError):raise Problem('Enter a valid amount for this token')
        slippage=int(data.get('slippage',50))
        if not 1<=slippage<=100:raise Problem('Slippage must be between 0.01% and 1%')
        with self.quote_lock:
            key=self.keys.get(wallet)
            if not key or key['expires_at']<now()+60:
                key=http_json('https://ws.kuru.io/api/generate-token',{'user_address':wallet});self.keys[wallet]=key;self.last_quote=time.monotonic()
            time.sleep(max(0,1.1-(time.monotonic()-self.last_quote)))
            raw=http_json('https://ws.kuru.io/api/quote',{'userAddress':wallet,'tokenIn':a['address'],'tokenOut':b['address'],'amount':str(amount),'slippageTolerance':slippage,'autoSlippage':False},{'Authorization':'Bearer '+key['token']})
            self.last_quote=time.monotonic()
        if raw.get('status')!='success':raise Problem('No route for this amount. Try another asset.',422,'no_route')
        transaction=raw.get('transaction',{});calldata=transaction.get('calldata','').removeprefix('0x')
        out=int(raw.get('output','0'));minimum=int(raw.get('minOut','0'));txvalue=int(transaction.get('value','0'))
        # Pin the official entry point and the swap ABI arguments. A quote is not authority.
        if transaction.get('to','').lower()!=FLOW or not re.fullmatch(r'[0-9a-fA-F]{8,60000}',calldata) or calldata[:8]!='ce1e7030':raise Problem('Unrecognized routing transaction',502)
        from eth_abi import decode,encode
        abi=['(address,uint256,address,uint256)','(address,uint256,address,uint256,bool)','bytes']
        try:
            payload=bytes.fromhex(calldata[8:]);decoded=decode(abi,payload)
            if encode(abi,decoded)!=payload:raise ValueError()
        except Exception:raise Problem('Noncanonical routing transaction',502)
        fee=decoded[1];fee_bps=int(fee[1])+int(fee[3])
        if fee_bps>100 or fee[1] and fee[0]==ZERO or fee[3] and fee[2]==ZERO:raise Problem('Unexpected router fee',502)
        # ce1e7030 is executeSwap, whose public ABI returns output to msg.sender.
        # The different executeSwapWithReceiver selector is rejected above.
        words=[calldata[8+i*64:8+(i+1)*64] for i in range(4)]
        if len(words[-1])!=64 or '0x'+words[0][-40:].lower()!=b['address'].lower() or int(words[1],16)!=minimum or '0x'+words[2][-40:].lower()!=a['address'].lower() or int(words[3],16)!=amount or not 0<minimum<=out:raise Problem('Routing transaction does not match your order',502)
        if minimum<out*(10000-slippage)//10000:raise Problem('Minimum received exceeds your allowed slippage',502)
        if txvalue!=(amount if a['address']==ZERO else 0):raise Problem('Unexpected transaction value',502)
        version=flow_version()
        ident=uid();expires=now()+30
        result={'id':ident,'wallet':wallet,'input':input_id,'output':output_id,'amount':str(value),'amountRaw':str(amount),'receive':units(out,b['decimals']),'minimum':units(minimum,b['decimals']),'provider':'Kuru Flow','chainId':143,'slippageBps':slippage,'expires':expires,'approval':None if a['address']==ZERO else {'token':a['address'],'spender':FLOW,'amount':str(amount)},'transaction':{'from':wallet,'to':FLOW,'data':'0x'+calldata,'value':hex(txvalue)}}
        result.update(version);result['fees']={'totalBps':fee_bps,'inputFee':bool(fee[4]),'collector':fee[0],'referrer':fee[2]}
        write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(ident,user,wallet,input_id,output_id,str(amount),dump(result),expires))
        return result


def bootstrap(who,include_markets=True):
    import settlement
    if who and who['grant']:raise Problem('Use the agent tools for this connection',403)
    user=who['user'] if who else None
    import social, privy_auth, community_tokens
    privy=privy_auth.status(user)
    token_status=community_tokens.status(user)
    return {'communityToken':token_status,'auth':{'privy':privy},'loginMethods':['wallet','password']+(['privy'] if privy['enabled'] else []),'passwordAccount':bool(user and one('SELECT pw FROM accounts WHERE id=?',(user,))['pw']),'unread':social.notices(who)['unread'] if who else 0,'me':profile(user,user) if user else None,'wallet':one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet'] if user else None,
        'communities':[{**c,'members':one('SELECT count(*) n FROM members WHERE community=?',(c['id'],))['n'],'joined':bool(user and one('SELECT 1 FROM members WHERE user_id=? AND community=?',(user,c['id'])))} for c in rows('SELECT * FROM communities')],
        'feeds':[settlement.view(f,user) for f in rows('SELECT * FROM feeds ORDER BY created') if social.visible(user,f['owner'])],
        'people':[profile(p['id'],user) for p in rows("SELECT id FROM accounts WHERE kind IN ('person','agent','service') ORDER BY created DESC LIMIT 50") if social.visible(user,p['id'])][:30],
        'watches':[x['asset'] for x in rows('SELECT asset FROM watches WHERE user_id=?',(user or '',))],
        'activeFeed':active_feed(user),
        'marketData':GATEWAY.markets(False) if include_markets else None,
        'connections':rows('SELECT id,agent,scopes,expires,revoked,last_used FROM grants WHERE owner=? ORDER BY rowid DESC',(user or '',)),
        'capabilities':{'social':'server','media':'server_upload','mcp':'streamable_http','spot':'live_quotes_wallet_execution','perps':'wallet_execution_funded_acceptance_pending','prediction':'castora_wallet_execution_eligible_pool_required','stocks':'partner_activation_and_contract_review_required','rwa':'catalog_quotes_subject_to_eligibility','subscriptions':'USDC_direct_creator_prepaid_30_days','messages':False}}

def active_feed(user):
    from settlement import allowed
    import social
    ident=(one('SELECT feed FROM settings WHERE user_id=?',(user,)) or {}).get('feed','latest')
    feed=one('SELECT * FROM feeds WHERE id=?',(ident,))
    return ident if feed and allowed(feed,user) and social.visible(user,feed['owner']) else 'latest'


def action(path,who,data,key=''):
    user=require(who)
    if path=='posts':return publish(who,data,key)
    if path=='profile':
        require(who,human=True)
        if 'handle' in data:
            handle=str(data['handle']).lower().strip()
            if not re.fullmatch(r'[a-z0-9_]{3,24}',handle):raise Problem('Use 3–24 letters, numbers or underscores')
            try:write('UPDATE accounts SET handle=? WHERE id=?',(handle,user))
            except sqlite3.IntegrityError:raise Problem('That username is taken',409)
        write('UPDATE accounts SET name=?,bio=? WHERE id=?',(str(data.get('name',''))[:48],str(data.get('bio',''))[:240],user));return profile(user,user)
    if path=='post/delete':
        require(who,'posts:write');changed=write('UPDATE posts SET deleted=1 WHERE id=? AND author=?',(data.get('id'),who['actor']))
        if not changed:raise Problem('Post not found or not owned',403)
        audit('post.delete',who,data['id']);return {'ok':True}
    if path=='reaction':
        import social
        social.post(data.get('post'),user)
        require(who,human=True);kind=data.get('kind');post=data.get('post')
        if kind not in {'like','save'} or not one('SELECT 1 FROM posts WHERE id=? AND deleted=0',(post,)):raise Problem('Post not found',404)
        if data.get('active'):
            write('INSERT OR IGNORE INTO reactions VALUES(?,?,?)',(user,post,kind))
            if kind=='like':social.notify(user,social.post(post,user)['author'],'like',post)
        else:write('DELETE FROM reactions WHERE user_id=? AND post=? AND kind=?',(user,post,kind))
        return post_view(one('SELECT * FROM posts WHERE id=?',(post,)),user)
    if path=='follow':
        require(who,human=True);target=profile(str(data.get('id','')),user)['id']
        if target==user:raise Problem('This is your profile')
        if data.get('active'):
            write('INSERT OR IGNORE INTO follows VALUES(?,?)',(user,target))
            import social
            social.notify(user,target,'follow')
        else:write('DELETE FROM follows WHERE user_id=? AND target=?',(user,target))
        return profile(target,user)
    if path=='watch':
        require(who,human=True);asset=data.get('asset')
        if asset not in GATEWAY.token_map:
            row=one('SELECT info FROM nad_tokens WHERE address=?',(asset,))
            if not row:raise Problem('Unknown asset')
            GATEWAY.token_map[asset]=json.loads(row['info'])
        if data.get('active'):write('INSERT OR IGNORE INTO watches VALUES(?,?)',(user,asset))
        else:write('DELETE FROM watches WHERE user_id=? AND asset=?',(user,asset))
        return {'ok':True}
    if path=='join':
        require(who,human=True);community=data.get('id')
        if not one('SELECT 1 FROM communities WHERE id=?',(community,)):raise Problem('Community not found',404)
        if data.get('active'):write('INSERT OR IGNORE INTO members VALUES(?,?)',(user,community))
        else:write('DELETE FROM members WHERE user_id=? AND community=?',(user,community))
        return {'ok':True}
    if path=='feeds/create':
        import settlement
        require(who,human=True);name=str(data.get('name','')).strip();weights=data.get('weights',[100,0,0])
        if not name or len(name)>32 or len(weights)!=3 or not all(isinstance(w,int) and 0<=w<=100 for w in weights) or not any(weights):raise Problem('Choose a name and ranking weights')
        amount=settlement.price(data.get('price','0'));recipient=one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
        if int(amount) and not recipient:raise Problem('Connect a wallet to receive feed payments',409,'wallet_required')
        ident=uid();write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,recipient) VALUES(?,?,?,?,?,?,?,?)',(ident,user,name,dump(weights),'[]',now(),amount,recipient if int(amount) else None));return {'id':ident}
    if path=='feeds/use':
        require(who,human=True);ident=data.get('id')
        feed=one('SELECT * FROM feeds WHERE id=?',(ident,))
        import social
        if feed and not social.visible(user,feed['owner']):raise Problem('Feed not found',404)
        if not feed:raise Problem('Feed not found',404)
        from settlement import allowed
        if not allowed(feed,user):raise Problem('Subscribe to use this feed',403,'subscription_required')
        write('INSERT INTO settings(user_id,feed) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET feed=excluded.feed',(user,ident));return {'ok':True}
    if path=='connections':return new_grant(who,data)
    if path=='connections/revoke':
        import oauth_sessions
        result=oauth_sessions.revoke_connection(who,data.get('id'));audit('connection.revoke',who,data.get('id'));return result
    if path=='quotes':return GATEWAY.quote(who,data)
    raise Problem('Action not found',404)


GATEWAY=Gateway()
