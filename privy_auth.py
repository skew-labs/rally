"""Privy identity verification and additive Rally account linking. No signing keys."""
import json
import os
import re
import secrets
import threading
import time
from urllib.request import Request, urlopen
import jwt
import service as s

KEYS = {}
KEY_LOCK = threading.Lock()


def config():
    app = os.environ.get('RALLY_PRIVY_APP_ID', '').strip()
    client = os.environ.get('RALLY_PRIVY_CLIENT_ID', '').strip()
    valid = bool(re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', app))
    return {'enabled': valid, 'appId': app if valid else None,
            'clientId': client if re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', client) else None,
            'loginMethods': ['email', 'google', 'wallet'], 'chainId': 143}


def initialize():
    with s.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS external_identities(
          provider TEXT NOT NULL,app_id TEXT NOT NULL,subject TEXT NOT NULL,
          user_id TEXT NOT NULL REFERENCES accounts(id),created INTEGER NOT NULL,
          PRIMARY KEY(provider,app_id,subject))''')
        db.execute('CREATE INDEX IF NOT EXISTS external_identity_user ON external_identities(user_id)')


def status(user):
    cfg = config()
    linked = bool(user and cfg['enabled'] and s.one(
        'SELECT 1 FROM external_identities WHERE provider=? AND app_id=? AND user_id=?',
        ('privy', cfg['appId'], user)))
    return {**cfg, 'linked': linked}


def verification_key(app, kid):
    # The endpoint is fixed by the application, never by a JWT's jku/x5u header.
    with KEY_LOCK:
        cached = KEYS.get(app, {})
        fresh = time.monotonic() - cached.get('at', -3600) < 600
        if fresh and kid in cached.get('keys', {}):
            return cached['keys'][kid]
        if time.monotonic() - cached.get('at', -3600) < 60:
            raise s.Problem('Could not verify this login. Try again.', 401, 'privy_invalid_token')
        try:
            req = Request('https://auth.privy.io/api/v1/apps/' + app + '/jwks.json',
                          headers={'Accept': 'application/json', 'User-Agent': 'Rally-Auth/1'})
            with urlopen(req, timeout=5) as response:
                if response.geturl() != req.full_url:
                    raise ValueError('Unexpected key redirect')
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Oversized key response')
            keys = {}
            for key in json.loads(raw).get('keys', [])[:20]:
                if (key.get('kty') == 'EC' and key.get('crv') == 'P-256'
                        and key.get('alg', 'ES256') == 'ES256'
                        and key.get('use', 'sig') == 'sig' and isinstance(key.get('kid'), str)):
                    keys[key['kid']] = jwt.PyJWK.from_dict(key, algorithm='ES256').key
            if not keys:
                raise ValueError('No signing keys')
            KEYS[app] = {'at': time.monotonic(), 'keys': keys}
        except Exception:
            raise s.Problem('Login verification is unavailable. Try again shortly.', 503, 'privy_verification_unavailable') from None
        if kid not in keys:
            raise s.Problem('Could not verify this login. Try again.', 401, 'privy_invalid_token')
        return keys[kid]


def claims(token, app, identity=False):
    if not isinstance(token, str) or not 20 < len(token) < 32000:
        raise s.Problem('Complete the Privy login first.', 401, 'privy_invalid_token')
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get('kid')
        if header.get('alg') != 'ES256' or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            raise ValueError()
        key = verification_key(app, kid)
        value = jwt.decode(token, key, algorithms=['ES256'], issuer='privy.io', audience=app,
                           options={'require': ['exp', 'iat', 'sub', 'iss', 'aud'], 'strict_aud': True})
        if not re.fullmatch(r'did:privy:[a-zA-Z0-9_-]{3,128}', value.get('sub', '')):
            raise ValueError()
        if identity:
            if not isinstance(value.get('linked_accounts'), str):
                raise ValueError()
        elif not isinstance(value.get('sid'), str) or not value['sid'] or 'linked_accounts' in value:
            raise ValueError()
        return value
    except s.Problem:
        raise
    except Exception:
        raise s.Problem('This login expired or could not be verified. Try again.', 401, 'privy_invalid_token') from None


def login(who, data):
    cfg = config()
    if not cfg['enabled']:
        raise s.Problem('Email and social login are not available yet.', 503, 'privy_not_configured')
    access = claims(data.get('accessToken'), cfg['appId'])
    identity = claims(data.get('identityToken'), cfg['appId'], identity=True)
    if access['sub'] != identity['sub']:
        raise s.Problem('Login identities do not match. Try again.', 401, 'privy_identity_mismatch')
    try:
        linked = json.loads(identity['linked_accounts'])
        if not isinstance(linked, list) or len(linked) > 100:
            raise ValueError()
        wallets = sorted({x['address'].lower() for x in linked if isinstance(x, dict)
                          and x.get('type') == 'wallet' and x.get('chain_type') == 'ethereum'
                          and isinstance(x.get('address'), str)
                          and re.fullmatch(r'0x[0-9a-fA-F]{40}', x['address']) and x['address'].lower() != s.ZERO})
    except Exception:
        raise s.Problem('Could not read this login identity.', 401, 'privy_invalid_token') from None
    # Email, names and client-supplied addresses never decide account ownership.
    linking = data.get('link') is True
    current = s.require(who, human=True) if linking else None
    if who and who['grant']:
        raise s.Problem('Your account must approve this login.', 403)
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        found = db.execute('SELECT user_id FROM external_identities WHERE provider=? AND app_id=? AND subject=?',
                           ('privy', cfg['appId'], access['sub'])).fetchone()
        owners = {r['id'] for address in wallets for r in db.execute('SELECT id FROM accounts WHERE wallet=?', (address,))}
        if found:
            user = found['user_id']
            if current and current != user:
                raise s.Problem('This login belongs to another Rally account.', 409, 'privy_account_conflict')
        else:
            if len(owners) > 1 or current and owners - {current}:
                raise s.Problem('These wallets belong to different Rally accounts. Sign in with your original wallet.',
                                409, 'privy_account_conflict')
            user = current or next(iter(owners), None)
            if user is None:
                user = s.uid()
                db.execute('INSERT INTO accounts(id,handle,name,kind,wallet,created) VALUES(?,?,?,?,?,?)',
                           (user, 'mon_' + user[:12], 'New member', 'person', wallets[0] if len(wallets) == 1 else None, s.now()))
                db.execute('INSERT OR IGNORE INTO follows VALUES(?,?)', (user, 'rally'))
            if who and who['user'] != user:
                raise s.Problem('Sign out before switching accounts.', 409, 'privy_account_conflict')
            account = db.execute('SELECT kind FROM accounts WHERE id=?', (user,)).fetchone()
            if not account or account['kind'] != 'person':
                raise s.Problem('This account cannot sign in.', 403)
            db.execute('INSERT INTO external_identities VALUES(?,?,?,?,?)',
                       ('privy', cfg['appId'], access['sub'], user, s.now()))
        if who and who['user'] != user:
            raise s.Problem('Sign out before switching accounts.', 409, 'privy_account_conflict')
        account = db.execute('SELECT kind FROM accounts WHERE id=?', (user,)).fetchone()
        if not account or account['kind'] != 'person':
            raise s.Problem('This account cannot sign in.', 403)
        session = secrets.token_urlsafe(40)
        # A Rally session derived from Privy never outlives either verified JWT.
        expires = min(int(access['exp']), int(identity['exp']), s.now() + 3600)
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (s.digest(session), user, expires))
    return s.profile(user, user), session, max(0, expires - s.now())
