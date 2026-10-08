import base64
import os
import sys
import hashlib
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get("RALLY_TESTING") == "1", "Use isolated tests"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s
import native_auth as n


class NativeAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'qa.sqlite'
        self.db_patch=patch.object(s,'DB',self.db);self.db_patch.start()
        with s.connection() as db:
            db.execute('CREATE TABLE accounts(id TEXT PRIMARY KEY,kind TEXT)')
            db.execute('CREATE TABLE sessions(hash TEXT PRIMARY KEY,user_id TEXT,expires INTEGER)')
            db.execute("INSERT INTO accounts VALUES('alice','person')")
        self.who={'user':'alice','actor':'alice','grant':None,'scopes':s.SCOPES};self.origin='https://rally.example'
        self.verifier=secrets.token_urlsafe(32)
        self.challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('=')
        self.request=n.start({'challenge':self.challenge},self.origin)
    def tearDown(self):self.db_patch.stop();self.tmp.cleanup()
    def poll(self,**changes):return n.poll({'id':self.request['id'],'verifier':self.verifier,**changes},self.origin)
    def approve(self,allow=True):return n.approve(self.who,{'id':self.request['id'],'allow':allow},self.origin)
    def test_pending_has_no_session(self):self.assertEqual(self.poll(),{'state':'pending'})
    def test_phone_auth_round_trip_survives_the_old_three_minute_window(self):
        started=s.now()
        with patch.object(s,'now',return_value=started+540):
            self.assertEqual(self.poll(),{'state':'pending'})
            self.approve();self.assertEqual(self.poll()['state'],'approved')
    def test_phone_auth_is_still_bounded_to_ten_minutes(self):
        with patch.object(s,'now',return_value=s.now()+600):
            with self.assertRaises(s.Problem) as e:self.poll()
            self.assertEqual(e.exception.status,410)
    def test_explicit_consent_creates_only_hashed_session(self):
        self.approve();result=self.poll();self.assertEqual(result['state'],'approved');row=s.one('SELECT * FROM sessions');self.assertEqual(row['hash'],s.digest(result['session']));self.assertEqual(row['user_id'],'alice');self.assertEqual(s.one('SELECT state FROM native_pairing')['state'],'consumed')
    def test_code_is_four_digits_and_has_no_verifier(self):self.assertRegex(self.request['code'],r'^\d{4}$');self.assertNotIn(self.verifier,self.request['url'])
    def test_wrong_device_cannot_claim(self):
        self.approve()
        with self.assertRaises(s.Problem) as e:self.poll(verifier=secrets.token_urlsafe(32))
        self.assertEqual(e.exception.status,403);self.assertIsNone(s.one('SELECT * FROM sessions'))
    def test_cannot_replay(self):
        self.approve();self.poll()
        with self.assertRaises(s.Problem) as e:self.poll()
        self.assertEqual(e.exception.status,409)
    def test_denied_never_creates_session(self):self.approve(False);self.assertEqual(self.poll(),{'state':'denied'});self.assertIsNone(s.one('SELECT * FROM sessions'))
    def test_expired_cannot_claim(self):
        self.approve();s.write('UPDATE native_pairing SET expires=?',(1,))
        with self.assertRaises(s.Problem) as e:self.poll()
        self.assertEqual(e.exception.status,410)
    def test_cross_origin_cannot_approve(self):
        with self.assertRaises(s.Problem):n.approve(self.who,{'id':self.request['id'],'allow':True},'https://other.example')
    def test_anonymous_cannot_approve(self):
        with self.assertRaises(s.Problem) as e:n.approve(None,{'id':self.request['id'],'allow':True},self.origin)
        self.assertEqual(e.exception.status,401)
    def test_agent_grant_cannot_create_human_session(self):
        with self.assertRaises(s.Problem):n.approve({**self.who,'grant':'agent'}, {'id':self.request['id'],'allow':True},self.origin)
    def test_approval_is_single_use(self):
        self.approve()
        with self.assertRaises(s.Problem):self.approve()
    def test_reject_invalid_challenge_and_verifier(self):
        for bad in ['','../','A'*100,None]:
            with self.assertRaises(s.Problem):n.start({'challenge':bad},self.origin)
            with self.assertRaises(s.Problem):self.poll(verifier=bad)
    def test_consumption_is_atomic_under_competing_claims(self):
        from concurrent.futures import ThreadPoolExecutor
        self.approve()
        def claim(_):
            try:return self.poll()['state']
            except s.Problem:return 'rejected'
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(claim,range(2))),['approved','rejected'])
        self.assertEqual(s.one('SELECT count(*) AS n FROM sessions')['n'],1)

if __name__=='__main__':unittest.main()
