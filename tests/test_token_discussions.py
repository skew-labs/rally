"""Conversations and subscriptions with disposable accounts; providers forbidden."""
import os,unittest
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
import service as s,feed_subscriptions as subs,daily_change as daily

class DiscussionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  s.initialize();subs.initialize()
 def setUp(self):
  self.rpc=patch.object(s,'rpc',side_effect=AssertionError('No provider'));self.rpc.start()
  self.http=patch.object(s,'http_json',side_effect=AssertionError('No provider'));self.http.start()
  with s.connection() as db:
   for t in ['posts','notifications','blocks','feed_subscriptions','entitlements','settings']:db.execute('DELETE FROM '+t)
   for id in ['alice','bobby','carol']:
    db.execute('INSERT OR REPLACE INTO accounts(id,handle,name,kind,created) VALUES(?,?,?,?,?)',(id,id,id,'person',s.now()))
   for id,price in [('free','0'),('paid','1000000')]:db.execute('INSERT OR REPLACE INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient) VALUES(?,?,?,?,?,?,?,?,?)',(id,'alice',id,'[100,0,0]','[]',s.now(),price,1,'0x'+'a'*40))
  self.who=lambda u:{'user':u,'actor':u,'grant':None,'scopes':s.SCOPES}
  self.token='0x'+'a'*40;self.other='0x'+'b'*40
  s.GATEWAY.token_map[self.token]={'id':self.token,'symbol':'QA','name':'Fixture','decimals':18}
  s.GATEWAY.token_map[self.other]={'id':self.other,'symbol':'OTHER','decimals':18}
 def tearDown(self):self.rpc.stop();self.http.stop()
 def post(self,user='alice',**kw):return s.publish(self.who(user),{'text':'Fixture comment','asset':self.token,**kw})
 def feed(self,user='carol',**kw):return s.get_feed(self.who(user),{'discussion':'1','feed':'latest',**kw})['posts']
 def test_same_exact_token_comment_and_nested_replies(self):
  root=self.post();reply=s.publish(self.who('bobby'),{'text':'@alice why?','parent':root['id']})
  leaf=s.publish(self.who('carol'),{'text':'@bobby answered','parent':reply['id']})
  self.post(asset=self.other);self.post(asset=None,text='Unattached')
  rows=self.feed(asset=self.token.upper())
  self.assertEqual({p['id'] for p in rows},{root['id'],reply['id'],leaf['id']})
  self.assertEqual(reply['asset'],self.token);self.assertEqual(reply['mentions'],[{'id':'alice','handle':'alice'}])
  self.assertEqual(leaf['replyTo']['author']['handle'],'bobby')
  self.assertTrue(s.one("SELECT 1 FROM notifications WHERE owner='alice' AND kind='mention'"))
 def test_block_or_delete_ancestor_removes_entire_branch(self):
  root=self.post();reply=self.post('bobby',parent=root['id']);self.post('carol',parent=reply['id'])
  s.write('INSERT INTO blocks VALUES(?,?,?)',('carol','bobby',s.now()))
  self.assertEqual([x['id'] for x in self.feed()],[root['id']])
  s.write('DELETE FROM blocks');s.write('UPDATE posts SET deleted=1 WHERE id=?',(root['id'],))
  self.assertEqual(self.feed(),[])
  with self.assertRaises(s.Problem):self.post('carol',parent=reply['id'])
 def test_other_token_reply_rejected_and_key_deduplicated(self):
  root=self.post()
  with self.assertRaises(s.Problem):self.post('bobby',parent=root['id'],asset=self.other)
  data={'parent':root['id'],'text':'Same reply'}
  a=s.publish(self.who('bobby'),data,'same');b=s.publish(self.who('bobby'),data,'same')
  self.assertEqual(a['id'],b['id'])
 def test_public_legacy_reply_inherits_token_and_no_provider(self):
  root=self.post();s.write('INSERT INTO posts(id,author,text,parent,created) VALUES(?,?,?,?,?)',('legacy','bobby','old reply',root['id'],s.now()))
  rows=self.feed(asset=self.token);self.assertEqual(next(x for x in rows if x['id']=='legacy')['asset'],self.token)
 def test_cursor_and_paid_rank_access(self):
  for i in range(35):self.post(text='Fixture '+str(i))
  first=s.get_feed(self.who('carol'),{'discussion':'1','feed':'latest'})
  second=s.get_feed(self.who('carol'),{'discussion':'1','feed':'latest','cursor':first['cursor']})
  self.assertEqual(len(first['posts']),30);self.assertEqual(len(second['posts']),5)
  self.assertFalse({x['id'] for x in first['posts']} & {x['id'] for x in second['posts']})
  with self.assertRaises(s.Problem):self.feed(feed='paid')
 def test_subscription_persists_and_removal_keeps_entitlement(self):
  who=self.who('carol');subs.update(who,{'id':'free'})
  def state():return {f['id']:f for f in subs.decorate(s.bootstrap(who,include_markets=False),who)['feeds']}
  self.assertTrue(state()['free']['subscribed']);self.assertFalse(state()['paid']['subscribed'])
  with self.assertRaises(s.Problem):subs.update(who,{'id':'paid'})
  s.write('INSERT INTO entitlements VALUES(?,?,?,?)',('carol','paid',1,s.now()+3600));subs.update(who,{'id':'paid'})
  subs.update(who,{'id':'paid','active':False});self.assertFalse(state()['paid']['subscriptionSaved']);self.assertTrue(state()['paid']['access'])
  self.assertIsNotNone(s.one('SELECT * FROM entitlements WHERE buyer=?',('carol',)))
  self.assertEqual(s.one('SELECT feed FROM settings WHERE user_id=?',('carol',))['feed'],'latest')
 def test_subscription_expiry_other_user_and_agent_grant(self):
  s.write('INSERT INTO entitlements VALUES(?,?,?,?)',('carol','paid',1,s.now()-1))
  who=self.who('carol');entry=next(f for f in subs.decorate(s.bootstrap(who,include_markets=False),who)['feeds'] if f['id']=='paid')
  self.assertEqual(entry['subscriptionState'],'expired')
  with self.assertRaises(s.Problem):subs.update(None,{'id':'free'})
  with self.assertRaises(s.Problem):subs.update({**who,'grant':'qa-grant'},{'id':'free'})
  with self.assertRaises(s.Problem):subs.update(who,{'id':'free','active':'false'})
  other=self.who('bobby');self.assertFalse(next(f for f in subs.decorate(s.bootstrap(other,include_markets=False),other)['feeds'] if f['id']=='paid')['subscriptionSaved'])

class DailyChangeTests(unittest.TestCase):
 def test_same_pool_tick_recalculates_without_extending_original_age(self):
  old={'price':2,'change':100,'fetchedAt':100,'pair':'0xabc','priceSource':'fixture'}
  current={'price':3,'change':None,'fetchedAt':120,'pair':'0xABC'}
  result=daily.preserve(current,old,120);self.assertEqual(result['change'],200);self.assertEqual(result['changeObservedAt'],100)
  self.assertIsNone(daily.preserve({**current,'fetchedAt':281},result,281)['change'])
 def test_no_baseline_or_different_pool_remains_unknown(self):
  a={'price':2,'change':None,'fetchedAt':100,'pair':'a'}
  self.assertIsNone(daily.preserve(a,{},100)['change'])
  self.assertIsNone(daily.preserve(a,{**a,'change':10,'pair':'b'},100)['change'])
  self.assertIsNone(daily.preserve(a,{**a,'change':float('nan')},100)['change'])

if __name__=='__main__':unittest.main()
