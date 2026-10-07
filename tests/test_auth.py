"""Ownership and scope boundaries in a fresh fixture database."""
import os
import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s
import agent_wallet as agent
import live_server
import oauth_sessions as oauth

class Authorization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(s,'rpc',side_effect=AssertionError('No RPC')),patch.object(s,'http_json',side_effect=AssertionError('No provider')):
            s.initialize();agent.initialize()
    def test_financial_scopes_are_not_grantable(self):
        self.assertEqual(s.SCOPES,{'feed:read','posts:write','replies:write','media:upload','markets:read'})
    def test_agent_cannot_become_a_human_financial_actor(self):
        who={'user':'owner','actor':'agent','grant':'grant','scopes':list(s.SCOPES)}
        with self.assertRaises(s.Problem) as error:s.require(who,human=True)
        self.assertEqual(error.exception.status,403)
    def test_read_only_connection_cannot_publish(self):
        who={'user':'owner','actor':'agent','grant':'grant','scopes':['feed:read']}
        with self.assertRaises(s.Problem):s.require(who,'posts:write')
    def test_mcp_exposes_no_financial_or_signing_tool(self):
        self.assertEqual({item['name'] for item in live_server.TOOLS},{'feed.read','posts.publish','posts.edit','media.upload','media.prepare_upload','markets.search','profile.read'})
    def test_absent_pairing_disables_agent_wallet(self):
        self.assertEqual(agent.profiles(),{})
    def test_stored_bearer_token_must_match_active_grant(self):
        with self.assertRaises(s.Problem) as error:s.identity(bearer='not-a-real-token')
        self.assertEqual(error.exception.status,401)

class OAuthRotation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s.initialize()
        for user,kind,owner in [('test-owner','person',None),('test-agent','agent','test-owner')]:
            s.write('INSERT OR IGNORE INTO accounts(id,handle,name,kind,owner,created) VALUES(?,?,?,?,?,?)',(user,user,user,kind,owner,s.now()))
    def setUp(self):
        self.resource='https://rally.example/mcp';self.verifier='v'*43
        challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('=')
        self.code=s.uid();self.client=s.uid();self.redirect='https://client.example/callback'
        s.write('INSERT INTO codes VALUES(?,?,?,?,?,?,?,?,?)',(s.digest(self.code),'test-owner','test-agent',self.client,self.redirect,challenge,json.dumps(['feed:read']),s.now()+120,0))
        s.write('INSERT INTO oauth_code_resources VALUES(?,?)',(s.digest(self.code),self.resource))
    def exchange(self,**change):
        return oauth.token({'grant_type':'authorization_code','code':self.code,'client_id':self.client,'redirect_uri':self.redirect,'code_verifier':self.verifier,**change},self.resource)
    def refresh(self,token,**change):
        return oauth.token({'grant_type':'refresh_token','refresh_token':token,'client_id':self.client,**change},self.resource)
    def rejected(self,token):
        with self.assertRaises(s.Problem) as error:s.identity(bearer=token)
        self.assertEqual(error.exception.status,401)
    def test_rotation_replaces_old_access_and_reuse_revokes_family(self):
        first=self.exchange();self.assertIsNotNone(s.identity(bearer=first['access_token']))
        second=self.refresh(first['refresh_token']);self.rejected(first['access_token'])
        self.assertIsNotNone(s.identity(bearer=second['access_token']))
        with self.assertRaises(s.Problem):self.refresh(first['refresh_token'])
        self.rejected(second['access_token'])
    def test_code_cannot_be_replayed(self):
        self.exchange()
        with self.assertRaises(s.Problem):self.exchange()
    def test_wrong_pkce_and_redirect_do_not_consume_code(self):
        for change in [{'code_verifier':'x'*43},{'redirect_uri':'https://other.example/callback'}]:
            with self.assertRaises(s.Problem):self.exchange(**change)
        self.assertIn('access_token',self.exchange())
    def test_refresh_cannot_broaden_scopes_or_change_audience(self):
        first=self.exchange()
        for change in [{'scope':'feed:read posts:write'},{'resource':'https://other.example/mcp'}]:
            with self.assertRaises(s.Problem):self.refresh(first['refresh_token'],**change)
        self.assertIn('access_token',self.refresh(first['refresh_token']))
    def test_revocation_disables_access(self):
        first=self.exchange();oauth.revoke({'client_id':self.client,'token':first['refresh_token']})
        self.rejected(first['access_token'])

if __name__=='__main__':unittest.main()
