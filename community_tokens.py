"""Creator token onboarding and unsigned, pinned Monad transactions."""
import json, os, re, threading, time
from decimal import Decimal, InvalidOperation
from eth_abi import encode, decode
from eth_utils import keccak
import service as s
import v2_routes
import extra_routes as e

FACTORY=os.environ.get('RALLY_COMMUNITY_FACTORY','').lower()
ARTIFACT=s.ROOT/'community-contracts.json'
ROUTER=v2_routes.DEPLOYMENTS['PancakeSwap v2'][1]
CACHE={};LOCK=threading.Lock()
LAUNCH_TOPIC='0x'+keccak(text='CommunityLaunched(address,address,address,address,uint256,uint16,uint16,uint16)').hex()
REVENUE_TOPIC='0x'+keccak(text='RevenuePaid(bytes32,bytes32,address,uint256,uint256,uint256,uint64)').hex()
TRANSFER_TOPIC='0x'+keccak(text='Transfer(address,address,uint256)').hex()

def initialize():
    with s.connection() as db:
        fresh=not db.execute("SELECT 1 FROM sqlite_master WHERE name='community_onboarding'").fetchone()
        db.executescript('''
        CREATE TABLE IF NOT EXISTS community_onboarding(user_id TEXT PRIMARY KEY REFERENCES accounts(id),state TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS creator_tokens(owner TEXT PRIMARY KEY REFERENCES accounts(id),wallet TEXT,draft TEXT,state TEXT,token TEXT UNIQUE,vault TEXT UNIQUE,pair TEXT,community TEXT UNIQUE,stats TEXT,verified INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS community_plans(id TEXT PRIMARY KEY,owner TEXT,wallet TEXT,kind TEXT,payload TEXT,created INTEGER,expires INTEGER,tx TEXT UNIQUE,state TEXT,receipt TEXT);
        CREATE INDEX IF NOT EXISTS community_plan_state ON community_plans(state,created);
        ''')
        if 'wallet' not in {x[1] for x in db.execute('PRAGMA table_info(creator_tokens)')}:
            db.execute('ALTER TABLE creator_tokens ADD COLUMN wallet TEXT')
        if 'image_media' not in {x[1] for x in db.execute('PRAGMA table_info(creator_tokens)')}:
            db.execute('ALTER TABLE creator_tokens ADD COLUMN image_media TEXT')
        db.execute('CREATE INDEX IF NOT EXISTS community_token_image ON creator_tokens(image_media,state)')
        if fresh:db.execute("INSERT OR IGNORE INTO community_onboarding SELECT id,'existing',? FROM accounts",(s.now(),))
    import community_deployment
    community_deployment.initialize()
    for row in s.rows("SELECT owner FROM creator_tokens WHERE state='live'"):register_asset(row['owner'])

def addr(value):
    value=str(value or '').lower()
    if not re.fullmatch('0x[0-9a-f]{40}',value) or value==s.ZERO:raise s.Problem('Invalid contract address')
    return value

def call(name,types=(),args=()):return '0x'+keccak(text=name+'('+','.join(types)+')').hex()[:8]+encode(list(types),list(args)).hex()
def read(target,name,types=(),args=(),outs=('uint256',),block='latest'):
    value=s.rpc('eth_call',[{'to':target,'data':call(name,types,args)},block])
    values=decode(list(outs),bytes.fromhex(value[2:]))
    return values[0] if len(values)==1 else values
def word(value):return bytes.fromhex(s.digest(str(value)))

def normalized(code,artifact):
    body=bytearray.fromhex(code[2:]);expected=artifact['runtime']
    if len(body)!=(len(expected)-2)//2:raise s.Problem('Community contract changed',503,'community_contract_changed')
    for refs in artifact['immutables'].values():
        for ref in refs:body[ref['start']:ref['start']+ref['length']]=b'\0'*ref['length']
    return '0x'+body.hex()

def pin():
    if not FACTORY or not re.fullmatch('0x[0-9a-f]{40}',FACTORY) or FACTORY==s.ZERO:
        raise s.Problem('Community token launch is awaiting mainnet activation',503,'community_activation_required')
    artifact=json.loads(ARTIFACT.read_text())['contracts']['RallyCommunityFactory']
    code=s.rpc('eth_getCode',[FACTORY,'latest'])
    if normalized(code,artifact)!=normalized(artifact['runtime'],artifact):raise s.Problem('Community contract changed',503,'community_contract_changed')
    if read(FACTORY,'quoteToken',outs=['address']).lower()!=s.USDC or read(FACTORY,'router',outs=['address']).lower()!=ROUTER:
        raise s.Problem('Community deployment does not match Monad configuration',503,'community_contract_changed')
    v2_routes.version('PancakeSwap v2')
    return FACTORY

def config(refresh=False):
    base={'enabled':False,'reason':'community_activation_required' if not FACTORY else 'community_verification_pending','chainId':143,'factory':FACTORY or None,'quoteToken':s.USDC,'quoteSymbol':'USDC','venue':'PancakeSwap v2','initialSupply':'1000000000','initialPoolShareBps':10000,'lpRecipient':'creator','oracleWarmupSeconds':600,'maxPoolInputBps':50,'automaticOnPayment':True,'keeperMode':os.environ.get('RALLY_COMMUNITY_KEEPER_MODE','observe')}
    with LOCK:
        cached=dict(CACHE.get('config',base));due=time.monotonic()-CACHE.get('at',0)>30
    # Background verification cannot block first paint or sign-in.
    if not refresh or not due:return cached
    if FACTORY:
        try:pin();base.update(enabled=True,reason=None)
        except Exception:base['reason']='community_contract_unavailable'
    with LOCK:CACHE.update(at=time.monotonic(),config=base)
    return dict(base)

def values(data):
    name=str(data.get('name') or '').strip();symbol=str(data.get('symbol') or '').strip().upper()
    if not name or len(name)>32 or len(name.encode())>64:raise s.Problem('Use a token name of 1–32 characters')
    if not re.fullmatch('[A-Z0-9]{2,10}',symbol):raise s.Problem('Use a symbol of 2–10 letters or numbers')
    bps={}
    for key,default in [('buybackBps',2000),('burnBps',10000),('slippageBps',100)]:
        value=data.get(key,default)
        if not isinstance(value,int) or isinstance(value,bool) or not (1<=value<=500 if key=='slippageBps' else 0<=value<=10000):raise s.Problem('Invalid '+key)
        bps[key]=value
    try:
        seed=Decimal(str(data.get('seedUSDC','10')))
        if not seed.is_finite() or not 1<=seed<=1_000_000 or seed*1_000_000!=int(seed*1_000_000):raise ValueError()
    except (ValueError,InvalidOperation,OverflowError):raise s.Problem('Initial liquidity must be 1–1,000,000 USDC')
    image_id=str(data.get('imageId') or '')
    preset=str(data.get('imagePreset') or '')
    if image_id and not re.fullmatch('[0-9a-f]{32}',image_id):raise s.Problem('Choose a token image')
    if preset not in {'','rally'} or image_id and preset:raise s.Problem('Choose one token image')
    path='/media/'+image_id if image_id else '/assets/community-rally.png' if preset else None
    return {'name':name,'symbol':symbol,'seedUSDC':s.units(int(seed*1_000_000),6),'seedRaw':str(int(seed*1_000_000)),
      'imageId':image_id or None,'imagePreset':preset or None,'imageURI':os.environ.get('RALLY_PUBLIC_ORIGIN','https://rallydot.com').rstrip('/')+path if path else None,**bps}

def validate_image(user,draft):
    if draft.get('imageId'):
        media=s.one('SELECT owner,mime FROM media WHERE id=?',(draft['imageId'],))
        if not media or media['owner']!=user or media['mime'] not in {'image/png','image/jpeg','image/webp'}:raise s.Problem('Use an image uploaded to your account',403)
    if draft.get('imagePreset'):
        import community_deployment
        if not community_deployment.permitted(user):raise s.Problem('Use your own community image',403)

def public_image(ident):
    return bool(re.fullmatch('[0-9a-f]{32}',ident) and s.one("SELECT 1 FROM creator_tokens WHERE image_media=? AND state='live' LIMIT 1",(ident,)))

def status(user):
    row=s.one('SELECT * FROM creator_tokens WHERE owner=?',(user,)) if user else None
    onboard=s.one('SELECT state FROM community_onboarding WHERE user_id=?',(user,)) if user else None
    account=s.one('SELECT kind,wallet FROM accounts WHERE id=?',(user,)) if user else None
    eligible=bool(account and account['kind']=='person' and (account['wallet'] or s.one("SELECT 1 FROM external_identities WHERE provider='privy' AND user_id=?",(user,))))
    import community_deployment
    return {'deployment':community_deployment.status(user),'onboarding':bool(eligible and not onboard),'config':config(),'draft':json.loads(row['draft']) if row else None,'state':row['state'] if row else 'not_started','token':public(user),'plans':[plan_view(x) for x in s.rows('SELECT * FROM community_plans WHERE owner=? ORDER BY created DESC LIMIT 3',(user,))] if user else []}

def public(owner):
    row=s.one("SELECT * FROM creator_tokens WHERE owner=? AND state='live'",(owner,))
    if not row:return None
    draft=json.loads(row['draft']);stats=json.loads(row['stats'] or '{}');asset=s.GATEWAY.token_map.get(row['token'])
    if asset:
        asset=dict(asset);asset['stale']=s.now()-asset.get('fetchedAt',0)>120
        if asset['stale']:asset['price']=None
    return {'owner':owner,'creatorWallet':row['wallet'],'address':row['token'],'vault':row['vault'],'pair':row['pair'],'community':row['community'],'name':draft['name'],'symbol':draft['symbol'],'logoURI':draft.get('imageURI'),'chainId':143,'venue':'PancakeSwap v2','buybackBps':stats.get('buybackBps',draft['buybackBps']),'burnBps':stats.get('burnBps',draft['burnBps']),'stats':stats,'asset':asset,'verifiedAt':row['verified'],'stale':s.now()-row['verified']>120}

def save(who,data):
    user=s.require(who,human=True);draft=values(data)
    validate_image(user,draft)
    row=s.one('SELECT state FROM creator_tokens WHERE owner=?',(user,))
    if row and row['state'] not in {'draft','launch_failed'}:raise s.Problem('This token launch already has a transaction. Check its status.',409)
    with s.connection() as db:
        db.execute("INSERT INTO creator_tokens(owner,draft,state,image_media) VALUES(?,?,'draft',?) ON CONFLICT(owner) DO UPDATE SET draft=excluded.draft,state='draft',image_media=excluded.image_media",(user,s.dump(draft),draft['imageId']))
        db.execute("INSERT INTO community_onboarding VALUES(?,'configured',?) ON CONFLICT(user_id) DO UPDATE SET state='configured'",(user,s.now()))
    return status(user)

def dismiss(who):
    user=s.require(who,human=True)
    s.write("INSERT INTO community_onboarding VALUES(?,'later',?) ON CONFLICT(user_id) DO UPDATE SET state='later'",(user,s.now()))
    return {'ok':True}

def wallet(who):
    user=s.require(who,human=True);address=(s.one('SELECT wallet FROM accounts WHERE id=?',(user,)) or {}).get('wallet')
    if not address:raise s.Problem('Connect your wallet to launch',409,'wallet_required')
    return user,addr(address)

def plan_view(row):
    p=json.loads(row['payload'])
    return {'id':row['id'],'kind':row['kind'],'state':row['state'],'tx':row['tx'],'summary':p['summary'],'expires':row['expires'],'receipt':json.loads(row['receipt']) if row['receipt'] else None}

def plan(who,data):
    user,w=wallet(who);factory=pin();kind=data.get('kind','launch')
    row=s.one('SELECT * FROM creator_tokens WHERE owner=?',(user,))
    if not row:raise s.Problem('Save your token settings first',409)
    if s.one("SELECT 1 FROM community_plans WHERE owner=? AND state IN ('submitted','confirmed')",(user,)):raise s.Problem('A transaction is still pending. Check its status.',409)
    if kind=='launch':
        if row['state'] not in {'draft','launch_failed'}:raise s.Problem('This community token already launched',409)
        if read(factory,'vaultOf',['address'],[w],['address'])!=s.ZERO:raise s.Problem('This wallet already has a community token',409)
        draft=json.loads(row['draft']);target=factory
        validate_image(user,draft)
        if not draft.get('imageURI'):raise s.Problem('Add your token image before launch',409)
        txdata=call('launch',['string','string','uint256','uint16','uint16','uint16'],[draft['name'],draft['symbol'],int(draft['seedRaw']),draft['buybackBps'],draft['burnBps'],draft['slippageBps']])
        approval={'token':s.USDC,'spender':factory,'amountRaw':draft['seedRaw']}
    elif kind=='policy':
        if row['state']!='live':raise s.Problem('Launch your community token first',409)
        draft=values({**json.loads(row['draft']),**data});validate_image(user,draft);target=row['vault']
        if read(target,'creator',outs=['address'])!=w:raise s.Problem('Use the community creator wallet',409)
        min_=read(target,'minBatchRaw');max_=read(target,'maxBatchRaw')
        txdata=call('setPolicy',['uint16','uint16','uint16','uint256','uint256'],[draft['buybackBps'],draft['burnBps'],draft['slippageBps'],min_,max_]);approval=None
    else:raise s.Problem('Unknown community action')
    ident=s.uid();created=s.now();p={'factory':factory,'draft':draft,'transaction':{'from':w,'to':target,'data':txdata,'value':'0x0','chainId':'0x8f'},'approval':approval,'summary':{**draft,'venue':'PancakeSwap v2','initialPoolShareBps':10000,'lpRecipient':w}}
    s.write("INSERT INTO community_plans VALUES(?,?,?,?,?,?,?,NULL,'awaiting_wallet',NULL)",(ident,user,w,kind,s.dump(p),created,created+180))
    return plan_view(s.one('SELECT * FROM community_plans WHERE id=?',(ident,)))

def owned(who,ident):
    user=s.require(who,human=True);row=s.one('SELECT * FROM community_plans WHERE id=? AND owner=?',(ident,user))
    if not row:raise s.Problem('Token transaction not found',404)
    return row

def gas(tx):
    value={k:v for k,v in tx.items() if k!='chainId'}
    limit=(int(s.rpc('eth_estimateGas',[value]),16)*125+99)//100
    fee=limit*int(s.rpc('eth_gasPrice',[]),16)
    if int(s.rpc('eth_getBalance',[tx['from'],'latest']),16)<fee:raise s.Problem('Add MON for the network fee',409,'insufficient_gas')
    return {**tx,'gas':hex(limit)},s.units(fee,18)

def prepare(who,data):
    row=owned(who,data.get('plan'));p=json.loads(row['payload']);_,w=wallet(who)
    if row['wallet']!=w:raise s.Problem('Wallet changed. Review a new transaction.',409)
    if row['tx'] or row['expires']<s.now():raise s.Problem('Review a fresh token transaction',409)
    if pin()!=p['factory']:raise s.Problem('Community deployment changed',409)
    if p['approval']:
        a=p['approval'];amount=int(a['amountRaw'])
        if read(s.USDC,'balanceOf',['address'],[w])<amount:raise s.Problem('Not enough USDC for initial liquidity',409,'insufficient_balance')
        if read(s.USDC,'allowance',['address','address'],[w,a['spender']])<amount:
            tx,cost=gas({'from':w,'to':s.USDC,'data':call('approve',['address','uint256'],[a['spender'],amount]),'value':'0x0','chainId':'0x8f'})
            return {'approval':tx,'estimatedGasCostMON':cost,'summary':p['summary']}
    if row['kind']=='launch' and read(p['factory'],'vaultOf',['address'],[w],['address'])!=s.ZERO:raise s.Problem('This wallet already launched',409)
    if row['kind']=='policy' and read(p['transaction']['to'],'creator',outs=['address'])!=w:raise s.Problem('Use the creator wallet',409)
    tx,cost=gas(p['transaction'])
    return {'transaction':tx,'estimatedGasCostMON':cost,'summary':p['summary']}

def record(who,data):
    row=owned(who,data.get('plan'));tx=str(data.get('tx') or '').lower()
    if not re.fullmatch('0x[0-9a-f]{64}',tx):raise s.Problem('Invalid transaction hash')
    if row['tx'] and row['tx']!=tx:raise s.Problem('This launch uses another transaction',409)
    if not row['tx']:
        p=json.loads(row['payload']);t=s.rpc('eth_getTransactionByHash',[tx]);expected=p['transaction']
        if not t:raise s.Problem('Transaction is not indexed. Retry this hash.',409,'transaction_pending')
        import wallet_execution
        wallet_execution.verified_call(tx,expected,t)
        try:
            with s.connection() as db:
                db.execute("UPDATE community_plans SET tx=?,state='submitted' WHERE id=? AND tx IS NULL",(tx,row['id']))
                if db.execute('SELECT tx FROM community_plans WHERE id=?',(row['id'],)).fetchone()['tx']!=tx:raise s.Problem('Another transaction was recorded',409)
                if row['kind']=='launch':db.execute("UPDATE creator_tokens SET state='submitted' WHERE owner=?",(row['owner'],))
        except s.sqlite3.IntegrityError:raise s.Problem('Transaction already used',409)
    reconcile(row['id']);return plan_view(s.one('SELECT * FROM community_plans WHERE id=?',(row['id'],)))

def approval_check(who,data):
    row=owned(who,data.get('plan'));p=json.loads(row['payload']);a=p['approval']
    if not a:raise s.Problem('This action does not need an allowance')
    tx=str(data.get('tx') or '').lower()
    if not re.fullmatch('0x[0-9a-f]{64}',tx):raise s.Problem('Invalid transaction hash')
    observed=s.rpc('eth_getTransactionByHash',[tx])
    if not observed:return {'state':'pending','tx':tx}
    expected=call('approve',['address','uint256'],[a['spender'],int(a['amountRaw'])])
    import wallet_execution
    try:wallet_execution.verified_call(tx,{'from':row['wallet'],'to':a['token'],'data':expected,'value':'0x0'},observed)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending','tx':tx}
        raise
    try:r=wallet_execution.finalized_receipt(tx)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending','tx':tx}
        raise
    if int(r['status'],16)==1:
        topic='0x'+keccak(text='Approval(address,address,uint256)').hex()
        events=[l for l in r.get('logs',[]) if not l.get('removed') and l['address'].lower()==a['token'] and len(l.get('topics',[]))==3 and l['topics'][0].lower()==topic and '0x'+l['topics'][1][-40:].lower()==row['wallet'] and '0x'+l['topics'][2][-40:].lower()==a['spender'] and int(l.get('data','0x0'),16)==int(a['amountRaw'])]
        if len(events)!=1:raise s.Problem('Expected USDC approval event was not verified',409)
    return {'state':'confirmed' if int(r['status'],16)==1 else 'failed','tx':tx}

def refresh(owner,block='latest'):
    row=s.one("SELECT * FROM creator_tokens WHERE owner=? AND state='live'",(owner,))
    if not row:return None
    if not config()['enabled']:raise s.Problem('Community contract unavailable',503)
    vault=row['vault'];token=row['token'];w=row['wallet']
    if not w:raise s.Problem('Community creator identity unavailable',503)
    block=s.rpc('eth_blockNumber',[]) if block=='latest' else block
    integers=['pendingBuyback','grossRevenue','creatorPaid','quoteSpent','tokensBought','tokensBurned','policyNonce','minBatchRaw','maxBatchRaw']
    bps=['buybackBps','burnBps','slippageBps']
    names=integers+bps+['paused']
    calls=[e.request(vault,k+'()') for k in names]+[e.request(token,'totalSupply()')]
    calls+=[e.request(vault,k+'()') for k in ['creator','communityToken','quoteToken','router','pair']]+[e.request(FACTORY,'vaultOf(address)',['address'],[w])]
    calls+=[e.request(row['pair'],'getReserves()'),e.request(row['pair'],'token0()')]
    data=e.batch(calls,block)
    if not all(ok for ok,_ in data):raise s.Problem('Community read unavailable',503)
    vals=[e.decoded(['bool' if k=='paused' else 'uint256'],payload)[0] for k,(_,payload) in zip(names+['supplyRaw'],data)]
    stats={k:v if k in bps+['paused'] else str(v) for k,v in zip(names+['supplyRaw'],vals)}
    identity=[e.decoded(['address'],payload)[0] for _,payload in data[len(names)+1:len(names)+7]]
    if identity!=[w,token,s.USDC,ROUTER,row['pair'],vault]:raise s.Problem('Community identity changed',503)
    r0,r1,_=e.decoded(['uint112','uint112','uint32'],data[-2][1]);first=e.decoded(['address'],data[-1][1])[0]
    if first not in {s.USDC,token}:raise s.Problem('Community pool assets changed',503)
    qraw,traw=(r0,r1) if first==s.USDC else (r1,r0)
    reference=Decimal(qraw)*10**12/Decimal(traw) if qraw and traw else None
    stats.update(poolQuoteRaw=str(qraw),poolTokenRaw=str(traw),referencePriceUSDC=str(reference) if reference is not None else None,referenceMarketCapUSDC=str(reference*Decimal(stats['supplyRaw'])/10**18) if reference is not None else None)
    s.write('UPDATE creator_tokens SET stats=?,verified=? WHERE owner=?',(s.dump(stats),s.now(),owner));register_asset(owner);market_price(owner,stats);return public(owner)

def reconcile(ident):
    row=s.one('SELECT * FROM community_plans WHERE id=?',(ident,))
    if not row or not row['tx'] or row['state'] in {'finalized','failed','invalid'}:return
    r=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not r:return
    b=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False])
    if not b or b['hash'].lower()!=r['blockHash'].lower():return
    final=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not final or int(final['number'],16)<int(r['blockNumber'],16):
        s.write("UPDATE community_plans SET state='confirmed',receipt=? WHERE id=?",(s.dump({'receipt':r,'verified':False}),ident));return
    if int(r['status'],16)!=1:
        s.write("UPDATE community_plans SET state='failed',receipt=? WHERE id=?",(s.dump(r),ident))
        if row['kind']=='launch':s.write("UPDATE creator_tokens SET state='launch_failed' WHERE owner=?",(row['owner'],))
        return
    state='finalized'
    p=json.loads(row['payload']);draft=p['draft']
    if int(b['timestamp'],16)<row['created']-5:raise s.Problem('Transaction predates launch',409)
    if row['kind']=='launch':
        logs=[l for l in r['logs'] if not l.get('removed') and l['address'].lower()==p['factory'] and len(l.get('topics',[]))==4 and l['topics'][0].lower()==LAUNCH_TOPIC and '0x'+l['topics'][1][-40:].lower()==row['wallet']]
        if len(logs)!=1:raise s.Problem('Launch event not verified',409)
        log=logs[0];token='0x'+log['topics'][2][-40:].lower();vault='0x'+log['topics'][3][-40:].lower()
        pair,seed,bb,burn_,slip=decode(['address','uint256','uint16','uint16','uint16'],bytes.fromhex(log['data'][2:]))
        if (seed,bb,burn_,slip)!=(int(draft['seedRaw']),draft['buybackBps'],draft['burnBps'],draft['slippageBps']):raise s.Problem('Launch settings differ',409)
        block=r['blockNumber']
        transfers=[l for l in r['logs'] if not l.get('removed') and l['address'].lower()==token and len(l.get('topics',[]))==3 and l['topics'][0].lower()==TRANSFER_TOPIC and int(l.get('data','0x0'),16)==10**27]
        mint=[l for l in transfers if '0x'+l['topics'][1][-40:].lower()==s.ZERO and '0x'+l['topics'][2][-40:].lower()==p['factory']]
        deposit=[l for l in transfers if '0x'+l['topics'][1][-40:].lower()==p['factory'] and '0x'+l['topics'][2][-40:].lower()==pair]
        checks=[len(mint)==1,len(deposit)==1,read(p['factory'],'vaultOf',['address'],[row['wallet']],['address'],block)==vault,read(vault,'creator',outs=['address'],block=block)==row['wallet'],read(vault,'communityToken',outs=['address'],block=block)==token,read(vault,'pair',outs=['address'],block=block)==pair,read(token,'name',outs=['string'],block=block)==draft['name'],read(token,'symbol',outs=['string'],block=block)==draft['symbol'],read(token,'totalSupply',block=block)<=10**27]
        if not all(checks):raise s.Problem('Launch identity not verified',409)
        if state=='finalized':
            cid='creator_'+row['owner']
            with s.connection() as db:
                db.execute("UPDATE creator_tokens SET state='live',wallet=?,draft=?,token=?,vault=?,pair=?,community=?,image_media=? WHERE owner=?",(row['wallet'],s.dump(draft),token,vault,pair,cid,draft.get('imageId'),row['owner']))
                db.execute('INSERT OR IGNORE INTO communities VALUES(?,?,?)',(cid,draft['name'],'Community token: '+draft['symbol']))
                db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(row['owner'],cid))
    elif state=='finalized':
        vault=p['transaction']['to'];block=r['blockNumber']
        if read(vault,'creator',outs=['address'],block=block)!=row['wallet'] or any(read(vault,k,outs=['uint16'],block=block)!=draft[k] for k in ['buybackBps','burnBps','slippageBps']):raise s.Problem('Policy update not verified',409)
        s.write('UPDATE creator_tokens SET draft=?,image_media=? WHERE owner=?',(s.dump(draft),draft.get('imageId'),row['owner']))
    s.write('UPDATE community_plans SET state=?,receipt=? WHERE id=?',(state,s.dump({'receipt':r,'verified':state=='finalized'}),ident))
    if state=='finalized':
        register_asset(row['owner'])
        # Launch finality and verified identity do not depend on live price reads.
        # The background collector retries metrics when the provider is unavailable.
        try:refresh(row['owner'])
        except s.Problem:pass

def route(feed):
    row=s.one("SELECT * FROM creator_tokens WHERE owner=? AND state='live'",(feed['owner'],))
    if not row:return None
    token=refresh(feed['owner']);stats=token['stats']
    if feed['recipient']!=row['wallet']:raise s.Problem('Use the community creator wallet as this feed’s payment recipient',409)
    return {'vault':row['vault'],'creator':row['wallet'],'communityToken':row['token'],'community':row['community'],'buybackBps':stats['buybackBps'],'burnBps':stats['burnBps'],'policyNonce':int(stats['policyNonce'])}

def register_asset(owner):
    info=public(owner)
    if not info:return
    avatar=(s.one('SELECT avatar FROM accounts WHERE id=?',(owner,)) or {}).get('avatar')
    asset={'id':info['address'],'address':info['address'],'name':info['name'],'symbol':info['symbol'],'decimals':18,'chainId':143,'logoURI':info['logoURI'] or avatar or None,'communityToken':True,'pair':info['pair']}
    with s.LOCK:
        if asset['id'] in s.GATEWAY.token_map:s.GATEWAY.token_map[asset['id']].update(asset)
        else:s.GATEWAY.tokens.append(asset);s.GATEWAY.token_map[asset['id']]=asset

def market_price(owner,stats):
    info=public(owner);reference=s.GATEWAY.prices.get(s.USDC,{})
    if not info:return
    price_usdc=Decimal(stats['referencePriceUSDC']) if stats.get('referencePriceUSDC') else None;ref=reference.get('price')
    usd=float(price_usdc*Decimal(str(ref))) if price_usdc is not None and ref and s.now()-reference.get('fetchedAt',0)<=120 else None
    snapshot={'price':usd,'priceUSDC':str(price_usdc) if price_usdc is not None else None,'marketCap':float(Decimal(str(usd))*Decimal(stats['supplyRaw'])/10**18) if usd is not None else None,'pool':info['pair'],'pairAddress':info['pair'],'fetchedAt':s.now(),'priceSource':'PancakeSwap v2 pool reserves','referenceOnly':True}
    with s.LOCK:
        s.GATEWAY.prices[info['address']]=snapshot
        s.GATEWAY.token_map[info['address']]={**s.GATEWAY.token_map[info['address']],**snapshot}

def background_once():
    import community_deployment
    community_deployment.background_once()
    config(refresh=True)
    for row in s.rows("SELECT id FROM community_plans WHERE state IN ('submitted','confirmed') ORDER BY created LIMIT 3"):
        try:reconcile(row['id'])
        except Exception:pass
    for row in s.rows("SELECT owner FROM creator_tokens WHERE state='live' ORDER BY verified LIMIT 3"):
        try:register_asset(row['owner']);refresh(row['owner'])
        except Exception:pass
