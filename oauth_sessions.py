"""PKCE code exchange and rotating, client-bound refresh families."""
import base64
import hashlib
import json
import re
import secrets
import service as s


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS oauth_families(id TEXT PRIMARY KEY,owner TEXT,agent TEXT,client TEXT,scopes TEXT,resource TEXT,expires INTEGER,revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS oauth_refresh(hash TEXT PRIMARY KEY,family TEXT,used INTEGER DEFAULT 0,created INTEGER);
        CREATE TABLE IF NOT EXISTS oauth_access(grant_id TEXT PRIMARY KEY,family TEXT);
        CREATE TABLE IF NOT EXISTS oauth_code_resources(hash TEXT PRIMARY KEY,resource TEXT NOT NULL);
        ''')


def revoke_family(db,family):
    db.execute('UPDATE oauth_families SET revoked=1 WHERE id=?',(family,))
    db.execute('UPDATE grants SET revoked=1 WHERE id IN (SELECT grant_id FROM oauth_access WHERE family=?)',(family,))


def revoke_connection(who, ident):
    user=s.require(who,human=True)
    with s.connection() as db:
        if not db.execute('UPDATE grants SET revoked=1 WHERE id=? AND owner=?',(ident,user)).rowcount:raise s.Problem('Connection not found',404)
        family=db.execute('SELECT family FROM oauth_access WHERE grant_id=?',(ident,)).fetchone()
        if family:revoke_family(db,family[0])
    return {'ok':True}


def token(data,resource):
    typ=data.get('grant_type');requested=data.get('resource')
    if requested and requested!=resource:raise s.Problem('Unknown resource')
    access=secrets.token_urlsafe(40);refresh=secrets.token_urlsafe(40);grant=s.uid();invalid=False
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if typ=='authorization_code':
            code=db.execute('SELECT * FROM codes WHERE hash=? AND used=0 AND expires>?',(s.digest(str(data.get('code',''))),s.now())).fetchone()
            audience=db.execute('SELECT resource FROM oauth_code_resources WHERE hash=?',(s.digest(str(data.get('code',''))),)).fetchone()
            if audience and audience['resource']!=resource:raise s.Problem('Authorization code belongs to another origin',400,'invalid_grant')
            verifier=str(data.get('code_verifier',''));challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            if not code or code['client']!=data.get('client_id') or code['redirect']!=data.get('redirect_uri') or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier) or not secrets.compare_digest(challenge,code['challenge']):raise s.Problem('Authorization code could not be verified',400,'invalid_grant')
            db.execute('UPDATE codes SET used=1 WHERE hash=?',(code['hash'],))
            family=s.uid();f={'id':family,'owner':code['user_id'],'agent':code['agent'],'client':code['client'],'scopes':code['scopes'],'resource':resource}
            db.execute('INSERT INTO oauth_families VALUES(?,?,?,?,?,?,?,0)',(family,f['owner'],f['agent'],f['client'],f['scopes'],resource,s.now()+86400*30))
        elif typ=='refresh_token':
            old=db.execute('SELECT r.*,f.owner,f.agent,f.client,f.scopes,f.resource,f.expires,f.revoked FROM oauth_refresh r JOIN oauth_families f ON f.id=r.family WHERE r.hash=?',(s.digest(str(data.get('refresh_token',''))),)).fetchone()
            if not old or old['client']!=data.get('client_id') or old['resource']!=resource:raise s.Problem('Refresh token could not be verified',400,'invalid_grant')
            if old['used']:
                revoke_family(db,old['family']);invalid=True
            elif old['revoked'] or old['expires']<=s.now():invalid=True
            elif data.get('scope') and set(str(data['scope']).split())!=set(json.loads(old['scopes'])):raise s.Problem('Refresh scope cannot change',400,'invalid_scope')
            if not invalid:
                db.execute('UPDATE oauth_refresh SET used=1 WHERE hash=?',(old['hash'],))
                db.execute('UPDATE grants SET revoked=1 WHERE id IN (SELECT grant_id FROM oauth_access WHERE family=?)',(old['family'],))
                f=dict(old);f['id']=old['family']
        else:raise s.Problem('Unsupported grant type',400,'unsupported_grant_type')
        if not invalid:
            db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,0,NULL)',(grant,f['owner'],f['agent'],s.digest(access),f['scopes'],s.now()+3600))
            db.execute('INSERT INTO oauth_access VALUES(?,?)',(grant,f['id']))
            db.execute('INSERT INTO oauth_refresh VALUES(?,?,0,?)',(s.digest(refresh),f['id'],s.now()))
    # Commit replay revocation before raising.
    if invalid:raise s.Problem('Connection expired or revoked. Connect again.',400,'invalid_grant')
    return {'access_token':access,'refresh_token':refresh,'token_type':'Bearer','expires_in':3600,'scope':' '.join(json.loads(f['scopes']))}


def revoke(data):
    hashed=s.digest(str(data.get('token','')))
    with s.connection() as db:
        row=db.execute('SELECT f.id,f.client FROM oauth_refresh r JOIN oauth_families f ON f.id=r.family WHERE r.hash=? UNION SELECT f.id,f.client FROM grants g JOIN oauth_access a ON a.grant_id=g.id JOIN oauth_families f ON f.id=a.family WHERE g.hash=?',(hashed,hashed)).fetchone()
        if row and row['client']==data.get('client_id'):revoke_family(db,row['id'])
    return {}
