"""Wallet-deployed external-token revenue vaults and explicit feed opt-in."""
import json
from eth_abi import encode,decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak
import service as s,nadfun as n,venues as v,community_tokens as ct,launchpad as lp

ARTIFACT=s.ROOT/'nad-revenue-contract.json'
GAS_CAP=3*10**17
QUOTE_VENUE='Uniswap v2'
QUOTE_FACTORY,QUOTE_ROUTER,*_=ct.v2_routes.DEPLOYMENTS[QUOTE_VENUE]

def initialize():
    with s.connection() as db:db.executescript('''
    CREATE TABLE IF NOT EXISTS nad_revenue_vaults(token TEXT PRIMARY KEY,owner TEXT NOT NULL,wallet TEXT NOT NULL,vault TEXT UNIQUE NOT NULL,tx TEXT UNIQUE NOT NULL,block INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS nad_revenue_feeds(feed TEXT PRIMARY KEY,owner TEXT NOT NULL,token TEXT NOT NULL);
    ''')
    with s.connection() as db:
        columns={r[1] for r in db.execute('PRAGMA table_info(nad_revenue_vaults)')}
        for name,definition in [('stats','TEXT'),('verified','INTEGER')]:
            if name not in columns:db.execute('ALTER TABLE nad_revenue_vaults ADD COLUMN '+name+' '+definition)

def artifact():
    data=json.loads(ARTIFACT.read_text())
    for name in ['RallyCommunity.sol','RallyNadRevenue.sol']:
        if s.digest((s.ROOT/'contracts'/name).read_text())!=data['sourceHashes'][name]:raise s.Problem('Revenue contract source changed',503)
    return data['contracts']['RallyNadRevenueVault'],s.digest(s.dump(data))

def owner(who,token):
    user,wallet=v.wallet(who);token=n.address(token)
    row=s.one('SELECT * FROM launch_tokens WHERE token=? AND owner=? AND wallet=?',(token,user,wallet))
    if not row:raise s.Problem('Choose a token you launched or registered',403)
    info=n.token_info(token)
    if info['version']!='v2' or info['quoteToken']!=n.WMON or info['creator']!=wallet:raise s.Problem('This adapter requires your WMON-based nad.fun V2 token',409)
    return user,wallet,token,info

def values(data):
    out={}
    for key,default in [('buybackBps',2000),('burnBps',10000),('slippageBps',100)]:
        x=data.get(key,default)
        if type(x) is not int or not (1<=x<=500 if key=='slippageBps' else 0<=x<=10000):raise s.Problem('Choose valid revenue allocation and slippage')
        out[key]=x
    out['maxBatchRaw']=v.raw(data.get('maxBatchUSDC','1'),6,'1000')
    if out['maxBatchRaw']<10000:raise s.Problem('Minimum batch is 0.01 USDC')
    return out

def limits(who,data):
    _,_,token,info=owner(who,data.get('token'));n.pin('v2');ct.v2_routes.version(QUOTE_VENUE)
    policy=values(data);pair=ct.read(QUOTE_FACTORY,'getPair',['address','address'],[s.USDC,n.WMON],['address'])
    if pair==s.ZERO:raise s.Problem('The USDC/WMON pool is unavailable',409)
    reserves=ct.read(pair,'getReserves',outs=['uint112','uint112','uint32']);first=ct.read(pair,'token0',outs=['address'])
    quote_reserve=reserves[0 if first==s.USDC else 1]
    if quote_reserve//200<10000:raise s.Problem('Quote liquidity cannot support the minimum buyback batch',409)
    wrapped=ct.read(QUOTE_ROUTER,'getAmountsOut',['uint256','address[]'],[1_000_000,[s.USDC,n.WMON]],['uint256[]'])[-1]
    tokens=n.read('v2','router','getAmountOut',[token,wrapped,True])
    floor=tokens*(10000-policy['slippageBps'])//10000
    if floor<=0:raise s.Problem('No supported revenue buyback quote',409)
    return {'token':token,'symbol':info['symbol'],'quotePair':pair,'minTokensPerUSDC':str(floor),'minimumTokensPerUSDC':s.units(floor,18),'buybackBps':policy['buybackBps'],'burnBps':policy['burnBps'],'slippageBps':policy['slippageBps'],'maxBatchUSDC':s.units(policy['maxBatchRaw'],6),'maxBatchRaw':str(policy['maxBatchRaw']),'chainId':143,'route':['USDC','WMON',info['symbol']],'burnMethod':'dead_address','burnAddress':'0x000000000000000000000000000000000000dead','oracleWarmupSeconds':600,'priceProtection':'Creator-approved minimum tokens per USDC. Price appreciation can queue buybacks until the creator updates this limit.','fetchedAt':s.now(),'expires':s.now()+90}

def verify(row,block='latest'):
    a,_=artifact();target=row['vault'];code=s.rpc('eth_getCode',[target,block])
    if ct.normalized(code,a)!=ct.normalized(a['runtime'],a):raise s.Problem('Revenue vault code changed',503)
    expected={'creator':row['wallet'],'quoteToken':s.USDC,'wrappedToken':n.WMON,'communityToken':row['token'],'router':QUOTE_ROUTER,'nadRouter':n.contract('v2','router')}
    for key,value in expected.items():
        if n.simple(target,key,outs=['address'],block=block)!=value:raise s.Problem('Revenue vault identity changed',503)
    return target

def apply_floor(q,data):
    floor=str(data.get('minTokensPerUSDC',q['minTokensPerUSDC']))
    if not floor.isdigit() or not 0<int(floor)<=2**128-1:raise s.Problem('Invalid minimum token receive')
    if int(floor)>int(q['minTokensPerUSDC']):raise s.Problem('Price moved beyond the previewed limit. Refresh it.',409)
    q['minTokensPerUSDC']=floor;q['minimumTokensPerUSDC']=s.units(int(floor),18)

def snapshot(row,block=None):
    block=block or s.rpc('eth_blockNumber',[])
    target=verify(row,block);out={'owner':row['owner'],'token':row['token'],'vault':target,'creator':row['wallet'],'deploymentTx':row['tx'],'burnMethod':'dead_address','chainId':143,'verifiedBlock':block}
    for key in ['pendingBuyback','grossRevenue','creatorPaid','quoteSpent','tokensBought','tokensBurned','minTokensPerUSDC','maxBatchRaw']:
        out[key]=str(n.simple(target,key,block=block))
    for key in ['buybackBps','burnBps','slippageBps']:out[key]=n.simple(target,key,outs=['uint16'],block=block)
    out['policyNonce']=n.simple(target,'policyNonce',outs=['uint64'],block=block);out['paused']=n.simple(target,'paused',outs=['bool'],block=block);out['verifiedAt']=s.now()
    s.write('UPDATE nad_revenue_vaults SET stats=?,verified=? WHERE token=? AND vault=?',(s.dump(out),s.now(),row['token'],target))
    return out

def status(who,token):
    user,wallet,token,info=owner(who,token);row=s.one('SELECT * FROM nad_revenue_vaults WHERE token=? AND owner=? AND wallet=?',(token,user,wallet))
    return {'token':token,'symbol':info['symbol'],'revenue':snapshot(row) if row else None,'feeds':s.rows('SELECT id,name FROM feeds WHERE owner=? ORDER BY created DESC LIMIT 100',(user,)),'boundFeeds':[r['feed'] for r in s.rows('SELECT feed FROM nad_revenue_feeds WHERE owner=? AND token=?',(user,token))]}

def plan(who,data):
    user,wallet,token,info=owner(who,data.get('token'));a,digest=artifact();kind=data.get('kind');created=s.now();approval=None
    if kind=='revenue_deploy':
        if s.one('SELECT 1 FROM nad_revenue_vaults WHERE token=?',(token,)):raise s.Problem('This token already has a revenue vault',409)
        if s.one("SELECT 1 FROM execution_records r JOIN execution_plans p ON p.id=r.plan WHERE p.venue='nadrevenue' AND p.kind='revenue_deploy' AND json_extract(p.payload,'$.summary.token')=? AND r.state NOT IN ('failed','invalid')",(token,)):raise s.Problem('Check the existing vault deployment in Activity',409)
        q=limits(who,data);apply_floor(q,data);types=['address']*6+['uint16']*3+['uint256']*2
        args=[wallet,s.USDC,n.WMON,token,QUOTE_ROUTER,n.contract('v2','router'),q['buybackBps'],q['burnBps'],q['slippageBps'],int(q['minTokensPerUSDC']),int(q['maxBatchRaw'])]
        tx={'from':wallet,'data':a['bytecode']+encode(types,args).hex(),'value':'0x0','chainId':'0x8f','nonce':s.rpc('eth_getTransactionCount',[wallet,'pending'])}
        summary={**q,'action':'activate','asset':info['symbol'],'amount':'0','inputAsset':'MON','maxGasCostMON':s.units(GAS_CAP,18)}
    else:
        row=s.one('SELECT * FROM nad_revenue_vaults WHERE token=? AND owner=? AND wallet=?',(token,user,wallet))
        if not row:raise s.Problem('Activate the revenue vault first',409)
        target=verify(row);stats=snapshot(row)
        if kind=='revenue_policy':
            q=limits(who,data);apply_floor(q,data);calldata=ct.call('setPolicy',['uint16','uint16','uint16','uint256','uint256'],[q['buybackBps'],q['burnBps'],q['slippageBps'],int(q['minTokensPerUSDC']),int(q['maxBatchRaw'])]);summary={**q,'action':'update','asset':info['symbol'],'amount':'0','vault':target}
        elif kind=='revenue_execute':
            calldata=ct.call('executeBuyback',['uint256'],[created+120]);summary={'action':'buyback','asset':info['symbol'],'token':token,'amount':s.units(int(stats['pendingBuyback']),6),'inputAsset':'USDC','vault':target}
        elif kind=='revenue_checkpoint':calldata=ct.call('checkpoint');summary={'action':'checkpoint','asset':info['symbol'],'token':token,'amount':'0','vault':target}
        elif kind=='revenue_pause':
            if type(data.get('paused')) is not bool:raise s.Problem('Choose pause or resume')
            calldata=ct.call('setPaused',['bool'],[data['paused']]);summary={'action':'pause' if data['paused'] else 'resume','asset':info['symbol'],'token':token,'amount':'0','vault':target,'paused':data['paused']}
        else:raise s.Problem('Unsupported revenue action')
        tx={'from':wallet,'to':target,'data':calldata,'value':'0x0','chainId':'0x8f'}
    ident=s.uid();p={'transaction':tx,'approval':approval,'summary':summary,'args':data,'created':created,'expires':created+90,'artifactHash':digest}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,wallet,'nadrevenue',kind,s.dump(p),p['expires']))
    return {'id':ident,**p}

def prepare(row,p):
    _,wallet,token,_=owner({'user':row['user_id'],'grant':None},p['summary']['token'])
    if artifact()[1]!=p['artifactHash']:raise s.Problem('Revenue contract changed',409)
    n.pin('v2');ct.v2_routes.version(QUOTE_VENUE)
    if row['kind']=='revenue_deploy':
        if s.one('SELECT 1 FROM nad_revenue_vaults WHERE token=?',(token,)):raise s.Problem('Vault already activated',409)
        if s.rpc('eth_getTransactionCount',[wallet,'pending'])!=p['transaction']['nonce']:raise s.Problem('Wallet nonce changed. Refresh activation.',409)
    else:
        stored=s.one('SELECT * FROM nad_revenue_vaults WHERE token=? AND owner=?',(token,row['user_id']))
        if not stored or stored['vault']!=p['transaction']['to']:raise s.Problem('Vault binding changed',409)
        verify(stored)

def transaction_check(p,tx):
    if p['transaction'].get('nonce') and int(tx.get('nonce','0x0'),16)!=int(p['transaction']['nonce'],16):raise s.Problem('Deployment nonce differs',409)
    if p['summary'].get('maxGasCostMON') and int(tx.get('gas','0x0'),16)*int(tx.get('maxFeePerGas') or tx.get('gasPrice','0x0'),16)>GAS_CAP:raise s.Problem('Deployment exceeds the 0.3 MON gas cap',409)

def buyback_delivery(receipt,row,pair):
    topic='0x'+keccak(text='BuybackExecuted(uint256,uint256,uint256,uint256)').hex()
    events=[l for l in receipt.get('logs',[]) if not l.get('removed') and l.get('address','').lower()==row['vault'] and l.get('topics')==[topic]]
    if len(events)!=1:return None
    try:
        spent,bought,sunk,treasury=decode(['uint256']*4,bytes.fromhex(events[0]['data'][2:]))
        def transfers(token,source=None,dest=None):
            return sum(int(l['data'],16) for l in receipt.get('logs',[]) if not l.get('removed') and l.get('address','').lower()==token and len(l.get('topics',[]))==3 and l['topics'][0].lower()==n.TRANSFER and (source is None or '0x'+l['topics'][1][-40:].lower()==source) and (dest is None or '0x'+l['topics'][2][-40:].lower()==dest))
        if not spent or not bought or sunk+treasury!=bought:return None
        if transfers(s.USDC,row['vault'],pair)!=spent or transfers(row['token'],dest=row['vault'])!=bought:return None
        if transfers(row['token'],row['vault'],'0x000000000000000000000000000000000000dead')!=sunk or transfers(row['token'],row['vault'],row['wallet'])!=treasury:return None
        return {'quoteSpentRaw':str(spent),'tokensBoughtRaw':str(bought),'tokensSunkRaw':str(sunk),'creatorTokensRaw':str(treasury),'burnMethod':'dead_address','token':row['token']}
    except (ValueError,KeyError,TypeError,OverflowError,DecodingError):return None

def reconcile(row):
    p=json.loads(row['payload']);r=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not r:return
    b=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False]);f=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not b or b['hash'].lower()!=r['blockHash'].lower():return
    state='finalized' if f and int(f['number'],16)>=int(r['blockNumber'],16) else 'confirmed';out={'receipt':r,'businessState':'revenue_receipt_pending'}
    if int(r['status'],16)!=1:state='failed';out['businessState']='reverted'
    elif row['kind']=='revenue_deploy':
        vault=n.address(r.get('contractAddress'));candidate={'token':p['summary']['token'],'owner':row['user_id'],'wallet':p['transaction']['from'],'vault':vault,'tx':row['tx'],'block':int(r['blockNumber'],16)}
        stats=snapshot(candidate,r['blockNumber'])
        if any(str(stats[k])!=str(p['summary'][k]) for k in ['buybackBps','burnBps','slippageBps','minTokensPerUSDC','maxBatchRaw']):raise s.Problem('Deployed policy differs',409)
        if state=='finalized':
            with s.connection() as db:
                old=db.execute('SELECT vault FROM nad_revenue_vaults WHERE token=?',(candidate['token'],)).fetchone()
                if old and old['vault']!=vault:raise s.Problem('Another revenue vault is registered',409)
                db.execute('INSERT OR IGNORE INTO nad_revenue_vaults(token,owner,wallet,vault,tx,block,stats,verified) VALUES(?,?,?,?,?,?,?,?)',tuple(candidate[k] for k in ['token','owner','wallet','vault','tx','block'])+(s.dump(stats),s.now()))
        out.update(businessState='revenue_vault_active' if state=='finalized' else 'deployment_confirmed',vault=vault,token=candidate['token'])
    else:
        stored=s.one('SELECT * FROM nad_revenue_vaults WHERE token=?',(p['summary']['token'],));stats=snapshot(stored)
        out.update(businessState='revenue_'+row['kind'].removeprefix('revenue_')+'_confirmed',revenue=stats)
        if row['kind']=='revenue_execute':
            pair=n.simple(stored['vault'],'pair',outs=['address'],block=r['blockNumber']);delivery=buyback_delivery(r,stored,pair)
            out['businessState']='buyback_executed' if delivery else 'buyback_delivery_verification_pending'
            if delivery:out['delivery']=delivery
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(out),row['id']))

def bind(who,data):
    user,wallet,token,_=owner(who,data.get('token'));row=s.one('SELECT * FROM nad_revenue_vaults WHERE token=? AND owner=? AND wallet=?',(token,user,wallet))
    if not row:raise s.Problem('Wait for vault activation to finalize',409)
    verify(row);feed=s.one('SELECT * FROM feeds WHERE id=? AND owner=?',(data.get('feed'),user))
    if not feed:raise s.Problem('Choose an algorithm you own',403)
    s.write('INSERT INTO nad_revenue_feeds VALUES(?,?,?) ON CONFLICT(feed) DO UPDATE SET owner=excluded.owner,token=excluded.token',(feed['id'],user,token))
    return status(who,token)

def route(feed):
    row=s.one('SELECT v.* FROM nad_revenue_feeds b JOIN nad_revenue_vaults v ON v.token=b.token WHERE b.feed=? AND b.owner=?',(feed['id'],feed['owner']))
    if not row:return None
    if row['wallet']!=feed['recipient']:raise s.Problem('Revenue recipient changed. Reconnect the algorithm.',409)
    stats=snapshot(row)
    return {'vault':row['vault'],'creator':row['wallet'],'communityToken':row['token'],'community':'launch_'+row['token'][2:],'buybackBps':stats['buybackBps'],'burnBps':stats['burnBps'],'policyNonce':stats['policyNonce'],'kind':'nad_revenue','burnMethod':'dead_address','artifactHash':artifact()[1]}

def public(feed):
    # Public feed rendering uses the last verified policy; signing always reads
    # fresh chain state through route() and verify_terms(). No provider waterfall.
    row=s.one('SELECT v.* FROM nad_revenue_feeds b JOIN nad_revenue_vaults v ON v.token=b.token WHERE b.feed=? AND b.owner=?',(feed['id'],feed['owner']))
    if not row:return None
    stats=json.loads(row['stats'] or '{}');token=n.token_info(row['token'],False)
    return {'owner':row['owner'],'creatorWallet':row['wallet'],'address':row['token'],'vault':row['vault'],'community':'launch_'+row['token'][2:],'name':token['name'],'symbol':token['symbol'],'logoURI':token.get('logoURI'),'chainId':143,'venue':'nad.fun V2','buybackBps':stats.get('buybackBps',0),'burnBps':stats.get('burnBps',0),'stats':stats,'verifiedAt':row['verified'],'stale':not row['verified'] or s.now()-row['verified']>120,'burnMethod':'dead_address'}

def verify_terms(t):
    row=s.one('SELECT * FROM nad_revenue_vaults WHERE token=? AND vault=?',(t['communityToken'],t['vault']))
    if not row or artifact()[1]!=t['artifactHash']:raise s.Problem('Revenue settlement binding changed',409)
    verify(row)
    n.pin('v2');ct.v2_routes.version(QUOTE_VENUE)
    if n.simple(t['vault'],'policyNonce',outs=['uint64'])!=t['policyNonce']:raise s.Problem('Creator allocation changed. Start a fresh checkout.',409,'policy_changed')
