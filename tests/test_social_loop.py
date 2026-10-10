"""Behavior and boundary tests; isolated records, no provider requests or funds."""
import base64,json,unittest
from unittest.mock import patch
from decimal import Decimal
import service as s
import social_loop as loop
import token_benefits as benefits
import push_delivery as push
import algorithm_league as league
import settlement,discovery,social
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

TOKEN='0x'+'a'*40
OTHER='0x'+'b'*40
WALLET='0x'+'c'*40
TX='0x'+'d'*64
BLOCK='0x'+'e'*64

class SocialLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):s.initialize()
    def setUp(self):
        self.clock=1791594000;self.timer=patch('service.now',lambda:self.clock);self.timer.start()
        loop.MARKET_CURSOR=('', '');loop.MIGRATION_CURSOR=('', '');push.OWNER_CURSOR=''
        for table in ['signals','signal_points','trade_shares','market_alerts','league_entries','league_rounds','league_runs','league_marks','holder_proofs','token_benefits','push_devices','push_queue','push_settings','notifications','orders','quotes','execution_records','execution_plans','invoices','entitlements','activity_context','feed_alerts','follows','watches','blocks','reactions']:
            s.write('DELETE FROM '+table)
        s.write("DELETE FROM posts WHERE author!='rally'");s.write("DELETE FROM feeds WHERE owner!='rally'")
        for owner in ['creator','reader','third']:
            s.write('INSERT OR REPLACE INTO accounts(id,handle,name,kind,wallet,created) VALUES(?,?,?,?,?,?)',(owner,owner,owner,'person',{'reader':WALLET,'creator':OTHER,'third':'0x'+'f'*40}[owner],self.clock))
        s.GATEWAY.token_map[TOKEN]={'id':TOKEN,'address':TOKEN,'decimals':18,'symbol':'TEST','name':'Test','chainId':143}
        s.GATEWAY.token_map[s.USDC]={'id':s.USDC,'address':s.USDC,'decimals':6,'symbol':'USDC','name':'USDC'}
        s.GATEWAY.prices[TOKEN]={'price':'1','fetchedAt':self.clock,'source':'Fixture reference'}
        s.write('DELETE FROM nad_tokens WHERE address=?',(TOKEN,))
        __import__('nadfun').MARKET_REFERENCES.pop(TOKEN,None)
        self.creator={'user':'creator','actor':'creator','scopes':s.SCOPES,'grant':None}
        self.reader={'user':'reader','actor':'reader','scopes':s.SCOPES,'grant':None}
    def tearDown(self):self.timer.stop()
    def feed(self,price='1000000'):
        s.write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient) VALUES(?,?,?,?,?,?,?,?,?)',('test-feed','creator','Test','[100,0,0]','[]',self.clock,price,1,OTHER))
        return s.one('SELECT * FROM feeds WHERE id=?',('test-feed',))
    def signal(self,key='test'):
        return s.publish(self.creator,{'text':'Signal','asset':TOKEN,'signal':{'target':'2','invalidation':'.5','hours':24}},key)
    def policy(self):
        self.feed();s.write('INSERT INTO token_benefits VALUES(?,?,?,?,?)',('creator',TOKEN,s.dump({'tiers':[{'label':'Member','minimum':'100','minimumRaw':str(100*10**18),'discountBps':2000,'feeds':['test-feed']}],'gatedFeeds':['test-feed']}),1,self.clock))
    def proof(self,balance=100*10**18,wallet=WALLET):
        s.write('INSERT OR REPLACE INTO holder_proofs VALUES(?,?,?,?,?,?,?,?,?,?)',('creator','reader',wallet,TOKEN,str(balance),100,BLOCK,self.clock,self.clock+120,1))
    def receipt(self,qty=10**18):
        def log(token,src,dst,amount):return {'address':token,'topics':[discovery.TRANSFER,'0x'+src[2:].rjust(64,'0'),'0x'+dst[2:].rjust(64,'0')],'data':hex(amount)}
        return {'status':'0x1','transactionHash':TX,'blockHash':BLOCK,'blockNumber':'0x64','logs':[log(s.USDC,WALLET,OTHER,1000000),log(TOKEN,OTHER,WALLET,qty)]}
    def order(self,state='finalized'):
        s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',('quote','reader',WALLET,s.USDC,TOKEN,'1000000',s.dump({'provider':'Kuru Flow','receive':'999'}),self.clock+60))
        s.write('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',('order','reader','quote',TX,state,s.dump(self.receipt()),self.clock))
    def subscription(self):
        key=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
        return {'endpoint':'https://fcm.googleapis.com/fcm/send/'+('a'*50),'keys':{'p256dh':enc(key),'auth':enc(b'x'*16)}}
    def test_signal_server_price_and_idempotence(self):
        p=self.signal();self.assertEqual(p['signal']['entry']['price'],'1');self.assertEqual(p['signal']['entry']['observedAt'],self.clock)
        self.clock+=500;p2=self.signal();self.assertEqual(p2['id'],p['id']);self.assertEqual(s.one('SELECT count(*) n FROM signals')['n'],1)
    def test_signal_idempotence_changed_terms_rejected(self):
        self.signal()
        with self.assertRaises(s.Problem):s.publish(self.creator,{'text':'Signal','asset':TOKEN,'signal':{'target':'3','invalidation':'.5','hours':24}},'test')
    def test_stale_signal_rolls_back_post(self):
        s.GATEWAY.prices[TOKEN]['fetchedAt']=self.clock-181
        with self.assertRaises(s.Problem):self.signal()
        self.assertFalse(s.one("SELECT 1 FROM posts WHERE author='creator'"))
    def test_future_or_wrong_chain_reference_rejected(self):
        s.GATEWAY.prices[TOKEN]['fetchedAt']=self.clock+1;self.assertIsNone(loop.reference(TOKEN))
        s.GATEWAY.prices[TOKEN]['fetchedAt']=self.clock;s.GATEWAY.prices[TOKEN]['chainId']=1;self.assertIsNone(loop.reference(TOKEN))
    def test_signal_target_and_failure_retained(self):
        p=self.signal();self.clock+=30;s.GATEWAY.prices[TOKEN].update(price='.4',fetchedAt=self.clock);loop.tick_signals()
        self.assertEqual(loop.track_record(None,'creator')['counts']['invalidated'],1)
        s.write('UPDATE posts SET deleted=1 WHERE id=?',(p['id'],));record=loop.track_record(None,'creator');self.assertEqual(record['counts']['invalidated'],1);self.assertEqual(record['withdrawn'],1);self.assertEqual(record['signals'],[])
    def test_target_crossing_not_realized_profit(self):
        p=self.signal();self.clock+=30;s.GATEWAY.prices[TOKEN].update(price='2.1',fetchedAt=self.clock);loop.tick_signals()
        card=loop.enrich({'id':p['id']})['signal'];self.assertEqual(card['state'],'target_reached');self.assertAlmostEqual(card['priceChangePercent'],110);self.assertNotIn('roi',card)
    def test_stale_price_does_not_cross_target(self):
        self.signal();self.clock+=500;s.GATEWAY.prices[TOKEN]['price']='9';loop.tick_signals();self.assertEqual(s.one('SELECT state FROM signals')['state'],'active')
    def test_expiry_does_not_use_late_price(self):
        self.signal();self.clock+=86410;s.GATEWAY.prices[TOKEN].update(price='9',fetchedAt=self.clock);loop.tick_signals();self.assertEqual(s.one('SELECT state,last FROM signals')['state'],'expired');self.assertEqual(json.loads(s.one('SELECT last FROM signals')['last'])['price'],'1')
    def test_agent_signal_requires_existing_scope(self):
        with self.assertRaises(s.Problem):s.publish({**self.creator,'scopes':{'feed:read'},'grant':'g'},{'text':'x','asset':TOKEN,'signal':{'target':'2','invalidation':'.5','hours':24}})
    def test_agent_signal_attribution_is_author_and_not_operator(self):
        s.write('INSERT OR REPLACE INTO accounts(id,handle,name,kind,owner,created) VALUES(?,?,?,?,?,?)',('agent','agent','Agent','agent','creator',self.clock))
        p=s.publish({**self.creator,'actor':'agent','grant':'g'},{'text':'Agent call','asset':TOKEN,'signal':{'target':'2','invalidation':'.5','hours':24}},'agent-call')
        self.assertEqual(loop.track_record(None,'agent')['total'],1);self.assertEqual(loop.track_record(None,'creator')['total'],0)
        self.clock+=30;s.GATEWAY.prices[TOKEN].update(price='.4',fetchedAt=self.clock);loop.tick_signals();self.assertEqual(s.one("SELECT owner FROM notifications WHERE post=?",(p['id'],))['owner'],'creator')
    def test_track_record_retains_old_failures_beyond_display_limit(self):
        p=self.signal();s.write("UPDATE signals SET state='invalidated'");s.write('UPDATE posts SET deleted=1 WHERE id=?',(p['id'],))
        with s.connection()as db:
            for i in range(1001):
                key='history-'+str(i);db.execute('INSERT INTO posts(id,author,text,created) VALUES(?,?,?,?)',(key,'creator','call',self.clock+i+1))
                db.execute('INSERT INTO signals(post,owner,asset,terms,entry,observed,expires,last,updated) SELECT ?,owner,asset,terms,entry,?,expires,entry,updated FROM signals WHERE post=?',(key,self.clock+i+1,p['id']))
        record=loop.track_record(None,'creator');self.assertEqual(record['total'],1002);self.assertEqual(record['counts']['invalidated'],1);self.assertEqual(record['withdrawn'],1);self.assertEqual(len(record['signals']),30)
    def test_own_finalized_fill_uses_receipt_not_quote(self):
        self.order();p=loop.share(self.reader,{'trade':'order'});self.assertEqual(p['verifiedTrade']['quantity'],'1');self.assertEqual(p['verifiedTrade']['tx'],TX)
        self.assertEqual(loop.share(self.reader,{'trade':'order'})['id'],p['id'])
    def test_pending_and_foreign_trade_cannot_share(self):
        self.order('confirmed')
        with self.assertRaises(s.Problem):loop.share(self.reader,{'trade':'order'})
        with self.assertRaises(s.Problem):loop.share(self.creator,{'trade':'order'})
    def test_actual_delivery_required(self):
        self.order();r=self.receipt(0);s.write('UPDATE orders SET receipt=?',(s.dump(r),))
        with self.assertRaises(s.Problem):loop.share(self.reader,{'trade':'order'})
    def test_spent_input_required(self):
        self.order();r=self.receipt();r['logs']=r['logs'][1:];s.write('UPDATE orders SET receipt=?',(s.dump(r),))
        with self.assertRaises(s.Problem):loop.share(self.reader,{'trade':'order'})
    def test_perpl_actual_partial_fill_and_market_identity(self):
        payload={'summary':{'marketId':7,'market':'BTC','direction':'long','reduceOnly':False}}
        outcome={'receipt':self.receipt(),'businessState':'partial_fill','fillQuantity':'0.001','entryPrice':'63000'}
        s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',('plan','reader',WALLET,'perpl','order',s.dump(payload),self.clock+60))
        s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('record','reader','plan',TX,'finalized',s.dump(outcome),self.clock))
        post=loop.share(self.reader,{'trade':'record'});self.assertEqual(post['verifiedTrade']['quantity'],'0.001');self.assertEqual(post['verifiedTrade']['marketId'],7);self.assertEqual(post['verifiedTrade']['label'],'Opened long')
        outcome['businessState']='order_placed';s.write('UPDATE execution_records SET outcome=?',(s.dump(outcome),))
        with self.assertRaises(s.Problem):loop.fill('reader','record')
    def test_withdraw_removed_from_following(self):
        self.order();s.write('INSERT INTO follows VALUES(?,?)',('third','reader'));p=loop.share(self.reader,{'trade':'order'});who={**self.reader,'user':'third','actor':'third'}
        self.assertEqual(len(s.get_feed(who,{'mode':'trades'})['posts']),1);loop.withdraw(self.reader,{'post':p['id']});self.assertEqual(s.get_feed(who,{'mode':'trades'})['posts'],[])
        with self.assertRaises(s.Problem):loop.share(self.reader,{'trade':'order'})
    def test_grant_cannot_share_or_set_benefits(self):
        for fn,data in [(loop.share,{'trade':'order'}),(benefits.save,{'tiers':[]}),(push.configure,{'enabled':True}),(league.enroll,{'feed':'x'})]:
            with self.assertRaises(s.Problem):fn({**self.reader,'grant':'g'},data)
    def test_holder_unlock_discount_and_badge(self):
        self.policy();self.proof();f=s.one('SELECT * FROM feeds WHERE id=?',('test-feed',));self.assertTrue(settlement.allowed(f,'reader'));self.assertEqual(settlement.view(f,'reader')['priceRaw'],'800000');self.assertEqual(benefits.badges('reader')[0]['label'],'Member')
    def test_expired_or_switched_wallet_fails_closed(self):
        self.policy();self.proof();f=s.one('SELECT * FROM feeds WHERE id=?',('test-feed',));self.clock+=121;self.assertFalse(settlement.allowed(f,'reader'));self.assertEqual(benefits.price(f,'reader')['amountRaw'],'1000000');self.assertEqual(benefits.badges('reader'),[])
        self.clock-=121;s.write('UPDATE accounts SET wallet=? WHERE id=?',('0x'+'1'*40,'reader'));self.assertFalse(settlement.allowed(f,'reader'))
    def test_paid_access_retained_after_holding_loss(self):
        self.policy();self.proof(0);s.write('INSERT INTO entitlements VALUES(?,?,?,?)',('reader','test-feed',1,self.clock+1000));self.assertTrue(settlement.allowed(s.one('SELECT * FROM feeds WHERE id=?',('test-feed',)),'reader'))
    def test_free_gated_feed_not_public(self):
        self.policy();s.write("UPDATE feeds SET price_raw='0'");f=s.one('SELECT * FROM feeds WHERE id=?',('test-feed',));self.assertFalse(settlement.allowed(f,None));self.assertFalse(settlement.allowed(f,'reader'));self.proof();self.assertTrue(settlement.allowed(f,'reader'))
    def test_checkout_discount_invalidation(self):
        self.policy();self.proof();a=settlement.checkout(self.reader,{'feed':'test-feed'});self.assertEqual(a['amountRaw'],'800000');self.clock+=121;b=settlement.checkout(self.reader,{'feed':'test-feed'});self.assertNotEqual(a['id'],b['id']);self.assertEqual(b['amountRaw'],'1000000')
    def test_prepare_rechecks_holder_price_without_requesting_wallet(self):
        self.policy();self.proof();a=settlement.checkout(self.reader,{'feed':'test-feed'});self.clock+=121
        with patch('service.rpc',side_effect=AssertionError('No provider request')):
            with self.assertRaises(s.Problem)as e:settlement.prepare(self.reader,{'invoice':a['id']})
        self.assertEqual(e.exception.code,'price_changed')
    def test_finalized_holdings_wallet_binding(self):
        self.policy()
        with patch('service.rpc',side_effect=[{'number':'0x64','hash':BLOCK},'0x'+hex(100*10**18)[2:].rjust(64,'0')])as rpc:
            d=benefits.refresh(self.reader,{'owner':'creator'});self.assertTrue(d['verified']);self.assertEqual(rpc.call_args_list[1].args[1][-1],'0x64')
    def test_invalid_tiers_do_not_update(self):
        fake={'address':TOKEN}
        with patch('community_tokens.public',return_value=fake):
            for data in [{'tiers':[{'label':'x','minimum':'NaN'}]},{'tiers':[{'label':'x','minimum':'1','feeds':['foreign']}]},{'tiers':[{'label':'x','minimum':'1','discountBps':10000}]}]:
                with self.assertRaises(s.Problem):benefits.save(self.creator,data)
        self.assertIsNone(benefits.policy('creator'))
    def test_push_private_keys_and_endpoint_validation(self):
        config=push.config();self.assertFalse(config['android']);self.assertEqual(len(base64.urlsafe_b64decode(config['applicationServerKey']+'=')),65)
        valid=self.subscription();self.assertEqual(push.subscription(valid),valid)
        for url in ['https://127.0.0.1/push/abc','https://fcm.googleapis.com.evil.test/push/abc','https://fcm.googleapis.com:bad/push/abc','https://user@fcm.googleapis.com/push/abc','http://fcm.googleapis.com/push/abc']:
            with self.assertRaises(s.Problem):push.subscription({**valid,'endpoint':url})
    def test_device_cannot_be_stolen(self):
        d=push.register(self.reader,{'kind':'web','subscription':self.subscription()})
        with self.assertRaises(s.Problem):push.register(self.creator,{'kind':'web','subscription':json.loads(s.one('SELECT payload FROM push_devices WHERE id=?',(d['id'],))['payload'])})
    def test_no_old_push_and_idempotent_queue(self):
        push.emit('reader','social','old','Rally','old','/?view=notifications');push.register(self.reader,{'kind':'web','subscription':self.subscription()});push.configure(self.reader,{'enabled':True});push.enqueue();self.assertEqual(s.one('SELECT count(*) n FROM push_queue')['n'],0)
        push.emit('reader','social','new','Rally','new','/?view=notifications');push.enqueue();push.enqueue();self.assertEqual(s.one('SELECT count(*) n FROM push_queue')['n'],1)
    def test_disabled_push_cancels_delivery(self):
        push.register(self.reader,{'kind':'web','subscription':self.subscription()});push.configure(self.reader,{'enabled':True});push.emit('reader','social','new','Rally','new','/?view=notifications');push.enqueue();push.configure(self.reader,{'enabled':False})
        with patch('push_delivery.send')as send:push.deliver_once();send.assert_not_called()
    def test_push_provider_acceptance_not_delivery_and_expiry(self):
        push.register(self.reader,{'kind':'web','subscription':self.subscription()});push.configure(self.reader,{'enabled':True});push.emit('reader','social','new','Rally','new','/?view=notifications');push.enqueue()
        with patch('push_delivery.send',return_value=201):push.deliver_once()
        self.assertEqual(s.one('SELECT state FROM push_queue')['state'],'accepted')
        push.emit('reader','social','other','Rally','new','/?view=notifications');push.enqueue()
        with patch('push_delivery.send',return_value=410):push.deliver_once()
        self.assertEqual(s.one('SELECT enabled FROM push_devices')['enabled'],0)
    def test_web_push_encryption_and_vapid_without_network(self):
        import requests
        push.config();payload={'id':'notice','url':'/?view=notifications','title':'Rally','body':'New activity in Rally'}
        response=requests.Response();response.status_code=201;response._content=b''
        with patch.dict('os.environ',{'RALLY_PUSH_DISABLED':'0'}),patch('requests.Session.send',return_value=response)as send:
            status=push.send({'kind':'web','payload':s.dump(self.subscription())},payload)
        self.assertEqual(status,201);request=send.call_args.args[0];self.assertEqual(request.headers['Content-Encoding'],'aes128gcm');self.assertTrue(request.headers['Authorization'].startswith('vapid '));self.assertNotIn(b'New activity',request.body);self.assertFalse(send.call_args.kwargs['allow_redirects'])
    def test_price_alert_requires_watch_and_no_repeats(self):
        with self.assertRaises(s.Problem):loop.alerts(self.reader,{'asset':TOKEN,'enabled':True})
        s.write('INSERT INTO watches VALUES(?,?)',('reader',TOKEN));loop.alerts(self.reader,{'asset':TOKEN,'enabled':True});self.clock+=301;s.GATEWAY.prices[TOKEN].update(price='1.1',fetchedAt=self.clock);loop.tick_markets();loop.tick_markets();self.assertEqual(s.one("SELECT count(*) n FROM notifications WHERE kind='price'")['n'],1)
        n=s.one("SELECT * FROM notifications WHERE kind='price'");s.write('DELETE FROM watches');self.assertFalse(push.eligible(n))
    def test_unchanged_watches_do_not_starve_later_accounts(self):
        ref=loop.reference(TOKEN);s.GATEWAY.prices[s.USDC]={'price':'1.1','fetchedAt':self.clock,'source':'QA reference'}
        with s.connection()as db:
            for i in range(101):
                owner='watch-'+str(i).zfill(4);asset=TOKEN if i<100 else s.USDC
                db.execute('INSERT INTO watches VALUES(?,?)',(owner,asset));db.execute('INSERT INTO market_alerts(owner,asset,enabled,threshold,anchor,last_at) VALUES(?,?,1,500,?,?)',(owner,asset,s.dump(ref),self.clock-301))
        with patch('service.rpc',side_effect=AssertionError('No provider')):loop.tick_markets();self.assertIsNone(s.one("SELECT 1 FROM notifications WHERE kind='price'"));loop.tick_markets()
        self.assertEqual(s.one("SELECT owner FROM notifications WHERE kind='price'")['owner'],'watch-0100')
    def test_migration_needs_observed_curve_then_finalized_dex(self):
        s.write('INSERT INTO watches VALUES(?,?)',('reader',TOKEN));loop.alerts(self.reader,{'asset':TOKEN,'enabled':True})
        # A provider's graduated label alone must never emit a migration.
        s.write('INSERT INTO nad_tokens VALUES(?,?,?,?)',(TOKEN,'v2',s.dump({'version':'v2','symbol':'TEST','graduated':True}),self.clock))
        with patch('service.rpc',return_value={'number':'0x64','hash':BLOCK})as rpc,patch('nadfun.state',side_effect=[{'phase':'curve','block':100},{'phase':'dex','block':100}])as state:
            loop.tick_markets();self.assertIsNone(s.one("SELECT 1 FROM notifications WHERE kind='migration'"));loop.tick_markets();loop.tick_markets()
        self.assertEqual(state.call_count,2);self.assertEqual(state.call_args.args,('v2',TOKEN,'0x64'));self.assertEqual(rpc.call_args.args,('eth_getBlockByNumber',['finalized',False]));self.assertEqual(s.one("SELECT count(*) n FROM notifications WHERE kind='migration'")['n'],1)
    def test_block_or_entitlement_loss_cancels_alert(self):
        f=self.feed();s.write('INSERT INTO entitlements VALUES(?,?,?,?)',('reader',f['id'],1,self.clock+100));discovery.alerts(self.reader,{'feed':f['id'],'enabled':True});p=s.publish(self.creator,{'text':'update'},'notice');discovery.alerts_tick();n=s.one("SELECT * FROM notifications WHERE kind='algorithm'");self.assertTrue(push.eligible(n));self.clock+=101;self.assertFalse(push.eligible(n))
    def test_league_same_frozen_candidates_and_no_backfill(self):
        f=self.feed();s.write('INSERT OR REPLACE INTO algorithms VALUES(?,?,?,?)',('algo','creator','Test',self.clock));s.write('INSERT OR REPLACE INTO algorithm_versions VALUES(?,?,?,?,?)',('version','algo',1,'recency',self.clock));s.write("UPDATE feeds SET algorithm_version='version'")
        self.signal();self.clock=(self.clock//3600+1)*3600;s.GATEWAY.prices[TOKEN]['fetchedAt']=self.clock
        league.enroll(self.creator,{'feed':f['id']});league.capture();league.run_pending();r=s.one('SELECT * FROM league_rounds');self.assertIsNotNone(r);self.assertEqual(s.one('SELECT state FROM league_runs')['state'],'scored')
        digest=r['digest'];s.write("UPDATE posts SET text='changed' WHERE author='creator'");league.capture();self.assertEqual(s.one('SELECT digest FROM league_rounds')['digest'],digest)
        self.clock+=86400;s.GATEWAY.prices[TOKEN].update(price='1.5',fetchedAt=self.clock);league.mark();self.assertEqual(s.one('SELECT state FROM league_marks')['state'],'measured');entry=league.listing()['entries'][0];self.assertEqual(entry['priceChangePercent'],50);self.assertIsNone(entry['rank']);self.assertIsNone(entry['performance']['roi'])
    def test_week_boundary_is_monday_utc(self):
        from datetime import datetime,timezone
        stamp=int(datetime(2026,10,11,23,59,tzinfo=timezone.utc).timestamp());self.assertEqual(league.period(stamp)[0],'2026-10-05');self.assertEqual(league.period(stamp+60)[0],'2026-10-12')

if __name__=='__main__':unittest.main(verbosity=2)
