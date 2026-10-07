"""Isolated discovery/access/performance tests; no live funds or providers."""
import os,sys,json,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING') == '1', 'Use scripts/test.py for isolated tests'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,discovery as d,settlement as p,journey,algorithms
W='0x'+'11'*20;T='0x'+'22'*20;R='0x'+'33'*20;BH='0x'+'44'*32
def who(user='buyer',grant=None):return {'user':user,'actor':user,'grant':grant,'scopes':s.SCOPES}
def transfer(token,a,b,value):return {'address':token,'topics':[d.TRANSFER,'0x'+a[2:].rjust(64,'0'),'0x'+b[2:].rjust(64,'0')],'data':hex(value)}
def trade(i,buy,quantity,stable,**extra):
    tx='0x'+format(i,'064x')
    logs=[transfer(T,R,W,quantity),transfer(s.USDC,W,R,stable)] if buy else [transfer(T,W,R,quantity),transfer(s.USDC,R,W,stable)]
    return {'id':str(i),'tx':tx,'state':'finalized','created':i,'wallet':W,'inputAddress':s.USDC if buy else T,'outputAddress':T if buy else s.USDC,'receipt':{'status':'0x1','transactionHash':tx,'blockHash':BH,'blockNumber':hex(i),'transactionIndex':'0x0','logs':logs},**extra}

class Returns(unittest.TestCase):
    def test_receipt_profit_and_proofs(self):
        out=d.realized([trade(1,True,100,1000000),trade(2,False,100,1500000)],s.USDC)
        self.assertEqual(out['roi'],50);self.assertEqual(out['pnl'],'0.5');self.assertEqual(out['closedTrades'],1);self.assertEqual(len(out['proofs']),2)
    def test_loss_and_partial_inventory_fifo(self):
        out=d.realized([trade(1,True,100,1000000),trade(2,False,50,400000)],s.USDC)
        self.assertEqual(out['roi'],-20);self.assertEqual(out['pnl'],'-0.1')
    def test_two_lots_and_remaining_basis(self):
        out=d.realized([trade(1,True,100,1000000),trade(2,True,100,2000000),trade(3,False,150,2400000),trade(4,False,50,1100000)],s.USDC)
        self.assertAlmostEqual(out['roi'],50/3);self.assertEqual(out['closedTrades'],2)
    def test_native_or_unknown_inventory_never_counted(self):
        for rows in [[trade(1,False,100,1500000)],[trade(1,True,100,1000000),trade(2,False,101,1500000)],[trade(1,True,100,1000000,inputAddress=s.ZERO)]]:
            self.assertIsNone(d.realized(rows,s.USDC)['roi'])
    def test_open_pending_failed_removed_or_hash_mismatch_excluded(self):
        for change in ['pending','failed','removed','hash']:
            buy=trade(1,True,100,1000000);sell=trade(2,False,100,2000000)
            if change=='pending':sell['state']='submitted'
            if change=='failed':sell['receipt']['status']='0x0'
            if change=='removed':sell['receipt']['logs'][0]['removed']=True
            if change=='hash':sell['receipt']['transactionHash']='0x'+'ff'*32
            self.assertIsNone(d.realized([buy,sell],s.USDC)['roi'])
    def test_duplicate_receipts_cannot_inflate_profit(self):
        sale=trade(2,False,100,1500000)
        self.assertEqual(d.realized([trade(1,True,200,2000000),sale,sale],s.USDC)['closedTrades'],1)
    def test_window_keeps_older_buy_basis(self):
        rows=[trade(1,True,100,1000000),trade(5,False,50,500000),trade(10,False,50,750000)]
        out=d.realized(rows,s.USDC,8);self.assertEqual(out['roi'],50);self.assertEqual(out['closedTrades'],1)
    def test_big_integer_precision_and_malformed_log(self):
        buy=trade(1,True,10**35,1);buy['receipt']['logs'].append({'topics':[None]})
        out=d.realized([buy,trade(2,False,10**35,2)],s.USDC);self.assertEqual(out['roi'],100)
    def test_chain_order_overrides_submission_order(self):
        buy=trade(1,True,100,1000000,created=5);sell=trade(2,False,100,1500000,created=3)
        self.assertEqual(d.realized([sell,buy],s.USDC)['roi'],50)

class Access(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rpc=patch.object(s,'rpc',side_effect=AssertionError('External RPC forbidden'));cls.rpc.start()
        cls.http=patch.object(s,'http_json',side_effect=AssertionError('External HTTP forbidden'));cls.http.start()
        s.initialize();d.initialize()
    @classmethod
    def tearDownClass(cls):cls.rpc.stop();cls.http.stop()
    def setUp(self):
        with s.connection() as db:
            db.execute('PRAGMA foreign_keys=OFF')  # Isolated fixture reset only.
            for table in ['posts','feeds','accounts','entitlements','feed_alerts','feed_performance_sharing','notifications','blocks','algorithm_versions','algorithms','orders','quotes','activity_context']:db.execute('DELETE FROM '+table)
            for ident,kind,owner in [('creator','person',None),('buyer','person',None),('agent','agent','creator')]:
                db.execute('INSERT INTO accounts(id,handle,name,kind,owner,avatar,wallet,created) VALUES(?,?,?,?,?,?,?,?)',(ident,ident,ident,kind,owner,'/assets/favicon.svg',W if ident=='creator' else None,s.now()-100))
            db.execute('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient) VALUES(?,?,?,?,?,?,?,?,?)',('paid','creator','Token signals','[100,0,0]','[]',s.now()-90,'2000000',1,R))
            for i in range(22):db.execute('INSERT INTO posts(id,author,text,created,deleted) VALUES(?,?,?,?,0)',('p'+str(i),'creator','Launch observation '+str(i),s.now()-80+i))
    def access(self):s.write('INSERT INTO entitlements VALUES(?,?,?,?)',('buyer','paid',1,s.now()+300))
    def test_locked_preview_is_one_and_latest_cannot_bypass(self):
        with patch.object(algorithms,'rank',return_value=None):out=journey.preview(who(),{'id':'paid'})
        self.assertEqual(out['previewLimit'],1);self.assertEqual(len(out['posts']),1);self.assertEqual([x['id'] for x in out['posts']],[x['id'] for x in out['latest']])
        self.assertFalse(out['feed']['access']);self.assertIsNone(out['feed']['weights'])
    def test_subscriber_preview_and_expiry(self):
        self.access()
        with patch.object(algorithms,'rank',return_value=None):self.assertEqual(len(journey.preview(who(),{'id':'paid'})['posts']),6)
        s.write('UPDATE entitlements SET expires=?',(s.now()-1,))
        with patch.object(algorithms,'rank',return_value=None):self.assertEqual(len(journey.preview(who(),{'id':'paid'})['posts']),1)
    def test_formula_hidden_from_both_catalogs(self):
        s.write('INSERT INTO algorithms VALUES(?,?,?,?)',('a','creator','Token signals',s.now()))
        s.write('INSERT INTO algorithm_versions VALUES(?,?,?,?,?)',('v','a',1,'recency',s.now()))
        s.write('UPDATE feeds SET algorithm_version=?',('v',))
        self.assertIsNone(p.view(s.one('SELECT * FROM feeds'),None)['formula'])
        self.assertIsNone(algorithms.listing()['algorithms'][0]['expression'])
        self.access();self.assertEqual(p.view(s.one('SELECT * FROM feeds'),'buyer')['formula'],'recency')
    def test_alert_requires_entitlement_and_human_connection(self):
        for actor in [None,who(),who(grant='scoped-agent')]:
            with self.assertRaises(s.Problem):d.alerts(actor,{'feed':'paid','enabled':True})
        self.access();self.assertTrue(d.alerts(who(),{'feed':'paid','enabled':True})['enabled'])
    def test_alert_disable_still_works_after_expiry(self):
        self.access();d.alerts(who(),{'feed':'paid','enabled':True});s.write('UPDATE entitlements SET expires=0')
        self.assertFalse(d.alerts(who(),{'feed':'paid','enabled':False})['enabled'])
    def test_alert_once_and_expiry_version_block_gates(self):
        self.access();d.alerts(who(),{'feed':'paid','enabled':True})
        s.write('INSERT INTO posts(id,author,text,created) VALUES(?,?,?,?)',('fresh','creator','New observation',s.now()+1))
        d.alerts_tick();d.alerts_tick();self.assertEqual(s.one('SELECT count(*) n FROM notifications')['n'],1)
        for gate in ['expiry','version','block']:
            s.write('DELETE FROM notifications');s.write('UPDATE feed_alerts SET after_created=0,after_post_row=0')
            if gate=='expiry':s.write('UPDATE entitlements SET expires=0')
            if gate=='version':s.write('UPDATE entitlements SET expires=?',(s.now()+300,));s.write('UPDATE feeds SET version=2')
            if gate=='block':s.write('UPDATE feeds SET version=1');s.write('INSERT INTO blocks VALUES(?,?,?)',('buyer','creator',s.now()))
            d.alerts_tick();self.assertEqual(s.one('SELECT count(*) n FROM notifications')['n'],0)
    def test_agent_creator_alert_and_same_second_posts(self):
        self.access();d.alerts(who(),{'feed':'paid','enabled':True})
        stamp=s.now()
        for ident in ['agent-one','agent-two']:
            s.write('INSERT INTO posts(id,author,text,created) VALUES(?,?,?,?)',(ident,'agent','QA agent update',stamp))
            d.alerts_tick()
        self.assertEqual(s.one('SELECT count(*) n FROM notifications')['n'],2)
    def test_repeated_creator_rows_are_one_leaderboard_entry(self):
        s.write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version) VALUES(?,?,?,?,?,?,?,?)',('second','creator','Second feed','[100,0,0]','[]',s.now(),'0',1))
        out=d.leaderboard(None,{})['unranked'];self.assertEqual(len(out),1);self.assertEqual(len(out[0]['algorithms']),2)
    def test_nine_card_cursor_stable_no_duplicates_search(self):
        out=d.catalog(None,{});self.assertEqual(len(out['items']),9)
        cursor=out['cursor'];old={x['id'] for x in out['items']}
        s.write('INSERT INTO posts(id,author,text,created) VALUES(?,?,?,?)',('new','creator','New post',s.now()+1))
        nxt=d.catalog(None,{'cursor':cursor});self.assertEqual(len(nxt['items']),9);self.assertFalse(old & {x['id'] for x in nxt['items']});self.assertNotIn('post:new',{x['id'] for x in nxt['items']})
        filtered=d.catalog(None,{'q':'observation 21'});self.assertEqual(filtered['total'],1)
        self.assertEqual(d.catalog(None,{'scope':'photos'})['total'],0)
    def test_catalog_enriches_only_visible_cards(self):
        with patch.object(s,'profile',wraps=s.profile) as profile:d.catalog(None,{})
        self.assertEqual(profile.call_count,1)
    def test_blocks_hide_catalog_preview_and_rankings(self):
        s.write('INSERT INTO blocks VALUES(?,?,?)',('buyer','creator',s.now()))
        self.assertEqual(d.catalog(who(),{})['total'],0)
        with self.assertRaises(s.Problem):d.preview(who(),'feed:paid')
        self.assertEqual(d.leaderboard(who(),{})['unranked'],[])
    def test_unknown_returns_are_unranked_people_filter(self):
        self.assertEqual(d.leaderboard(None,{})['entries'],[])
        self.assertEqual(len(d.leaderboard(None,{'kind':'human'})['unranked']),1)
        self.assertEqual(d.leaderboard(None,{'kind':'agent'})['unranked'],[])
    def test_scope_and_cursor_validation(self):
        for params in [{'scope':'unknown'},{'cursor':'invalid'},{'cursor':'-1:1'}]:
            with self.assertRaises(s.Problem):d.catalog(None,params)
        with self.assertRaises(s.Problem):d.catalog({'user':'buyer','grant':'x','scopes':set()}, {})
    def test_only_creator_can_publish_returns(self):
        for actor in [None,who(),who('creator','agent-grant')]:
            with self.assertRaises(s.Problem):d.share_performance(actor,{'feed':'paid','enabled':True})
        self.assertTrue(d.share_performance(who('creator'),{'feed':'paid','enabled':True})['enabled'])
        self.assertFalse(d.share_performance(who('creator'),{'feed':'paid','enabled':False})['enabled'])
    def test_private_history_not_queried_for_public_return(self):
        feed=s.one('SELECT * FROM feeds')
        with patch.object(s,'rows',wraps=s.rows) as rows:
            self.assertIsNone(d.performance(feed)['roi'])
        self.assertFalse(any('FROM orders' in call.args[0] for call in rows.call_args_list))
    def test_public_rank_uses_receipts_only_and_exact_feed_attribution(self):
        for i,buy,stable in [(1,True,1000000),(2,False,1500000)]:
            row=trade(i,buy,100,stable)
            s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',('q'+str(i),'creator',W,row['inputAddress'],row['outputAddress'],'1','{"receive":"99999999"}',s.now()+30))
            s.write('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',(row['id'],'creator','q'+str(i),row['tx'],'finalized',json.dumps(row['receipt']),s.now()-10+i))
            s.write('INSERT INTO activity_context VALUES(?,?,?,?,?,?)',('spot','q'+str(i),'creator',None,'paid',s.now()))
        feed=s.one('SELECT * FROM feeds')
        self.assertIsNone(d.performance(feed)['roi'])
        d.share_performance(who('creator'),{'feed':'paid','enabled':True})
        ranked=d.leaderboard(None,{})['entries'];self.assertEqual(ranked[0]['performance']['roi'],50);self.assertEqual(ranked[0]['rank'],1)
        s.write('UPDATE activity_context SET feed=? WHERE reference=?',('other-feed','q2'))
        self.assertIsNone(d.performance(feed)['roi'])

if __name__=='__main__':unittest.main()
