"""Opt-in Web Push and FCM delivery. No wallet or trading authority."""
import base64
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import service as s

KINDS={'social','algorithm','price','migration','trade','signal'}
KEY_LOCK=threading.Lock()
TOKEN_LOCK=threading.Lock()
FCM_TOKEN=None
OWNER_CURSOR=''


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS push_settings(owner TEXT PRIMARY KEY,enabled INTEGER DEFAULT 0,kinds TEXT NOT NULL,after_row INTEGER NOT NULL DEFAULT 0,created INTEGER);
        CREATE TABLE IF NOT EXISTS push_devices(id TEXT PRIMARY KEY,owner TEXT,kind TEXT,payload TEXT,enabled INTEGER DEFAULT 1,created INTEGER,updated INTEGER,UNIQUE(kind,payload));
        CREATE TABLE IF NOT EXISTS push_queue(id TEXT PRIMARY KEY,device TEXT,notice TEXT,state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_at INTEGER,lease_until INTEGER DEFAULT 0,created INTEGER,accepted INTEGER,error TEXT,UNIQUE(device,notice));
        CREATE INDEX IF NOT EXISTS push_due ON push_queue(state,next_at);
        CREATE INDEX IF NOT EXISTS push_owner_devices ON push_devices(owner,enabled);
        ''')
        cols={r[1] for r in db.execute('PRAGMA table_info(notifications)')}
        for name in ('url','detail','feed'):
            if name not in cols:db.execute('ALTER TABLE notifications ADD COLUMN '+name+' TEXT')


def key_path():return Path(os.environ.get('RALLY_WEB_PUSH_PRIVATE_KEY',str(s.STATE/'web-push.pem')))


def ensure_key():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    with KEY_LOCK:
        p=key_path()
        if not p.exists():
            p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            key=ec.generate_private_key(ec.SECP256R1())
            raw=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            try:
                fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as f:f.write(raw)
            except FileExistsError:pass
        if p.stat().st_mode & 0o077:raise s.Problem('Push key permissions need configuration',503)
        key=serialization.load_pem_private_key(p.read_bytes(),password=None)
        if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):raise s.Problem('Push key unavailable',503)
        return key


def firebase():
    p=Path(os.environ.get('RALLY_FIREBASE_CREDENTIALS',str(s.STATE/'firebase-service-account.json')))
    android=s.STATE/'firebase-android.json'
    if not p.exists() or not android.exists():return None
    try:
        if p.stat().st_mode & 0o077 or p.stat().st_size>20000:return None
        account=json.loads(p.read_text());cfg=json.loads(android.read_text())
        if account.get('type')!='service_account' or cfg.get('projectId')!=account.get('project_id'):return None
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,62}',str(cfg.get('projectId',''))):return None
        if not re.fullmatch(r'1:\d+:android:[a-f0-9]+',str(cfg.get('applicationId',''))):return None
        if not re.fullmatch(r'AIza[A-Za-z0-9_-]{30,50}',str(cfg.get('apiKey',''))) or not str(cfg.get('senderId','')).isdigit():return None
        return account,{k:str(cfg[k]) for k in ['projectId','applicationId','apiKey','senderId']}
    except (ValueError,OSError,KeyError):return None


def config():
    from cryptography.hazmat.primitives import serialization
    pub=ensure_key().public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    f=firebase()
    return {'web':True,'applicationServerKey':base64.urlsafe_b64encode(pub).decode().rstrip('='),
        'android':bool(f),'firebase':f[1] if f else None,'kinds':sorted(KINDS)}


def settings(who):
    user=s.require(who,human=True);row=s.one('SELECT * FROM push_settings WHERE owner=?',(user,))
    devices=s.rows('SELECT id,kind,enabled,updated FROM push_devices WHERE owner=? ORDER BY updated DESC',(user,))
    return {'enabled':bool(row and row['enabled']),'kinds':json.loads(row['kinds']) if row else sorted(KINDS),
        'devices':devices,'config':config()}


def configure(who,data):
    user=s.require(who,human=True)
    if type(data.get('enabled')) is not bool:raise s.Problem('Choose whether to enable alerts')
    kinds=data.get('kinds',sorted(KINDS))
    if not isinstance(kinds,list) or len(kinds)>len(KINDS) or not all(isinstance(k,str) and k in KINDS for k in kinds):raise s.Problem('Choose supported alert types')
    old=s.one('SELECT * FROM push_settings WHERE owner=?',(user,))
    cursor=old['after_row'] if old and old['enabled'] and data['enabled'] else s.one('SELECT coalesce(max(rowid),0) n FROM notifications')['n']
    s.write('INSERT INTO push_settings VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET enabled=excluded.enabled,kinds=excluded.kinds,after_row=excluded.after_row',
        (user,int(data['enabled']),s.dump(sorted(set(kinds))),cursor,s.now()))
    if not data['enabled']:s.write("UPDATE push_queue SET state='cancelled' WHERE device IN (SELECT id FROM push_devices WHERE owner=?) AND state IN ('pending','sending')",(user,))
    return settings(who)


def b64(value,size):
    if not isinstance(value,str) or len(value)>200 or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}',value):raise s.Problem('Invalid push subscription')
    try:raw=base64.urlsafe_b64decode(value.rstrip('=')+'='*((-len(value.rstrip('=')))%4))
    except ValueError:raise s.Problem('Invalid push subscription')
    if len(raw)!=size:raise s.Problem('Invalid push subscription')
    return raw


def subscription(value):
    if not isinstance(value,dict):raise s.Problem('Invalid push subscription')
    endpoint=value.get('endpoint')
    try:
        u=urlsplit(endpoint) if isinstance(endpoint,str) else None
        port=u.port if u else None
    except ValueError:raise s.Problem('Invalid push service')
    if not u or u.scheme!='https' or u.username or u.password or u.fragment or port not in (None,443) or len(endpoint)>2048:raise s.Problem('Invalid push service')
    host=u.hostname or ''
    valid=host in {'fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'} or bool(re.fullmatch(r'[a-z0-9-]+\.notify\.windows\.com',host))
    if not valid or len(u.path)<10:raise s.Problem('Unsupported push service')
    keys=value.get('keys',{})
    if not isinstance(keys,dict):raise s.Problem('Invalid push subscription')
    raw=b64(keys.get('p256dh'),65);b64(keys.get('auth'),16)
    from cryptography.hazmat.primitives.asymmetric import ec
    try:ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),raw)
    except ValueError:raise s.Problem('Invalid push subscription')
    return {'endpoint':endpoint,'keys':{'p256dh':keys['p256dh'],'auth':keys['auth']}}


def register(who,data):
    user=s.require(who,human=True);kind=data.get('kind')
    if kind=='web':payload=subscription(data.get('subscription'));key=payload['endpoint']
    elif kind=='android':
        if not firebase():raise s.Problem('Android push notifications are being configured',409,'push_not_configured')
        token=data.get('token','')
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_:\-]{40,4096}',token):raise s.Problem('Invalid push token')
        payload={'token':token};key=token
    else:raise s.Problem('Unsupported device')
    ident=s.digest(kind+':'+key)
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT owner FROM push_devices WHERE id=?',(ident,)).fetchone()
        if old and old['owner']!=user:raise s.Problem('Remove this device from its previous account first',409)
        if not old and db.execute('SELECT count(*) FROM push_devices WHERE owner=?',(user,)).fetchone()[0]>=10:raise s.Problem('Device limit reached',429)
        db.execute('INSERT INTO push_devices VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=1,payload=excluded.payload,updated=excluded.updated',
            (ident,user,kind,s.dump(payload),1,s.now(),s.now()))
    return {'id':ident,'kind':kind,'registered':True}


def remove(who,data):
    user=s.require(who,human=True)
    s.write('DELETE FROM push_devices WHERE id=? AND owner=?',(str(data.get('id','')),user))
    return {'removed':True}


def emit(owner,kind,key,title,body,url,actor='rally',post=None,feed=None):
    if not isinstance(url,str) or not url.startswith('/?') or len(url)>600:raise ValueError('Unsafe notification route')
    ident=s.uid()
    s.write('INSERT OR IGNORE INTO notifications(id,owner,actor,kind,post,created,dedupe,url,detail,feed) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (ident,owner,actor,kind,post,s.now(),key,url,s.dump({'title':title[:90],'body':body[:180]}),feed))


def eligible(n):
    import social,settlement
    if not social.visible(n['owner'],n['actor']):return False
    if n.get('post'):
        p=s.one('SELECT * FROM posts WHERE id=? AND deleted=0',(n['post'],))
        if not p or not social.visible(n['owner'],p['author']):return False
    if n.get('feed'):
        f=s.one('SELECT * FROM feeds WHERE id=?',(n['feed'],))
        if not f or not settlement.allowed(f,n['owner']):return False
    if n['kind'] in {'price','migration'}:
        from urllib.parse import parse_qs
        asset=parse_qs(urlsplit(n.get('url') or '').query).get('token',[''])[0]
        if not s.one('SELECT 1 FROM market_alerts m JOIN watches w ON w.user_id=m.owner AND w.asset=m.asset WHERE m.owner=? AND m.asset=? AND m.enabled=1',(n['owner'],asset)):return False
    if n['kind']=='trade' and (not n.get('post') or not s.one('SELECT 1 FROM trade_shares WHERE post=? AND withdrawn=0',(n['post'],))):return False
    if n['kind']=='algorithm':
        a=s.one('SELECT a.*,f.version current_version FROM feed_alerts a JOIN feeds f ON f.id=a.feed WHERE a.owner=? AND a.feed=?',(n['owner'],n.get('feed')))
        if not a or not a['enabled'] or a['version']!=a['current_version']:return False
    return True


def content(n):
    from urllib.parse import quote
    detail=json.loads(n['detail']) if n.get('detail') else None
    if not detail:
        actor=s.one('SELECT name FROM accounts WHERE id=?',(n['actor'],)) or {'name':'Rally'}
        detail={'title':'Rally','body':actor['name']+' '+{'algorithm':'published a creator update','follow':'followed you','like':'liked your post','reply':'replied to you','repost':'reposted your post'}.get(n['kind'],'posted an update')}
    url=n.get('url') or ('/?view=post&post='+quote(n['post']) if n.get('post') else '/?view=notifications')
    return {**detail,'url':url,'tag':'rally-'+n['id'],'id':n['id']}


def enqueue():
    global OWNER_CURSOR
    batch=s.rows('SELECT * FROM push_settings WHERE enabled=1 AND owner>? ORDER BY owner LIMIT 1000',(OWNER_CURSOR,))
    if not batch:batch=s.rows('SELECT * FROM push_settings WHERE enabled=1 ORDER BY owner LIMIT 1000')
    if batch:OWNER_CURSOR=batch[-1]['owner']
    for cfg in batch:
        notices=s.rows('SELECT *,rowid seq FROM notifications WHERE owner=? AND rowid>? ORDER BY rowid LIMIT 50',(cfg['owner'],cfg['after_row']))
        kinds=set(json.loads(cfg['kinds']))
        with s.connection() as db:
            for n in notices:
                kind=n['kind'] if n['kind'] in KINDS else 'social'
                if kind not in kinds or n['created']<s.now()-3600 or not eligible(n):continue
                for d in db.execute('SELECT id FROM push_devices WHERE owner=? AND enabled=1',(cfg['owner'],)):
                    db.execute('INSERT OR IGNORE INTO push_queue(id,device,notice,next_at,created) VALUES(?,?,?,?,?)',(s.uid(),d['id'],n['id'],s.now(),s.now()))
            if notices:db.execute('UPDATE push_settings SET after_row=max(after_row,?) WHERE owner=?',(notices[-1]['seq'],cfg['owner']))


def fcm_token(account):
    import jwt
    global FCM_TOKEN
    with TOKEN_LOCK:
        if FCM_TOKEN and FCM_TOKEN[0]==account['client_email'] and FCM_TOKEN[2]>s.now()+120:return FCM_TOKEN[1]
        signed=jwt.encode({'iss':account['client_email'],'scope':'https://www.googleapis.com/auth/firebase.messaging',
            'aud':'https://oauth2.googleapis.com/token','iat':s.now(),'exp':s.now()+3600},account['private_key'],algorithm='RS256')
        req=Request('https://oauth2.googleapis.com/token',data=urlencode({'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer','assertion':signed}).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
        with urlopen(req,timeout=6) as r:data=json.loads(r.read(20000))
        FCM_TOKEN=(account['client_email'],data['access_token'],s.now()+min(int(data['expires_in']),3600));return FCM_TOKEN[1]


def send(device,payload):
    if os.environ.get('RALLY_PUSH_DISABLED')=='1':raise RuntimeError('Delivery disabled in this environment')
    data=json.loads(device['payload'])
    if device['kind']=='web':
        import requests
        from pywebpush import webpush,WebPushException
        class NoRedirect(requests.Session):
            def request(self,*args,**kwargs):kwargs['allow_redirects']=False;return super().request(*args,**kwargs)
        try:
            with NoRedirect() as session:
                r=webpush(subscription_info=data,data=s.dump(payload),vapid_private_key=str(key_path()),vapid_claims={'sub':os.environ.get('RALLY_WEB_PUSH_CONTACT','https://rallydot.com')},ttl=3600,timeout=6,requests_session=session,headers={'Urgency':'normal','Topic':s.digest(payload['id'])[:32]})
                return r.status_code
        except WebPushException as e:return e.response.status_code if e.response is not None else 503
    f=firebase()
    if not f:return 503
    account,cfg=f
    # Generic lock-screen text avoids exposing account/subscriber content.
    body={'message':{'token':data['token'],'notification':{'title':'Rally','body':'New activity in Rally'},
        'data':{k:str(v) for k,v in payload.items()},'android':{'priority':'normal','ttl':'3600s','collapse_key':payload['tag'],
            'notification':{'channel_id':'rally_activity','tag':payload['tag'],'click_action':'com.rallydot.OPEN_NOTIFICATION','visibility':'private'}}}}
    req=Request('https://fcm.googleapis.com/v1/projects/'+cfg['projectId']+'/messages:send',data=s.dump(body).encode(),headers={'Authorization':'Bearer '+fcm_token(account),'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=6) as r:r.read(20000);return r.status
    except HTTPError as e:return e.code


def deliver_once():
    for job in s.rows("SELECT * FROM push_queue WHERE (state='pending' AND next_at<=?) OR (state='sending' AND lease_until<?) ORDER BY created LIMIT 8",(s.now(),s.now())):
        if not s.write("UPDATE push_queue SET state='sending',lease_until=?,attempts=attempts+1 WHERE id=? AND ((state='pending' AND next_at<=?) OR (state='sending' AND lease_until<?))",(s.now()+30,job['id'],s.now(),s.now())):continue
        d=s.one('SELECT * FROM push_devices WHERE id=? AND enabled=1',(job['device'],));n=s.one('SELECT * FROM notifications WHERE id=?',(job['notice'],))
        pref=s.one('SELECT * FROM push_settings WHERE owner=?',(d['owner'],)) if d else None
        kind=n['kind'] if n and n['kind'] in KINDS else 'social'
        if not d or not n or d['owner']!=n['owner'] or not pref or not pref['enabled'] or kind not in json.loads(pref['kinds']) or not eligible(n) or job['created']<s.now()-3600:
            s.write("UPDATE push_queue SET state='cancelled' WHERE id=?",(job['id'],));continue
        try:status=send(d,content(n))
        except Exception:status=503
        if 200<=status<300:s.write("UPDATE push_queue SET state='accepted',accepted=?,error=NULL WHERE id=?",(s.now(),job['id']))
        elif status in {404,410}:
            s.write('UPDATE push_devices SET enabled=0 WHERE id=?',(d['id'],));s.write("UPDATE push_queue SET state='expired',error=? WHERE id=?",('subscription_expired',job['id']))
        elif job['attempts']>=4 or status in {400,401,403}:
            s.write("UPDATE push_queue SET state='failed',error=? WHERE id=?",('provider_'+str(status),job['id']))
        else:s.write("UPDATE push_queue SET state='pending',next_at=?,error=? WHERE id=?",(s.now()+min(900,30*2**job['attempts']),'provider_'+str(status),job['id']))
    s.write('DELETE FROM push_queue WHERE created<?',(s.now()-86400*7,))


def background():
    import time
    while True:
        try:enqueue();deliver_once()
        except Exception as error:
            __import__('logging').getLogger(__name__).warning('Push worker failed: %s',type(error).__name__)
        time.sleep(5)
