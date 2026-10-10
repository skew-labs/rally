"""Account recovery and social controls. No wallet authority."""
import hmac
import json
import secrets
import service as s


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS blocks(owner TEXT,target TEXT,created INTEGER,PRIMARY KEY(owner,target));
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,owner TEXT,post TEXT,reason TEXT,status TEXT,created INTEGER,UNIQUE(owner,post));
        CREATE TABLE IF NOT EXISTS reposts(owner TEXT,post TEXT,created INTEGER,PRIMARY KEY(owner,post));
        CREATE TABLE IF NOT EXISTS edits(post TEXT,version INTEGER,text TEXT,created INTEGER,PRIMARY KEY(post,version));
        CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,owner TEXT,actor TEXT,kind TEXT,post TEXT,created INTEGER,seen INTEGER DEFAULT 0,dedupe TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS recovery(owner TEXT,hash TEXT UNIQUE,used INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS notifications_owner ON notifications(owner,created DESC);
        ''')
        if 'version' not in [r[1] for r in db.execute('PRAGMA table_info(posts)')]:
            db.execute('ALTER TABLE posts ADD COLUMN version INTEGER DEFAULT 1')


def owner(actor):
    row=s.one('SELECT id,owner FROM accounts WHERE id=?',(actor,))
    return (row['owner'] or row['id']) if row else actor


def visible(viewer, actor):
    if not viewer:return True
    a,b=owner(viewer),owner(actor)
    return a==b or not s.one('SELECT 1 FROM blocks WHERE (owner=? AND target=?) OR (owner=? AND target=?)',(a,b,b,a))


def visibility_sql(viewer, alias='posts'):
    if not viewer:return '',[]
    return f''' AND NOT EXISTS (SELECT 1 FROM blocks b JOIN accounts a ON a.id={alias}.author
      WHERE (b.owner=? AND b.target=coalesce(a.owner,a.id)) OR (b.target=? AND b.owner=coalesce(a.owner,a.id)))''',[owner(viewer)]*2


def post(ident, viewer):
    row=s.one('SELECT * FROM posts WHERE id=? AND deleted=0',(ident,))
    if not row or not visible(viewer,row['author']):raise s.Problem('Post not found',404)
    return row


def notify(actor, recipient, kind, ident=None):
    recipient=owner(recipient)
    if owner(actor)==recipient or not visible(recipient,actor):return
    # A repeated like/follow must not create repeated alerts.
    key=':'.join([actor,recipient,kind,ident or ''])
    s.write('INSERT OR IGNORE INTO notifications(id,owner,actor,kind,post,created,dedupe) VALUES(?,?,?,?,?,?,?)',(s.uid(),recipient,actor,kind,ident,s.now(),key))


def notices(who):
    user=s.require(who,human=True)
    result=[]
    for n in s.rows('SELECT * FROM notifications WHERE owner=? ORDER BY created DESC,id DESC LIMIT 100',(user,)):
        if not visible(user,n['actor']) or not __import__('push_delivery').eligible(n):continue
        p=s.one('SELECT id,text,deleted FROM posts WHERE id=?',(n['post'],)) if n['post'] else None
        if n['post'] and (not p or p['deleted']):continue
        result.append({**n,'actor':s.profile(n['actor'],user),'text':p['text'][:180] if p else '', 'detail':json.loads(n['detail']) if n.get('detail') else None})
    return {'notifications':result,'unread':sum(not n['seen'] for n in result)}


def extras(row, viewer):
    row['reposted']=bool(viewer and s.one('SELECT 1 FROM reposts WHERE owner=? AND post=?',(owner(viewer),row['id'])))
    row['reposts']=s.one('SELECT count(*) n FROM reposts WHERE post=?',(row['id'],))['n']
    row['edited']=row.get('version',1)>1
    return row


def search(who, query):
    if who and who['grant']:s.require(who,'feed:read')
    viewer=who['user'] if who else None
    query=str(query).strip()[:100]
    if len(query)<2:return {'posts':[],'people':[],'communities':[]}
    pattern='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    guard,args=visibility_sql(viewer)
    posts=s.rows("SELECT * FROM posts WHERE deleted=0 AND text LIKE ? ESCAPE '\\'"+guard+' ORDER BY created DESC LIMIT 20',[pattern]+args)
    people=s.rows("SELECT id FROM accounts WHERE name LIKE ? ESCAPE '\\' OR handle LIKE ? ESCAPE '\\' ORDER BY created DESC LIMIT 50",[pattern,pattern])
    return {'posts':[s.post_view(p,viewer) for p in posts], 'people':[s.profile(p['id'],viewer) for p in people if visible(viewer,p['id'])][:20], 'communities':s.rows("SELECT * FROM communities WHERE name LIKE ? ESCAPE '\\' LIMIT 10",[pattern])}


def recovery_codes(who, data):
    user=s.require(who,human=True)
    account=s.one('SELECT pw FROM accounts WHERE id=?',(user,))
    if not account['pw'] or not hmac.compare_digest(s.password_hash(data.get('password',''),account['pw'].split(':')[0]),account['pw']):raise s.Problem('Password is incorrect',401)
    codes=[secrets.token_hex(12) for _ in range(8)]
    with s.connection() as db:
        db.execute('DELETE FROM recovery WHERE owner=?',(user,))
        db.executemany('INSERT INTO recovery(owner,hash) VALUES(?,?)',[(user,s.digest(user+':'+c)) for c in codes])
    s.audit('recovery.create',who,user)
    return {'codes':codes,'shownOnce':True}


def recover(data):
    hashed=s.password_hash(data.get('password',''))
    account=s.one("SELECT id FROM accounts WHERE handle=? AND kind='person'",(str(data.get('handle','')).strip().lower(),))
    valid=False
    if account:
        user=account['id'];code_hash=s.digest(user+':'+str(data.get('code','')).replace('-','').strip().lower())
        with s.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            valid=bool(db.execute('UPDATE recovery SET used=1 WHERE owner=? AND hash=? AND used=0',(user,code_hash)).rowcount)
            if valid:
                db.execute('UPDATE accounts SET pw=? WHERE id=?',(hashed,user))
                db.execute('DELETE FROM sessions WHERE user_id=?',(user,))
                db.execute('UPDATE grants SET revoked=1 WHERE owner=?',(user,))
                db.execute('UPDATE oauth_families SET revoked=1 WHERE owner=?',(user,))
    if not valid:raise s.Problem('Username or recovery code is incorrect',401)
    return {'ok':True}


def action(path, who, data):
    if path=='auth/recover':return recover(data)
    user=s.require(who)
    if path=='post/edit':
        s.require(who,'posts:write');p=post(data.get('id'),user)
        if p['author']!=who['actor']:raise s.Problem('This is not your post',403)
        text=str(data.get('text','')).strip()
        if len(text)>4000 or not (text or p['media']):raise s.Problem('Add text or media')
        version=data.get('version')
        if not isinstance(version,int):raise s.Problem('Post version required')
        with s.connection() as db:
            if not db.execute('UPDATE posts SET text=?,version=version+1 WHERE id=? AND version=? AND deleted=0',(text,p['id'],version)).rowcount:raise s.Problem('Post changed. Reload before editing.',409)
            db.execute('INSERT INTO edits VALUES(?,?,?,?)',(p['id'],version,p['text'],s.now()))
        s.audit('post.edit',who,p['id'])
        return s.post_view(s.one('SELECT * FROM posts WHERE id=?',(p['id'],)),who['actor'])
    s.require(who,human=True)
    if path=='auth/recovery-codes':return recovery_codes(who,data)
    if path=='notifications/read':
        ids=data.get('ids',[])
        if not isinstance(ids,list) or len(ids)>100 or not all(isinstance(i,str) for i in ids):raise s.Problem('Invalid notifications')
        with s.connection() as db:db.executemany('UPDATE notifications SET seen=1 WHERE owner=? AND id=?',[(user,i) for i in ids])
        return {'ok':True}
    if path=='block':
        target=owner(s.profile(str(data.get('id','')))['id'])
        if target==user:raise s.Problem('You cannot block your own profile')
        with s.connection() as db:
            if data.get('active'):
                db.execute('INSERT OR IGNORE INTO blocks VALUES(?,?,?)',(user,target,s.now()))
                # Disconnect both owners and their agent profiles.
                db.execute('DELETE FROM follows WHERE (user_id=? AND target IN (SELECT id FROM accounts WHERE id=? OR owner=?)) OR (user_id=? AND target IN (SELECT id FROM accounts WHERE id=? OR owner=?))',(user,target,target,target,user,user))
            else:db.execute('DELETE FROM blocks WHERE owner=? AND target=?',(user,target))
        return {'ok':True}
    if path=='post/report':
        p=post(data.get('id'),user);reason=data.get('reason')
        if reason not in {'spam','scam','harassment','other'}:raise s.Problem('Choose a reason')
        s.write('INSERT OR IGNORE INTO reports VALUES(?,?,?,?,?,?)',(s.uid(),user,p['id'],reason,'received',s.now()))
        return {'ok':True,'status':'received'}
    if path=='post/repost':
        p=post(data.get('id'),user)
        if data.get('active'):
            s.write('INSERT OR IGNORE INTO reposts VALUES(?,?,?)',(user,p['id'],s.now()));notify(user,p['author'],'repost',p['id'])
        else:s.write('DELETE FROM reposts WHERE owner=? AND post=?',(user,p['id']))
        return s.post_view(p,user)
    raise s.Problem('Action not found',404)
