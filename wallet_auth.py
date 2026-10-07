"""Wallet-only login: bound nonce proof, no transaction or allowance."""
import re
import secrets
from datetime import datetime,timezone
from urllib.parse import urlsplit
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address
import service as s

# Out-of-band Guard approval can take ten minutes. Keep the signed expiry
# bounded and longer than that window; verify still enforces it exactly.
CHALLENGE_TTL_SECONDS = 15 * 60


def initialize():
    with s.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS wallet_logins(id TEXT PRIMARY KEY,address TEXT,message TEXT,expires INTEGER,used INTEGER DEFAULT 0)')
        # Wallet linking and wallet login share one identity per address.
        duplicate=db.execute('SELECT wallet FROM accounts WHERE wallet IS NOT NULL GROUP BY wallet HAVING count(*)>1').fetchone()
        if duplicate:raise RuntimeError('Duplicate wallet identities require review')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS account_wallet ON accounts(wallet) WHERE wallet IS NOT NULL')


def _proof(data,origin,statement):
    address=str(data.get('address','')).lower()
    if not re.fullmatch(r'0x[0-9a-f]{40}',address) or address==s.ZERO:raise s.Problem('Invalid wallet address')
    ident=s.uid();nonce=secrets.token_hex(16);expires=s.now()+CHALLENGE_TTL_SECONDS
    issued=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    expiry=datetime.fromtimestamp(expires,timezone.utc).isoformat().replace('+00:00','Z')
    msg=f'{urlsplit(origin).netloc} wants you to sign in with your Ethereum account:\n{to_checksum_address(address)}\n\n{statement} No transaction or spending permission.\n\nURI: {origin}\nVersion: 1\nChain ID: 143\nNonce: {nonce}\nIssued At: {issued}\nExpiration Time: {expiry}'
    return ident,address,msg,expires


def challenge(data,origin):
    ident,address,msg,expires=_proof(data,origin,'Sign in to Rally.')
    with s.connection() as db:
        db.execute('DELETE FROM wallet_logins WHERE expires<?',(s.now()-3600,))
        db.execute('INSERT INTO wallet_logins VALUES(?,?,?,?,0)',(ident,address,msg,expires))
    return {'id':ident,'message':msg,'expires':expires,'purpose':'sign_in','chainId':143}


def link_challenge(who,data,origin):
    user=s.require(who,human=True)
    ident,address,msg,expires=_proof(data,origin,'Link this wallet to your Rally account.')
    s.write('INSERT INTO challenges VALUES(?,?,?,?,?,?)',(ident,user,address,msg,expires,0))
    return {'id':ident,'message':msg,'expires':expires,'purpose':'link_wallet','chainId':143}


def verify(data,origin):
    ident=str(data.get('id',''));signature=str(data.get('signature',''))
    row=s.one('SELECT * FROM wallet_logins WHERE id=? AND used=0 AND expires>?',(ident,s.now()))
    if not row or f'URI: {origin}\n' not in row['message']:raise s.Problem('Login request expired. Try again.',401)
    if not re.fullmatch(r'0x[0-9a-fA-F]{130}',signature):raise s.Problem('Invalid login signature',401)
    try:address=Account.recover_message(encode_defunct(text=row['message']),signature=signature).lower()
    except Exception:raise s.Problem('Could not verify this wallet signature',401)
    if address!=row['address']:raise s.Problem('Signature does not match this wallet',401)
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('UPDATE wallet_logins SET used=1 WHERE id=? AND used=0 AND expires>?',(ident,s.now())).rowcount:raise s.Problem('Login request already used',401)
        user=db.execute("SELECT id,kind FROM accounts WHERE wallet=?",(address,)).fetchone()
        if user and user['kind']!='person':raise s.Problem('This wallet cannot sign in',403)
        if user:user_id=user['id']
        else:
            user_id=s.uid();handle='mon_'+user_id[:12]
            db.execute('INSERT INTO accounts(id,handle,name,kind,wallet,created) VALUES(?,?,?,?,?,?)',(user_id,handle,address[:6]+'…'+address[-4:],'person',address,s.now()))
            db.execute('INSERT OR IGNORE INTO follows VALUES(?,?)',(user_id,'rally'))
    return s.profile(user_id,user_id),s.session_for(user_id)
