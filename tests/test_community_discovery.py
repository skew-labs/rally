"""Stored community counts and token identity; providers are forbidden."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,community_discovery as directory


class Communities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rpc=patch.object(s,'rpc',side_effect=AssertionError('Provider call forbidden'));cls.rpc.start()
        cls.http=patch.object(s,'http_json',side_effect=AssertionError('Provider call forbidden'));cls.http.start()
        s.initialize()
    @classmethod
    def tearDownClass(cls):cls.rpc.stop();cls.http.stop()
    def setUp(self):
        with s.connection() as db:
            for table in ['posts','members','communities','creator_tokens','blocks']:db.execute('DELETE FROM '+table)
            for ident,kind,owner in [('owner','person',None),('reader','person',None),('agent','agent','owner')]:
                db.execute('INSERT OR REPLACE INTO accounts(id,handle,name,kind,owner,created) VALUES(?,?,?,?,?,?)',(ident,ident,ident,kind,owner,s.now()))
            db.execute('INSERT INTO communities VALUES(?,?,?)',('room','Room','A real community'))
            db.execute('INSERT INTO members VALUES(?,?)',('owner','room'))
            for ident,created,deleted,parent,author in [('fresh',s.now(),0,None,'owner'),('old',s.now()-86401,0,None,'owner'),('deleted',s.now(),1,None,'owner'),('reply',s.now(),0,'fresh','reader'),('agent-post',s.now(),0,None,'agent')]:
                db.execute('INSERT INTO posts(id,author,text,community,created,deleted,parent) VALUES(?,?,?,?,?,?,?)',(ident,author,'Public text','room',created,deleted,parent))
    def test_counts_are_visible_top_level_posts_in_real_window(self):
        item=directory.catalog()[0]
        self.assertEqual((item['posts'],item['posts24h'],item['members']),(3,2,1))
        self.assertFalse(item['joined']);self.assertIsNone(item['token']);self.assertIsNotNone(item['lastPostAt'])
    def test_blocked_owner_and_agent_do_not_leak_activity(self):
        s.write('INSERT INTO blocks VALUES(?,?,?)',('reader','owner',s.now()))
        item=directory.catalog('reader')[0]
        self.assertEqual((item['posts'],item['posts24h']),(0,0));self.assertIsNone(item['lastPostAt'])
    def test_membership_and_zero_activity_are_not_inferred(self):
        s.write('INSERT INTO communities VALUES(?,?,?)',('empty','Empty',''))
        s.write('INSERT INTO members VALUES(?,?)',('reader','room'))
        items={r['id']:r for r in directory.catalog('reader')}
        self.assertTrue(items['room']['joined']);self.assertEqual(items['room']['members'],2)
        self.assertEqual(items['empty']['posts24h'],0);self.assertIsNone(items['empty']['lastPostAt'])
    def test_token_identity_is_available_without_people_list_or_provider(self):
        address='0x'+'a'*40
        s.write('INSERT INTO creator_tokens(owner,state,community) VALUES(?,?,?)',('owner','live','room'))
        with patch('community_tokens.public',return_value={'address':address,'symbol':'TEST','asset':{'id':address}}),patch.dict(s.GATEWAY.token_map,{s.USDC:{'id':s.USDC,'symbol':'USDC','decimals':6}}):
            item=directory.catalog()[0]
            self.assertEqual(item['token']['address'],address);self.assertEqual(item['token']['quoteAsset']['id'],s.USDC)
            s.write('INSERT INTO blocks VALUES(?,?,?)',('reader','owner',s.now()))
            self.assertIsNone(directory.catalog('reader')[0]['token'])


if __name__=='__main__':unittest.main()
