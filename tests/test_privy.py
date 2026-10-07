"""Privy verified identity and versioned bundle boundaries. No provider login."""
import os,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
assert os.environ.get('RALLY_TESTING')=='1'
import service as s,privy_auth as p

class Privy(unittest.TestCase):
    def setUp(self):
        self.key=ec.generate_private_key(ec.SECP256R1());self.app='fixture-public-app'
        self.claims={'iss':'privy.io','aud':self.app,'sub':'did:privy:fixture','sid':'fixture-session','iat':int(time.time()),'exp':int(time.time())+300}
        self.keys=patch.object(p,'verification_key',return_value=self.key.public_key());self.lookup=self.keys.start();self.addCleanup(self.keys.stop)
    def token(self,value=None,headers=None):return jwt.encode(value or self.claims,self.key,algorithm='ES256',headers=headers or {'kid':'fixture'})
    def test_access_token_identity(self):self.assertEqual(p.claims(self.token(),self.app)['sub'],self.claims['sub'])
    def test_wrong_issuer_audience_expiry_subject_and_missing_session(self):
        for field,value in [('iss','other'),('aud','other-app'),('exp',int(time.time())-1),('sub','wallet:unverified'),('sid','')]:
            with self.subTest(field=field),self.assertRaises(s.Problem):p.claims(self.token({**self.claims,field:value}),self.app)
    def test_identity_and_access_tokens_are_not_interchangeable(self):
        identity={**self.claims,'linked_accounts':json.dumps([])};identity.pop('sid')
        self.assertEqual(p.claims(self.token(identity),self.app,identity=True)['sub'],self.claims['sub'])
        with self.assertRaises(s.Problem):p.claims(self.token(identity),self.app)
        with self.assertRaises(s.Problem):p.claims(self.token(),self.app,identity=True)
    def test_missing_kid_rejected_before_provider(self):
        with self.assertRaises(s.Problem):p.claims(self.token(headers={'typ':'JWT'}),self.app)
        self.lookup.assert_not_called()
    def test_oversized_token_rejected(self):
        with self.assertRaises(s.Problem):p.claims('a'*32001,self.app)
        self.lookup.assert_not_called()
    def test_signed_identity_mismatch_rejected(self):
        identity={**self.claims,'sub':'did:privy:other','linked_accounts':'[]'};identity.pop('sid')
        with patch.dict(os.environ,{'RALLY_PRIVY_APP_ID':self.app}),self.assertRaises(s.Problem) as error:p.login(None,{'accessToken':self.token(),'identityToken':self.token(identity)})
        self.assertEqual(error.exception.code,'privy_identity_mismatch')
    def test_bridge_manifest_cannot_escape_assets(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(s,'ROOT',Path(directory)):
            auth=Path(directory)/'assets/auth';auth.mkdir(parents=True)
            for entry in ['../../private/session.json','https://attacker.example/bundle.js','privy-bridge-ABCDEFGH.js']:
                (auth/'manifest.json').write_text(json.dumps({'entry':entry}));self.assertEqual(p.config()['bridgeURL'],'/assets/auth/privy-bridge.js')
            (auth/'privy-bridge-ABCDEFGH.js').write_text('export const fixture=true;')
            self.assertEqual(p.config()['bridgeURL'],'/assets/auth/privy-bridge-ABCDEFGH.js')

if __name__=='__main__':unittest.main(verbosity=2)
