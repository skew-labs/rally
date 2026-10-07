"""Persistent launch ingestion and paging boundaries. Synthetic reads only."""
import copy,json,os,sys,unittest
from urllib.error import HTTPError
from email.message import Message
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,nadfun as n,launch_ingestion as i,market_universe as u
from eth_abi import encode
from eth_utils import keccak

A='0x'+'11'*20;B='0x'+'22'*20;P='0x'+'33'*20;OWNER='0x'+'44'*20
def candidate(a=A,version='v2',name='Example',created=None):
    return {'token_info':{'token_id':a,'version':version,'name':name,'symbol':'EX','created_at':created or s.now()-100,'creator':{'account_id':OWNER},'image_uri':'https://storage.nadapp.net/coin/12345678-test'},'market_info':{'token_id':a,'price_usd':'0.001','total_supply':str(10**27)}}
def identity(a=A,created=None,**extra):
    return {'id':a,'address':a,'name':'Example','symbol':'EX','decimals':18,'chainId':143,'version':'v2','created':created or s.now()-100,'price':'0.001','totalSupply':'1000000000','marketCap':'1000000','referenceAt':s.now(),'graduated':False,'phase':'curve',**extra}
def put(info):s.write('INSERT OR REPLACE INTO nad_tokens VALUES(?,?,?,?)',(info['id'],info['version'],s.dump(info),s.now()-200))

class Launches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):n.initialize()
    def setUp(self):
        with s.connection() as db:
            for table in ['nad_tokens','launch_sources','launch_candidates']:db.execute('DELETE FROM '+table)
        n.MARKET_REFERENCES.clear();i.VISIBLE.clear();i.URGENT.clear();i.VISIBLE_EVENT.clear();u.READY=False
        with u.db() as db:
            for table in ['assets','pools','sources']:db.execute('DELETE FROM '+table)
        self.rpc=patch.object(s,'rpc',side_effect=AssertionError('Network forbidden'));self.rpc.start()
    def tearDown(self):self.rpc.stop()
    def test_candidate_is_not_public_until_contract_verification(self):
        i.enqueue([candidate()]);self.assertEqual(n.catalog()['tokens'],[]);self.assertEqual(i.health()['queued'],1)
    def test_duplicate_queue_address_and_latest_priority(self):
        i.enqueue([candidate()],0);i.enqueue([candidate()],2);row=s.one('SELECT * FROM launch_candidates')
        self.assertEqual(i.health()['queued'],1);self.assertEqual(row['priority'],2)
    def test_fresh_lifecycle_does_not_prevent_metadata_repair(self):
        put(identity(logoURI=None));s.write('UPDATE nad_tokens SET observed=?',(s.now(),))
        i.enqueue([candidate()],2);self.assertEqual(i.health()['queued'],1)
    def test_latest_precedes_history_queue(self):
        i.enqueue([candidate(A)],0);i.enqueue([candidate(B)],2)
        with patch.object(s,'rpc',return_value='0x10'),patch.object(i,'many_state',return_value={}) as verify:i.verify_once(1)
        self.assertEqual(verify.call_args[0][0][0]['token_info']['token_id'],B)
    def test_failure_defers_retry_and_preserves_last_good_token(self):
        put(identity());i.enqueue([candidate()],2)
        with patch.object(s,'rpc',return_value='0x10'),patch.object(i,'many_state',side_effect=ValueError('Outage')):i.verify_once()
        row=s.one('SELECT * FROM launch_candidates');self.assertGreater(row['next_attempt'],s.now());self.assertEqual(n.catalog()['tokens'][0]['price'],'0.001')
    def test_interior_short_page_cannot_advance(self):
        i.status('history',nextPage=2)
        with patch.object(n,'api',return_value={'tokens':[candidate()],'total_count':300}):self.assertFalse(i.history_once())
        self.assertEqual(i.health()['sources']['history']['nextPage'],2)
    def test_failed_page_retries_same_cursor_after_restart(self):
        i.status('history',nextPage=3)
        with patch.object(n,'api',side_effect=s.Problem('Outage',503)):i.history_once()
        i.initialize()
        with patch.object(n,'api',return_value={'tokens':[],'total_count':200}) as api:self.assertTrue(i.history_once())
        self.assertIn('page=3',api.call_args[0][0]);self.assertEqual(i.health()['sources']['history']['state'],'complete')
    def test_history_completion_is_separate_from_verified_coverage(self):
        with patch.object(n,'api',return_value={'tokens':[candidate()],'total_count':1}):i.history_once()
        h=i.health();self.assertEqual(h['sources']['history']['state'],'complete');self.assertEqual(h['queued'],1);self.assertEqual(h['verified'],0)
    def test_reference_wrong_address_or_version_does_not_publish(self):
        put(identity());c=candidate();c['market_info']['token_id']=B;i.publish_reference(c,s.now());self.assertEqual(n.MARKET_REFERENCES,{})
        c=candidate(version='v1');i.publish_reference(c,s.now());self.assertEqual(n.MARKET_REFERENCES,{})
    def test_stale_price_hidden_without_removing_identity_or_art(self):
        put(identity(referenceAt=s.now()-901,logoURI='https://storage.nadapp.net/coin/12345678-test'))
        t=n.catalog()['tokens'][0];self.assertIsNone(t['price']);self.assertIsNone(t['marketCap']);self.assertTrue(t['logoURI']);self.assertEqual(t['id'],A)
    def test_paging_past_100_and_new_insert_keeps_latest_cursor(self):
        stamp=s.now()-100
        for num in range(1,254):put(identity('0x'+format(num,'040x'),created=stamp))
        first=n.catalog(limit=100);put(identity('0x'+format(999,'040x'),created=s.now()+1))
        second=n.catalog(cursor=first['nextCursor']);third=n.catalog(cursor=second['nextCursor'])
        ids=[t['id'] for d in [first,second,third] for t in d['tokens']]
        self.assertEqual(len(ids),253);self.assertEqual(len(set(ids)),253);self.assertIsNone(third['nextCursor'])
    def test_search_is_over_full_registry(self):
        for num in range(1,152):put(identity('0x'+format(num,'040x'),name='Needle' if num==1 else 'Other',created=s.now()-200+num))
        self.assertEqual(len(n.catalog(query='needle')['tokens']),1)
    def test_cursor_cannot_change_filters_or_size(self):
        put(identity(A));put(identity(B));cursor=n.catalog(limit=1)['nextCursor']
        for kwargs in [{'cursor':cursor,'query':'changed'},{'cursor':cursor,'phase':'dex'},{'cursor':'bad'},{'limit':101},{'limit':0}]:
            with self.assertRaises(s.Problem):n.catalog(**kwargs)
    def test_cap_includes_records_beyond_old_500_limit(self):
        for num in range(1,503):put(identity('0x'+format(num,'040x'),created=s.now()-1000+num,marketCap=str(10**9 if num==1 else 10)))
        self.assertEqual(n.catalog(sort='cap')['tokens'][0]['id'],'0x'+format(1,'040x'))
    def test_cache_endpoint_never_reads_a_provider(self):
        put(identity());self.assertEqual(n.references(A)['tokens'][0]['id'],A);self.assertIn(A,i.VISIBLE)
    def test_graduation_enters_shared_spot_registry(self):
        i.store(candidate(),{'version':'v2','graduated':True,'phase':'dex','pair':P},s.now())
        with u.db() as db:self.assertEqual(json.loads(db.execute('SELECT info FROM assets WHERE address=?',(A,)).fetchone()[0])['phase'],'dex')
    def test_old_verified_job_cannot_regress_newer_reference(self):
        put(identity(price='8',marketCap='8000000000',referenceAt=s.now()))
        t=i.store(candidate(),{'version':'v2','graduated':False,'phase':'curve'},s.now()-100)
        self.assertEqual(t['price'],'8');self.assertEqual(t['referenceAt'],s.now())
    def test_old_job_cannot_delete_newer_candidate(self):
        i.enqueue([candidate()],2);i.store(candidate(),{'version':'v2','graduated':False},s.now()-1);self.assertEqual(i.health()['queued'],1)
    def test_image_provider_must_match_exact_chain_identity(self):
        s.GATEWAY.token_map[A]=identity()
        with u.db() as db:db.execute('INSERT INTO assets(address,info) VALUES(?,?)',(A,s.dump(identity())))
        pair={'chainId':'solana','baseToken':{'address':A,'name':'Example','symbol':'EX'},'info':{'imageUrl':'https://cdn.dexscreener.com/asset.png'}}
        u.enrich_artwork([pair],[A]);self.assertNotIn('logoURI',s.GATEWAY.token_map[A]);pair['chainId']='monad';pair['baseToken']['name']='Other';u.enrich_artwork([pair],[A]);self.assertNotIn('logoURI',s.GATEWAY.token_map[A])
        pair['baseToken']['name']='Example';pair['info']['imageUrl']='https://localhost/secret';u.enrich_artwork([pair],[A]);self.assertNotIn('logoURI',s.GATEWAY.token_map[A])
        pair['info']['imageUrl']='https://cdn.dexscreener.com/asset.png';u.enrich_artwork([pair],[A]);self.assertEqual(s.GATEWAY.token_map[A]['logoURI'],pair['info']['imageUrl'])
    def test_nad_api_429_stops_all_readers_during_retry_after(self):
        headers=Message();headers['Retry-After']='45'
        class Opener:
            def open(self,*a,**kw):raise HTTPError('https://api.nad.fun',429,'Limited',headers,None)
        n.API_AT=0;n.API_RETRY_AT=0
        try:
            with patch.object(n.time,'monotonic',return_value=1000),patch.object(n,'build_opener',return_value=Opener()) as opener:
                with self.assertRaises(s.Problem):n.api('/token/'+A)
                with self.assertRaises(s.Problem) as error:n.api('/token/'+B)
                self.assertEqual(error.exception.code,'nad_api_backoff');self.assertEqual(opener.call_count,1);self.assertEqual(n.API_RETRY_AT,1045)
        finally:n.API_AT=0;n.API_RETRY_AT=0
    def test_recovered_source_clears_old_failure(self):
        i.status('history',state='delayed',error='nad_api_429');value=i.status('history',state='indexing',nextPage=2);self.assertNotIn('error',value)

class ChainIdentity(unittest.TestCase):
    setUpClass=classmethod(lambda cls:n.initialize())
    setUp=Launches.setUp
    tearDown=Launches.tearDown
    def batch(self,calls,block):
        self.assertEqual(block,'0x10');output=[]
        for target,_,data in calls:
            selector=data[:4];outputs=None;value=None
            simple={'name()':('string','Example'),'symbol()':('string','EX'),'decimals()':('uint8',18),'totalSupply()':('uint256',10**27)}
            for sig,(typ,v) in simple.items():
                if selector==keccak(text=sig)[:4]:outputs=[typ];value=[v]
            if outputs is None:
                for version in n.FILES:
                    for label in n.FILES[version]:
                        for f in n.abi(version,label):
                            if f.get('type')!='function':continue
                            sig=f['name']+'('+','.join(n.v.typ(x) for x in f['inputs'])+')'
                            if selector!=keccak(text=sig)[:4]:continue
                            name=f['name'];outputs=[n.v.typ(o) for o in f['outputs']]
                            if name=='getCurve':
                                values={'token':A,'creator':OWNER,'quoteToken':n.WMON,'virtualQuoteReserve':10**21,'virtualTokenReserve':10**27,'k':10**48,'minTokenReserve':0,'initialQuoteReserve':10**21,'initialTokenReserve':10**27,'createdAtBlock':1,'graduated':False,'creatorFeeRate':100,'version':0,'dexType':0,'pair':P,'graduateFee':0}
                                value=[tuple(values[o['name']] for o in f['outputs'][0]['components'])]
                            elif name=='getPair':value=[P]
                            elif name=='getFeeConfig':value=[(A,n.WMON,100,100,100)]
                            elif name=='getSnipingPenalty':value=[0]
                            elif name=='isGraduated':value=[False]
                            else:continue
                            break
                        if value is not None:break
                    if value is not None:break
            if value is None:raise AssertionError('Unspecified fixture read')
            output.append((True,encode(outputs,value)))
        return output
    def test_same_block_batch_verifies_metadata_creator_pair_and_quote(self):
        with patch.object(u,'batch',side_effect=self.batch) as batch:
            result=i.many_state([candidate()],'0x10');self.assertIn(A,result);self.assertEqual(batch.call_count,2);self.assertEqual(result[A]['pair'],P)
    def test_creator_or_symbol_mismatch_cannot_enter_registry(self):
        with patch.object(u,'batch',side_effect=self.batch):
            c=candidate();c['token_info']['creator']['account_id']=B;self.assertEqual(i.many_state([c],'0x10'),{})
            c=candidate();c['token_info']['symbol']='Fake';self.assertEqual(i.many_state([c],'0x10'),{})
    def test_curve_price_uses_fresh_quote_observation_time(self):
        s.GATEWAY.prices[n.WMON]={'price':2,'fetchedAt':s.now()-10}
        with patch.object(u,'batch',side_effect=self.batch):result=i.many_state([candidate()],'0x10')[A]
        self.assertEqual(result['referenceAt'],s.now()-10);self.assertEqual(float(result['price']),.000002);self.assertEqual(float(result['marketCap']),2000)
        s.GATEWAY.prices[n.WMON]['fetchedAt']=s.now()-121
        with patch.object(u,'batch',side_effect=self.batch):self.assertNotIn('price',i.many_state([candidate()],'0x10')[A])

if __name__=='__main__':unittest.main()
