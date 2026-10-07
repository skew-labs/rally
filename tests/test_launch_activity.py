"""Isolated receipt/visibility tests. Fixtures are not mainnet executions."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eth_abi import encode
import launch_activity as a
import service as s

TOKEN='0x'+'11'*20; VAULT='0x'+'22'*20; WALLET='0x'+'33'*20
BUYER='0x'+'44'*20; TX='0x'+'55'*32; TX2='0x'+'66'*32
def topic(address):return '0x'+'00'*12+address[2:]
def transfer(asset,source,target,value):
    return {'address':asset,'topics':[a.TRANSFER,topic(source),topic(target)],'data':hex(value),'logIndex':'0x2'}
def receipt(tx=TX,logs=None):
    return {'status':'0x1','transactionHash':tx,'blockHash':'0x'+'77'*32,'logs':logs or []}

class LaunchActivity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'isolated.sqlite3'
        self.patchers=[patch.object(s,'DB',self.db),patch.object(s,'now',lambda:2000000000),
            patch.object(s,'rpc',side_effect=AssertionError('No RPC on public reads')),
            patch.object(s,'http_json',side_effect=AssertionError('No provider on public reads')),
            patch.object(s.GATEWAY,'token_map',{})]
        for p in self.patchers:p.start()
        with s.connection() as db:
            db.executescript('''
            CREATE TABLE accounts(id TEXT,handle TEXT,name TEXT,kind TEXT,owner TEXT,avatar TEXT);
            CREATE TABLE blocks(owner TEXT,target TEXT,created INTEGER);
            CREATE TABLE launch_tokens(token TEXT,owner TEXT,wallet TEXT,identity TEXT,community TEXT,allocations TEXT,creation_tx TEXT,block INTEGER,created INTEGER,beneficiary TEXT);
            CREATE TABLE nad_tokens(address TEXT,info TEXT);
            CREATE TABLE creator_tokens(owner TEXT,wallet TEXT,draft TEXT,state TEXT,token TEXT,vault TEXT,pair TEXT,community TEXT,stats TEXT,verified INTEGER);
            CREATE TABLE nad_revenue_vaults(token TEXT,owner TEXT,wallet TEXT,vault TEXT,stats TEXT,verified INTEGER);
            CREATE TABLE invoices(id TEXT,feed TEXT,buyer TEXT,wallet TEXT,amount_raw TEXT,tx TEXT,settled INTEGER,community_terms TEXT,receipt TEXT,state TEXT);
            CREATE TABLE execution_records(id TEXT,plan TEXT,tx TEXT,state TEXT,outcome TEXT,created INTEGER);
            CREATE TABLE execution_plans(id TEXT,venue TEXT,kind TEXT,payload TEXT);
            ''')
        s.write('INSERT INTO accounts VALUES(?,?,?,?,?,?)',('creator','public_creator','Creator','person',None,''))
        s.write('INSERT INTO accounts VALUES(?,?,?,?,?,?)',('viewer','viewer','Viewer','person',None,''))
        s.write('INSERT INTO accounts VALUES(?,?,?,?,?,?)',('agent','public_agent','Agent','agent','creator',''))
        s.write('INSERT INTO creator_tokens VALUES(?,?,?,?,?,?,?,?,?,?)',('creator',WALLET,s.dump({'name':'Fixture','symbol':'FIX','buybackBps':8000,'burnBps':10000}),'live',TOKEN,VAULT,None,'community',s.dump({'grossRevenue':'900000000','creatorPaid':'180000000','pendingBuyback':'700000000','quoteSpent':'20000000','tokensBought':'123','tokensBurned':'123'}),s.now()-200))

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.tmp.cleanup()

    def invoice(self,**changes):
        terms={'communityToken':TOKEN,'vault':VAULT,'creator':WALLET,'buybackBps':8000,'policyNonce':3}
        log={'address':VAULT,'topics':[a.ct.REVENUE_TOPIC,'0x'+a.ct.word('private_invoice').hex(),'0x'+a.ct.word('private_feed').hex(),topic(BUYER)],'data':'0x'+encode(['uint256','uint256','uint256','uint64'],[1000000,200000,800000,3]).hex(),'logIndex':'0x1'}
        row=dict(id='private_invoice',feed='private_feed',buyer='private_buyer',wallet=BUYER,amount_raw='1000000',tx=TX,settled=s.now()-100,community_terms=s.dump(terms),receipt=s.dump(receipt(logs=[log,transfer(s.USDC,BUYER,VAULT,1000000),transfer(s.USDC,VAULT,WALLET,200000)])),state='paid')
        row.update(changes)
        s.write('INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(row[k] for k in ('id','feed','buyer','wallet','amount_raw','tx','settled','community_terms','receipt','state')))
        return row

    def execution(self,state='finalized',kind='creator_claim',asset='MON',business='fees_claimed',**changes):
        payload={'summary':{'token':TOKEN},'transaction':{'from':WALLET,'to':VAULT}}
        outcome={'businessState':business,'recipient':WALLET,'deliveryAsset':asset,'quotedRaw':'1000000000000000000','nativeDeliveredRaw':'1000000000000000000','deliveredRaw':'1000000000000000000','receipt':receipt(TX2)}
        outcome.update(changes)
        s.write('INSERT INTO execution_plans VALUES(?,?,?,?)',('plan','nadfees',kind,s.dump(payload)))
        s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?)',('record','plan',TX2,state,s.dump(outcome),s.now()-200))

    def total(self,d,asset='USDC'):return next(g for g in d['totals'] if g['asset']==asset)
    def test_empty_ledger_and_alltime_snapshot_are_separate(self):
        d=a.overview();self.assertEqual(d['count'],0);self.assertEqual(self.total(d)['creatorPayoutRaw'],'0')
        self.assertEqual(d['tokens'][0]['stats']['creatorPaid'],'180000000');self.assertTrue(d['tokens'][0]['stale'])
    def test_public_payout_requires_exact_event_and_delivery(self):
        self.invoice();d=a.overview();self.assertEqual(d['count'],1)
        self.assertEqual(self.total(d)['salesRaw'],'1000000');self.assertEqual(self.total(d)['creatorPayoutRaw'],'200000');self.assertEqual(self.total(d)['reservedRaw'],'800000')
    def test_private_identity_and_subscription_metadata_are_not_exposed(self):
        self.invoice();body=s.dump(a.overview())
        for value in ['private_buyer','private_invoice','private_feed',BUYER]:self.assertNotIn(value,body)
    def test_pending_confirmed_failed_invalid_never_count(self):
        for state in ['submitted','confirmed','failed','invalid']:
            with self.subTest(state=state):
                s.write('DELETE FROM invoices');self.invoice(state=state);self.assertEqual(a.overview()['count'],0)
    def test_mismatched_transaction_is_not_a_proof(self):
        self.invoice(receipt=s.dump(receipt(TX2)));self.assertEqual(a.overview()['count'],0)
    def test_wrong_creator_delivery_is_excluded(self):
        row=self.invoice();r=json.loads(row['receipt']);r['logs'][-1]=transfer(s.USDC,VAULT,BUYER,200000)
        s.write('UPDATE invoices SET receipt=?',(s.dump(r),));self.assertEqual(a.overview()['count'],0)
    def test_captured_invoice_split_not_current_policy(self):
        self.invoice();s.write('UPDATE creator_tokens SET stats=?',(s.dump({'buybackBps':1000}),))
        self.assertEqual(self.total(a.overview())['reservedRaw'],'800000')
    def test_removed_and_malformed_events_fail_closed(self):
        row=self.invoice();r=json.loads(row['receipt'])
        for alteration in [{'removed':True},{'data':'0x01'}]:
            with self.subTest(alteration=alteration):
                changed=copy.deepcopy(r);changed['logs'][0].update(alteration);s.write('UPDATE invoices SET receipt=?',(s.dump(changed),));self.assertEqual(a.overview()['count'],0)
    def test_unbound_vault_is_not_public(self):
        row=self.invoice();t=json.loads(row['community_terms']);t['vault']=BUYER;s.write('UPDATE invoices SET community_terms=?',(s.dump(t),));self.assertEqual(a.overview()['count'],0)
    def test_blocked_creator_removes_token_receipts_and_totals(self):
        self.invoice();s.write('INSERT INTO blocks VALUES(?,?,?)',('viewer','creator',s.now()))
        d=a.overview({'user':'viewer'});self.assertEqual(d['tokens'],[]);self.assertEqual(d['count'],0)
    def test_reverse_block_also_hides_records(self):
        s.write('INSERT INTO blocks VALUES(?,?,?)',('creator','viewer',s.now()));self.assertEqual(a.overview({'user':'viewer'})['tokens'],[])
    def test_invalid_filters_and_hidden_token(self):
        for kw in [{'period':'year'},{'token':'not-an-address'},{'limit':'201'},{'limit':'0'},{'limit':'1.0'},{'token':BUYER}]:
            with self.subTest(kw=kw),self.assertRaises(s.Problem):a.overview(**kw)
    def test_asset_totals_never_mix_usdc_and_native_claims(self):
        self.invoice();self.execution();d=a.overview();self.assertEqual(d['count'],2)
        self.assertEqual(self.total(d)['feesClaimedRaw'],'0');self.assertEqual(self.total(d,'MON')['feesClaimedRaw'],'1000000000000000000')
    def test_unverified_delivery_not_counted(self):
        self.execution(business='claim_delivery_verification_pending');self.assertEqual(a.overview()['count'],0)
    def test_claim_recipient_and_amount_must_match(self):
        for alteration in [{'recipient':BUYER},{'nativeDeliveredRaw':'1'},{'deliveryAsset':'UNKNOWN'}]:
            with self.subTest(alteration=alteration):
                s.write('DELETE FROM execution_records');s.write('DELETE FROM execution_plans');self.execution(**alteration);self.assertEqual(a.overview()['count'],0)
    def test_claim_must_be_finalized(self):
        self.execution(state='confirmed');self.assertEqual(a.overview()['count'],0)
    def test_period_filters_receipts_not_vault_balances(self):
        self.invoice(settled=s.now()-2*86400);d=a.overview(period='24h');self.assertEqual(d['count'],0)
        self.assertEqual(d['tokens'][0]['stats']['creatorPaid'],'180000000');self.assertEqual(a.overview(period='7d')['count'],1)
    def test_series_reconciles_to_totals(self):
        self.invoice();self.execution();d=a.overview(period='24h')
        for asset in ['USDC','MON']:
            for field in a.FIELDS:self.assertEqual(sum(int(b[asset][field]) for b in d['series']),int(self.total(d,asset)[field]))
    def test_no_provider_reads_or_database_mutations(self):
        self.invoice();before=self.db.read_bytes();a.overview();self.assertEqual(before,self.db.read_bytes());s.rpc.assert_not_called();s.http_json.assert_not_called()
    def test_receipt_limit_does_not_reduce_aggregate(self):
        self.invoice();self.execution();d=a.overview(limit='1');self.assertEqual(len(d['activity']),1);self.assertTrue(d['hasMore']);self.assertEqual(d['count'],2)
    def test_agent_identity_and_missing_snapshot(self):
        other='0x'+'88'*20;s.write('INSERT INTO launch_tokens VALUES(?,?,?,?,?,?,?,?,?,?)',(other,'creator',WALLET,'agent','agent_community','{}',TX,12,s.now(),'{}'))
        s.write('INSERT INTO nad_tokens VALUES(?,?)',(other,s.dump({'name':'Agent Token','symbol':'AGT'})))
        d=a.overview(token=other);self.assertEqual(d['tokens'][0]['creator']['operator']['id'],'creator');self.assertIsNone(d['tokens'][0]['stats'])
    def test_dead_address_buyback_is_not_supply_burn(self):
        payload={'summary':{'token':TOKEN},'transaction':{'from':WALLET,'to':VAULT}}
        outcome={'businessState':'buyback_executed','receipt':receipt(TX2),'delivery':{'token':TOKEN,'quoteSpentRaw':'10000','tokensBoughtRaw':'1000000000000000000','tokensSunkRaw':'800000000000000000','creatorTokensRaw':'200000000000000000'}}
        s.write('INSERT INTO execution_plans VALUES(?,?,?,?)',('plan','nadrevenue','revenue_execute',s.dump(payload)))
        s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?)',('record','plan',TX2,'finalized',s.dump(outcome),s.now()))
        d=a.overview();self.assertEqual(d['activity'][0]['burnMethod'],'dead_address');self.assertEqual(self.total(d)['buybackSpentRaw'],'10000')
        outcome['delivery']['creatorTokensRaw']='1';s.write('UPDATE execution_records SET outcome=?',(s.dump(outcome),));self.assertEqual(a.overview()['count'],0)

if __name__=='__main__':unittest.main()
