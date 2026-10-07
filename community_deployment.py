"""Owner-reviewed factory deployment. Wallet signing remains in the browser."""
import json, os, re
from decimal import Decimal, InvalidOperation
from eth_abi import encode
import service as s
import community_tokens as ct

DEPLOYER=os.environ.get('RALLY_COMMUNITY_DEPLOYER','').lower()
CREATION=s.ROOT/'community-deployment.json'

def initialize():
    with s.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS community_deployments(
          id TEXT PRIMARY KEY,owner TEXT,wallet TEXT,payload TEXT,created INTEGER,
          expires INTEGER,tx TEXT UNIQUE,state TEXT,receipt TEXT,factory TEXT)''')
    active=s.one("SELECT factory FROM community_deployments WHERE state='finalized' ORDER BY created DESC LIMIT 1")
    if active and not ct.FACTORY:ct.FACTORY=ct.addr(active['factory'])

def permitted(user):
    account=s.one('SELECT wallet,kind FROM accounts WHERE id=?',(user,)) if user else None
    return bool(DEPLOYER and account and account['kind']=='person' and (account['wallet'] or '').lower()==DEPLOYER)

def wallet(who):
    user,w=ct.wallet(who)
    if not permitted(user) or w!=DEPLOYER:raise s.Problem('Use the authorized launchpad wallet',403)
    return user,w

def view(row):
    p=json.loads(row['payload'])
    return {'id':row['id'],'state':row['state'],'tx':row['tx'],'factory':row['factory'],
      'expires':row['expires'],'summary':p['summary'],
      'receipt':json.loads(row['receipt']) if row['receipt'] else None}

def status(user):
    if not permitted(user):return {'allowed':False}
    return {'allowed':True,'active':bool(ct.FACTORY),'factory':ct.FACTORY or None,
      'plans':[view(r) for r in s.rows('SELECT * FROM community_deployments WHERE owner=? ORDER BY created DESC LIMIT 3',(user,))]}

def owned(who,ident):
    user,w=wallet(who)
    row=s.one('SELECT * FROM community_deployments WHERE id=? AND owner=?',(ident,user))
    if not row or row['wallet']!=w:raise s.Problem('Deployment not found for this wallet',404)
    return row

def creation():
    a=json.loads(CREATION.read_text());runtime=json.loads(ct.ARTIFACT.read_text())
    if a['sourceHash']!=runtime['sourceHashes']['RallyCommunity.sol'] or not re.fullmatch('0x[0-9a-f]+',a['bytecode']):
        raise s.Problem('Deployment source does not match reviewed contract',503)
    return a['bytecode']+encode(['address','address'],[s.USDC,ct.ROUTER]).hex(),a['sourceHash']

def quote(w,cap):
    s.verify_rpc_network();ct.v2_routes.version('PancakeSwap v2')
    data,source=creation()
    tx,cost=ct.gas({'from':w,'data':data,'value':'0x0','chainId':'0x8f'})
    price=int(s.rpc('eth_gasPrice',[]),16)
    if int(tx['gas'],16)*price>cap:raise s.Problem('Network fee exceeds your deployment limit. Review a new limit.',409)
    if int(s.rpc('eth_getBalance',[w,'latest']),16)<int(tx['gas'],16)*price:raise s.Problem('Add MON for deployment gas',409)
    tx.update(gasPrice=hex(price),nonce=s.rpc('eth_getTransactionCount',[w,'pending']))
    return tx,{'wallet':w,'chainId':143,'contract':'RallyCommunityFactory','venue':'PancakeSwap V2',
      'quoteToken':s.USDC,'router':ct.ROUTER,'sourceHash':source,
      'estimatedGasCostMON':s.units(int(tx['gas'],16)*price,18),'maxGasCostMON':s.units(cap,18),
      'valueMON':'0','tokenLaunchIncluded':False,'keeperFundingIncluded':False}

def plan(who,data):
    user,w=wallet(who)
    if ct.FACTORY:raise s.Problem('Launchpad already activated',409)
    if s.one("SELECT 1 FROM community_deployments WHERE state IN ('submitted','confirmed')"):
        raise s.Problem('A deployment is pending. Check its existing transaction.',409)
    try:
        amount=Decimal(str(data.get('maxGasCostMON','0.5')))
        if not amount.is_finite() or not Decimal('.01')<=amount<=2 or amount*10**18!=int(amount*10**18):raise ValueError()
        cap=int(amount*10**18)
    except (ValueError,InvalidOperation,OverflowError):raise s.Problem('Set a deployment gas limit between 0.01 and 2 MON')
    tx,summary=quote(w,cap);ident=s.uid();now=s.now()
    p={'transaction':tx,'summary':summary,'maxGasWei':str(cap)}
    s.write("INSERT INTO community_deployments VALUES(?,?,?,?,?,?,NULL,'awaiting_wallet',NULL,NULL)",(ident,user,w,s.dump(p),now,now+180))
    return view(s.one('SELECT * FROM community_deployments WHERE id=?',(ident,)))

def prepare(who,data):
    row=owned(who,data.get('plan'));p=json.loads(row['payload']);tx=p['transaction']
    if ct.FACTORY or row['tx'] or row['expires']<s.now():raise s.Problem('Review a fresh deployment',409)
    if creation()[0]!=tx['data']:raise s.Problem('Deployment source changed',409)
    s.verify_rpc_network();ct.v2_routes.version('PancakeSwap v2')
    if int(s.rpc('eth_getTransactionCount',[row['wallet'],'pending']),16)!=int(tx['nonce'],16):
        raise s.Problem('Wallet nonce changed. Review a fresh deployment.',409)
    if int(s.rpc('eth_getBalance',[row['wallet'],'latest']),16)<int(tx['gas'],16)*int(tx['gasPrice'],16):
        raise s.Problem('Add MON for deployment gas',409)
    return {'transaction':tx,'summary':p['summary']}

def matches(row,t):
    p=json.loads(row['payload']);tx=p['transaction']
    if not t or (t.get('from') or '').lower()!=row['wallet'] or t.get('to') not in [None,'','0x'] or t.get('input','').lower()!=tx['data'] or int(t.get('value','0x0'),16):
        raise s.Problem('Transaction does not match reviewed deployment',409)
    if int(t.get('nonce','0x0'),16)!=int(tx['nonce'],16) or int(t.get('chainId','0x8f'),16)!=143:
        raise s.Problem('Deployment nonce or network changed',409)
    price=int(t.get('maxFeePerGas') or t.get('gasPrice') or '0x0',16)
    if price<=0 or int(t.get('gas','0x0'),16)*price>int(p['maxGasWei']):raise s.Problem('Transaction exceeds reviewed gas limit',409)

def validate(factory,block):
    a=json.loads(ct.ARTIFACT.read_text())['contracts']['RallyCommunityFactory']
    code=s.rpc('eth_getCode',[factory,block])
    if ct.normalized(code,a)!=ct.normalized(a['runtime'],a):raise s.Problem('Deployed code differs from reviewed contract',409)
    if ct.read(factory,'quoteToken',outs=['address'],block=block).lower()!=s.USDC or ct.read(factory,'router',outs=['address'],block=block).lower()!=ct.ROUTER:
        raise s.Problem('Deployed factory configuration differs',409)

def record(who,data):
    row=owned(who,data.get('plan'));tx=str(data.get('tx') or '').lower()
    if not re.fullmatch('0x[0-9a-f]{64}',tx):raise s.Problem('Invalid transaction hash')
    if row['tx'] and row['tx']!=tx:raise s.Problem('Check the existing deployment hash',409)
    if not row['tx']:
        t=s.rpc('eth_getTransactionByHash',[tx])
        if not t:raise s.Problem('Transaction is not indexed. Check the same hash again.',409,'transaction_pending')
        matches(row,t)
        try:
            with s.connection() as db:
                db.execute("UPDATE community_deployments SET tx=?,state='submitted' WHERE id=? AND tx IS NULL",(tx,row['id']))
                if db.execute('SELECT tx FROM community_deployments WHERE id=?',(row['id'],)).fetchone()['tx']!=tx:raise s.Problem('Another transaction was recorded',409)
        except s.sqlite3.IntegrityError:raise s.Problem('This deployment hash is already recorded',409)
    reconcile(row['id']);return view(s.one('SELECT * FROM community_deployments WHERE id=?',(row['id'],)))

def reconcile(ident):
    row=s.one('SELECT * FROM community_deployments WHERE id=?',(ident,))
    if not row or not row['tx'] or row['state'] not in {'submitted','confirmed'}:return
    r=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not r:return
    b=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False]);f=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not b or b['hash'].lower()!=r['blockHash'].lower() or not f or int(f['number'],16)<int(r['blockNumber'],16):return
    matches(row,s.rpc('eth_getTransactionByHash',[row['tx']]))
    if int(r['status'],16)!=1:
        s.write("UPDATE community_deployments SET state='failed',receipt=? WHERE id=?",(s.dump(r),ident));return
    factory=ct.addr(r.get('contractAddress'));validate(factory,r['blockNumber']);validate(factory,'latest')
    if ct.FACTORY and ct.FACTORY!=factory:raise s.Problem('Another launchpad is already active',409)
    spent=int(r['gasUsed'],16)*int(r['effectiveGasPrice'],16)
    if spent>int(json.loads(row['payload'])['maxGasWei']):raise s.Problem('Deployment fee exceeds reviewed limit',409)
    s.write("UPDATE community_deployments SET state='finalized',receipt=?,factory=? WHERE id=?",(s.dump({'tx':row['tx'],'block':int(r['blockNumber'],16),'factory':factory,'gasCostMON':s.units(spent,18)}),factory,ident))
    ct.FACTORY=factory
    with ct.LOCK:ct.CACHE.clear()
    ct.config(refresh=True)

def background_once():
    for row in s.rows("SELECT id FROM community_deployments WHERE state IN ('submitted','confirmed') ORDER BY created LIMIT 1"):
        try:reconcile(row['id'])
        except Exception:pass
