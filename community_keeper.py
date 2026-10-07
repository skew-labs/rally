"""Bounded gas-only keeper. Observe by default; no owner wallet or auth tokens.

Relay mode requires a separately approved signer and explicit gas caps. Unknown
broadcast outcomes block further sends until receipt reconciliation.
"""
import fcntl,json,os,time
from decimal import Decimal
from eth_account import Account
import service as s
import community_tokens as ct

def budget(name):
    try:
        value=Decimal(os.environ.get(name,''))
        if not value.is_finite() or value<=0:raise ValueError()
        return int(value*10**18)
    except Exception:raise s.Problem('Keeper gas budget is not configured',503)

def initialize():
    with s.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS community_keeper_jobs(
          id TEXT PRIMARY KEY,owner TEXT,day TEXT,transaction_json TEXT,
          gas_reserved TEXT,tx TEXT UNIQUE,state TEXT,created INTEGER)''')

def intents():
    if not ct.config(refresh=True)['enabled']:return []
    ct.pin();out=[]
    for row in s.rows("SELECT owner,vault FROM creator_tokens WHERE state='live' ORDER BY verified LIMIT 3"):
        try:
            t=ct.refresh(row['owner']);stats=t['stats']
            if stats['paused'] or int(stats['pendingBuyback'])<int(stats['minBatchRaw']):continue
            block=s.rpc('eth_getBlockByNumber',['latest',False]);now=int(block['timestamp'],16)
            # A separate checkpoint commits the observation even if a later
            # buyback cannot satisfy price protection.
            observed=ct.read(row['vault'],'observationTime',outs=['uint32'])
            action='checkpoint' if now-observed>=600 else 'executeBuyback'
            data=ct.call('checkpoint') if action=='checkpoint' else ct.call('executeBuyback',['uint256'],[now+120])
            tx={'to':row['vault'],'data':data,'value':'0x0','chainId':'0x8f'}
            s.rpc('eth_call',[tx,'latest'])
            out.append({'owner':row['owner'],'action':action,'transaction':tx,'observedAt':now})
        except s.Problem:continue
    return out

def reconcile():
    for job in s.rows("SELECT * FROM community_keeper_jobs WHERE state='broadcast_unknown'"):
        r=s.rpc('eth_getTransactionReceipt',[job['tx']])
        if not r:continue
        b=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False]);final=s.rpc('eth_getBlockByNumber',['finalized',False])
        if not b or b['hash'].lower()!=r['blockHash'].lower() or not final or int(final['number'],16)<int(r['blockNumber'],16):continue
        s.write('UPDATE community_keeper_jobs SET state=? WHERE id=?',('finalized' if int(r['status'],16)==1 else 'failed',job['id']))

def relay(items):
    if os.environ.get('RALLY_COMMUNITY_KEEPER_MODE')!='relay':return {'mode':'observe','intents':items,'submitted':0}
    if os.environ.get('RALLY_COMMUNITY_KEEPER_SEND_ENABLED')!='true':raise s.Problem('Keeper sending has not been enabled',503)
    approved=ct.addr(os.environ.get('RALLY_COMMUNITY_KEEPER_APPROVED_ADDRESS'))
    key=os.environ.get('RALLY_COMMUNITY_KEEPER_PRIVATE_KEY','')
    try:signer=Account.from_key(key)
    except Exception:raise s.Problem('Keeper signer is not configured',503)
    if signer.address.lower()!=approved:raise s.Problem('Keeper signer is not the approved account',503)
    per_tx=budget('RALLY_COMMUNITY_KEEPER_MAX_TX_MON');daily=budget('RALLY_COMMUNITY_KEEPER_MAX_DAY_MON')
    ct.pin();reconcile()
    if s.one("SELECT 1 FROM community_keeper_jobs WHERE state='broadcast_unknown'"):return {'mode':'relay','submitted':0,'state':'awaiting_receipt'}
    if not items:return {'mode':'relay','submitted':0,'state':'idle'}
    job=items[0];row=s.one("SELECT vault FROM creator_tokens WHERE owner=? AND state='live'",(job['owner'],))
    if not row or row['vault']!=job['transaction']['to']:raise s.Problem('Keeper target is not an active community',503)
    allowed=[ct.call('checkpoint')]
    if job['action']=='executeBuyback':
        now=int(s.rpc('eth_getBlockByNumber',['latest',False])['timestamp'],16)
        allowed.append(ct.call('executeBuyback',['uint256'],[job['observedAt']+120]))
        if not now<=job['observedAt']+120<=now+300:raise s.Problem('Keeper intent expired',409)
    if job['transaction']['data'] not in allowed or job['transaction']['value']!='0x0':raise s.Problem('Keeper action is not allowed',503)
    estimate={'from':approved,**{k:v for k,v in job['transaction'].items() if k!='chainId'}}
    gas=(int(s.rpc('eth_estimateGas',[estimate]),16)*125+99)//100;fee=int(s.rpc('eth_gasPrice',[]),16);reserve=gas*fee
    if reserve>per_tx:return {'mode':'relay','submitted':0,'state':'transaction_budget_exceeded'}
    day=time.strftime('%Y-%m-%d',time.gmtime());spent=sum(int(x['gas_reserved']) for x in s.rows('SELECT gas_reserved FROM community_keeper_jobs WHERE day=?',(day,)))
    if reserve+spent>daily:return {'mode':'relay','submitted':0,'state':'daily_budget_exceeded'}
    if int(s.rpc('eth_getBalance',[approved,'latest']),16)<reserve:return {'mode':'relay','submitted':0,'state':'gas_required'}
    nonce=int(s.rpc('eth_getTransactionCount',[approved,'pending']),16)
    tx={'to':s.to_checksum_address(row['vault']) if hasattr(s,'to_checksum_address') else row['vault'],'value':0,'data':job['transaction']['data'],'chainId':143,'nonce':nonce,'gas':gas,'gasPrice':fee}
    from eth_utils import to_checksum_address
    tx['to']=to_checksum_address(tx['to'])
    signed=signer.sign_transaction(tx);txhash='0x'+signed.hash.hex();ident=s.uid()
    # Reserve before broadcast. Do not retry an unknown result with a new nonce.
    s.write("INSERT INTO community_keeper_jobs VALUES(?,?,?,?,?,?,'broadcast_unknown',?)",(ident,job['owner'],day,s.dump(tx),str(reserve),txhash,s.now()))
    returned=s.rpc('eth_sendRawTransaction',['0x'+signed.raw_transaction.hex()])
    if returned.lower()!=txhash:raise s.Problem('Keeper broadcast outcome is unresolved',503)
    return {'mode':'relay','submitted':1,'tx':txhash}

def once():
    initialize()
    lock=s.STATE/'community-keeper.lock'
    with lock.open('a') as handle:
        os.chmod(lock,0o600);fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return relay(intents())

if __name__=='__main__':
    s.initialize()
    try:print(s.dump(once()))
    except Exception:print(s.dump({'ok':False,'state':'keeper_check_failed'}));raise SystemExit(1)
