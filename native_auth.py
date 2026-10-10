"""First-party Android pairing. Browser consent plus a device-held S256 verifier.

This issues a human session after explicit consent, never an OAuth agent grant,
wallet permission, signing key or transaction. Codes are short lived and one use.
"""
import base64
import hashlib
import hmac
import re
import secrets
import service as s

TTL = 600
SESSION_TTL = 7 * 86400


def initialize():
    with s.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS native_pairing(id TEXT PRIMARY KEY,challenge TEXT NOT NULL,origin TEXT NOT NULL,expires INTEGER NOT NULL,state TEXT NOT NULL,user_id TEXT)')
        if 'session_hash' not in {r['name'] for r in db.execute('PRAGMA table_info(native_pairing)')}:
            db.execute('ALTER TABLE native_pairing ADD COLUMN session_hash TEXT')


def owned_request(ident, origin, db):
    if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise s.Problem('Invalid connection request', 400)
    row = db.execute('SELECT * FROM native_pairing WHERE id=? AND origin=?', (ident, origin)).fetchone()
    if not row or row['expires'] <= s.now():
        raise s.Problem('Connection expired. Start again in the app.', 410, 'native_expired')
    return row


def code(ident):
    return str(int(hashlib.sha256(ident.encode()).hexdigest()[:8], 16) % 10000).zfill(4)


def start(data, origin):
    challenge = data.get('challenge')
    if not isinstance(challenge, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', challenge):
        raise s.Problem('Invalid device challenge', 400)
    initialize()
    ident = secrets.token_hex(16)
    with s.connection() as db:
        db.execute('DELETE FROM native_pairing WHERE expires<=?', (s.now(),))
        if db.execute('SELECT count(*) FROM native_pairing').fetchone()[0] >= 500:
            raise s.Problem('Connections are busy. Try again shortly.', 429)
        db.execute('INSERT INTO native_pairing(id,challenge,origin,expires,state,user_id) VALUES(?,?,?,?,?,NULL)', (ident, challenge, origin, s.now()+TTL, 'pending'))
    return {'id': ident, 'code': code(ident), 'expiresIn': TTL, 'url': origin+'/connect-native?nativeRequest='+ident+'&view=account'}


def status(ident, origin):
    initialize()
    with s.connection() as db:
        row = owned_request(ident, origin, db)
        return {'state': row['state'], 'code': code(ident), 'expires': row['expires']}


def approve(who, data, origin):
    user = s.require(who, human=True)
    initialize()
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = owned_request(data.get('id'), origin, db)
        if row['state'] != 'pending':
            raise s.Problem('This connection has already been handled', 409)
        state = 'approved' if data.get('allow') is True else 'denied'
        db.execute('UPDATE native_pairing SET state=?,user_id=? WHERE id=?', (state, user if state=='approved' else None, row['id']))
    return {'state': state}


def poll(data, origin):
    verifier = data.get('verifier')
    if not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', verifier):
        raise s.Problem('Invalid device verifier', 400)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    initialize()
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = owned_request(data.get('id'), origin, db)
        if not hmac.compare_digest(challenge, row['challenge']):
            raise s.Problem('This connection belongs to another device', 403)
        # A device may recover a lost response without issuing another session.
        # Its random verifier stays on the device; only session hashes are stored.
        token = base64.urlsafe_b64encode(hmac.new(verifier.encode(), ('rally-native-session-v1\n'+origin+'\n'+row['id']).encode(), hashlib.sha256).digest()).decode().rstrip('=')
        if row['state'] == 'consumed':
            session = db.execute('SELECT * FROM sessions WHERE hash=? AND user_id=? AND expires>?', (s.digest(token), row['user_id'], s.now())).fetchone()
            if row['session_hash'] != s.digest(token) or not session:
                raise s.Problem('Connection was already used. Sign in again.', 409)
            return {'state': 'approved', 'session': token, 'expiresIn': session['expires']-s.now()}
        if row['state'] != 'approved':
            return {'state': row['state']}
        if not db.execute('SELECT 1 FROM accounts WHERE id=? AND kind=?', (row['user_id'], 'person')).fetchone():
            raise s.Problem('Sign in with a personal account', 403)
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (s.digest(token), row['user_id'], s.now()+SESSION_TTL))
        db.execute('UPDATE native_pairing SET state=?,session_hash=? WHERE id=?', ('consumed', s.digest(token), row['id']))
        return {'state': 'approved', 'session': token, 'expiresIn': SESSION_TTL}
