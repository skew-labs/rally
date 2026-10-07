"""Rally's owned social identity layer over nad.fun V2. Never signs or holds funds."""
import json, threading, time
from eth_abi import encode, decode
from eth_utils import keccak
import service as s
import nadfun as n
import venues as v

PIN_FILE=n.ROOT/'launch-vaults.json'
LABELS={'creator':'creatorFeeVault','burn':'burnVault','liquidity':'lpVault','gift':'giftVault'}
CONFIG_LOCK=threading.Lock(); CONFIG=None; CONFIG_AT=0

def initialize():
    with s.connection() as db:db.executescript('''
    CREATE TABLE IF NOT EXISTS launch_tokens(token TEXT PRIMARY KEY,owner TEXT NOT NULL,wallet TEXT NOT NULL,identity TEXT NOT NULL,community TEXT NOT NULL,allocations TEXT NOT NULL,creation_tx TEXT NOT NULL,block INTEGER NOT NULL,created INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS launch_owner ON launch_tokens(owner,created DESC);
    ''')
    with s.connection() as db:
        if 'beneficiary' not in {r[1] for r in db.execute('PRAGMA table_info(launch_tokens)')}:
            db.execute('ALTER TABLE launch_tokens ADD COLUMN beneficiary TEXT')

def beneficiary(value):
    if not isinstance(value,dict) or set(value)!={'platform','handle'} or value['platform'] not in {'X','GitHub'}:
        raise s.Problem('Choose an X or GitHub beneficiary')
    handle=str(value['handle']).strip().removeprefix('@')
    pattern=r'[A-Za-z0-9_]{1,15}' if value['platform']=='X' else r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?'
    if not s.re.fullmatch(pattern,handle) or value['platform']=='GitHub' and '--' in handle:
        raise s.Problem('Enter a valid beneficiary handle')
    return {'platform':value['platform'],'handle':handle.lower()}

def identity(user,ident=None):
    ident=ident or user
    row=s.one('SELECT id,kind,owner FROM accounts WHERE id=?',(ident,))
    if not row or not (ident==user or row['kind']=='agent' and row['owner']==user):
        raise s.Problem('Choose yourself or an agent you operate',403,'launch_identity_forbidden')
    return ident

def intent(who,data):
    user,wallet=v.wallet(who)
    ident=identity(user,data.get('identity'))
    supplied=data.get('allocations',{'creator':10000,'burn':0,'liquidity':0})
    if not isinstance(supplied,dict) or set(supplied) not in [set(LABELS),set(LABELS)-{'gift'}]:raise s.Problem('Choose creator, burn, liquidity and beneficiary allocations')
    if any(type(x) is not int or x<0 or x>10000 for x in supplied.values()) or sum(supplied.values())!=10000:
        raise s.Problem('Fee allocations must add up to 100%')
    policy={'identity':ident,'allocations':{k:supplied[k] for k in LABELS if k in supplied}}
    if supplied.get('gift'):
        policy['beneficiary']=beneficiary(data.get('beneficiary'))
    elif data.get('beneficiary'):raise s.Problem('Set a beneficiary fee share above zero')
    return policy

def pins():
    return json.loads(PIN_FILE.read_text())

def pin_allocations(allocations,block='latest'):
    values=pins()
    for key,bps in allocations.items():
        if not bps:continue
        p=values[LABELS[key]];target=p['address']
        if s.digest(s.rpc('eth_getCode',[target,block]).lower())!=p['codeHash']:
            raise s.Problem('Fee vault changed. Try again after review.',503,'launch_vault_changed')
        impl='0x'+s.rpc('eth_getStorageAt',[target,v.IMPL_SLOT,block])[-40:].lower()
        if impl!=p['implementation'] or s.digest(s.rpc('eth_getCode',[impl,block]).lower())!=p['implementationHash']:
            raise s.Problem('Fee vault implementation changed. Review required.',503,'launch_vault_changed')
    return s.digest(s.dump(values))

def vaults(allocations,wallet,beneficiary=None):
    values=pins()
    def setup(key):
        if key=='creator':return encode(['address'],[wallet])
        if key=='gift':
            b=globals()['beneficiary'](beneficiary)
            return encode(['(uint8,string)'],[(1 if b['platform']=='X' else 0,b['handle'])])
        return b''
    return [(values[LABELS[key]]['address'],bps,setup(key)) for key,bps in allocations.items() if bps]

def config():
    global CONFIG,CONFIG_AT
    with CONFIG_LOCK:
        if CONFIG is not None and time.monotonic()-CONFIG_AT<60:return CONFIG
        block=s.rpc('eth_getBlockByNumber',['finalized',False])
        if not block or not 0<=s.now()-int(block['timestamp'],16)<120:raise s.Problem('Fresh Monad state is unavailable',503)
        n.pin('v2',True);pin_allocations(dict.fromkeys(LABELS,1),block['number'])
        fee=n.creation_fee(block['number'])
        if s.rpc('eth_getBlockByNumber',[block['number'],False])['hash']!=block['hash']:raise s.Problem('Monad state changed. Refresh.',503)
        CONFIG={'chainId':143,'version':'v2','creationFeeMON':s.units(fee,18),'creatorFeeBps':100,'quoteAsset':'MON','initialBuy':'0','vaults':{k:pins()[label]['address'] for k,label in LABELS.items()},'fetchedAt':s.now(),'block':int(block['number'],16),'allocationCheck':'Full creation is simulated before a wallet request'};CONFIG_AT=time.monotonic()
        return CONFIG

def background():
    # Warm the shared fee snapshot without placing discovery behind RPC latency.
    while True:
        try:config();repair_connections()
        except Exception:pass
        time.sleep(60)

def creator(ident):
    p=s.one('SELECT id,handle,name,kind,owner,avatar FROM accounts WHERE id=?',(ident,))
    if p and p['owner']:p['operator']=s.one('SELECT id,handle,name FROM accounts WHERE id=?',(p['owner'],))
    return p

def binding(row):
    cached=s.one('SELECT info FROM nad_tokens WHERE address=?',(row['token'],));t=json.loads(cached['info']) if cached else {}
    return {'token':row['token'],'name':t.get('name'),'symbol':t.get('symbol'),'logoURI':t.get('logoURI'),'creator':creator(row['identity']),'community':row['community'],'allocations':json.loads(row['allocations']),'beneficiary':json.loads(row.get('beneficiary') or 'null'),'creationTx':row['creation_tx'],'verifiedBlock':row['block'],'created':row['created'],'source':'finalized nad.fun V2 creation'}

def owned(ident):
    return [binding(x) for x in s.rows('SELECT * FROM launch_tokens WHERE identity=? ORDER BY created DESC LIMIT 50',(ident,))]

def me(who):
    user=s.require(who,human=True)
    return {'identities':[creator(p['id']) for p in s.rows("SELECT id FROM accounts WHERE id=? OR kind='agent' AND owner=? ORDER BY kind DESC,created LIMIT 100",(user,user))],'tokens':[binding(x) for x in s.rows('SELECT * FROM launch_tokens WHERE owner=? ORDER BY created DESC LIMIT 50',(user,))]}

def catalog(who=None,params=None):
    import social,community_tokens
    viewer=who['user'] if who else None
    params=params or {}
    data=n.catalog(sort=params.get('sort','latest'),query=params.get('query',''),cursor=params.get('cursor',''),limit=params.get('limit',100));tokens=data['tokens'];bound={x['token']:x for x in s.rows('SELECT * FROM launch_tokens ORDER BY created DESC LIMIT 500')}
    present={t['id'] for t in tokens}
    # Include registered launches even when they fall outside nad.fun's latest page.
    for token in bound:
        if not params.get('cursor') and token not in present:
            cached=s.one('SELECT info FROM nad_tokens WHERE address=?',(token,))
            if cached:tokens.append(n.public_info(json.loads(cached['info'])))
    for t in tokens:t['launch']=binding(bound[t['id']]) if t['id'] in bound and social.visible(viewer,bound[t['id']]['identity']) else None
    existing=[community_tokens.public(x['owner']) for x in s.rows('SELECT owner FROM creator_tokens WHERE state=? LIMIT 50',('live',))] if s.one("SELECT name FROM sqlite_master WHERE type='table' AND name='creator_tokens'") else []
    import token_images
    token_images.decorate(tokens)
    return {**data,'tokens':tokens,'communityTokens':[{**t,'creatorProfile':creator(t['owner'])} for t in existing if t and social.visible(viewer,t['owner'])]}

def detail(token,who=None):
    import social
    token=n.address(token);row=s.one('SELECT * FROM launch_tokens WHERE token=?',(token,))
    if not row or not social.visible(who['user'] if who else None,row['identity']):return {'launch':None}
    item=binding(row)
    item['algorithms']=[{'id':f['id'],'name':f['name'],'owner':f['owner']} for f in s.rows('SELECT id,name,owner FROM feeds WHERE owner=? ORDER BY created DESC LIMIT 20',(row['owner'],))]
    return {'launch':item}

def attach(user,wallet,token,tx,block,created,policy):
    identity(user,policy.get('identity'))
    ident=policy.get('identity',user);community='launch_'+token[2:]
    info=s.one('SELECT info FROM nad_tokens WHERE address=?',(token,))
    if not info:raise s.Problem('Token metadata is still indexing. Register again shortly.',409)
    t=json.loads(info['info'])
    with s.connection() as db:
        prior=db.execute('SELECT * FROM launch_tokens WHERE token=?',(token,)).fetchone()
        if prior:
            if prior['owner']!=user or prior['wallet']!=wallet:raise s.Problem('This token is already registered',409)
            return binding(dict(prior))
        db.execute('INSERT INTO launch_tokens(token,owner,wallet,identity,community,allocations,creation_tx,block,created,beneficiary) VALUES(?,?,?,?,?,?,?,?,?,?)',(token,user,wallet,ident,community,s.dump(policy['allocations']),tx,block,created,s.dump(policy.get('beneficiary'))))
        db.execute('INSERT OR IGNORE INTO communities VALUES(?,?,?)',(community,t['name'],t['symbol']+' on Monad'))
        db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(user,community))
    return detail(token)['launch']

def creation_proof(token,wallet):
    """Read the actual create calldata, Create log and canonical finalized receipt."""
    n.pin('v2',True);info=n.token_info(token);block=s.rpc('eth_getBlockByNumber',['finalized',False])
    live=n.state('v2',token,block['number'])
    if live['creator'].lower()!=wallet:raise s.Problem('This wallet did not create the token',403,'launch_owner_mismatch')
    if live['createdBlock']>int(block['number'],16):raise s.Problem('Wait for the launch to finalize',409)
    height=hex(live['createdBlock']);curve=n.contract('v2','curve')
    logs=s.rpc('eth_getLogs',[{'address':curve,'fromBlock':height,'toBlock':height}]);matched=[]
    for log in logs:
        if log.get('removed'):continue
        ev=n.event('v2','curve',log)
        if ev and ev['name']=='Create' and ev['fields'].get('token')==token:matched.append(log)
    if len(matched)!=1:raise s.Problem('Could not verify the token creation receipt',409)
    log=matched[0];tx=s.rpc('eth_getTransactionByHash',[log['transactionHash']]);receipt=s.rpc('eth_getTransactionReceipt',[log['transactionHash']]);canonical=s.rpc('eth_getBlockByNumber',[height,False])
    if not receipt or int(receipt['status'],16)!=1 or receipt['blockHash'].lower()!=canonical['hash'].lower() or log['blockHash'].lower()!=canonical['hash'].lower() or tx['blockHash'].lower()!=canonical['hash'].lower():raise s.Problem('Token creation is not canonical',409)
    label='router' if str(tx.get('to','')).lower()==n.contract('v2','router') else 'curve' if str(tx.get('to','')).lower()==curve else None
    if not label:raise s.Problem('This launch route cannot be imported yet',409)
    raw=tx.get('input','');method=next((f for f in n.abi('v2',label) if f.get('type')=='function' and f['name'] in {'create','createWithNative'} and raw[:10]=='0x'+keccak(text=f['name']+'('+','.join(v.typ(x) for x in f['inputs'])+')').hex()[:8]),None)
    if not method:raise s.Problem('Could not verify the creation fee routing',409)
    params=v.named(method['inputs'][0],decode([v.typ(method['inputs'][0])],bytes.fromhex(raw[10:]))[0])
    event=n.event('v2','curve',log)['fields']
    if any(params.get(k)!=event.get(k) for k in ['name','symbol','tokenURI','quoteToken']) or params.get('creatorFeeRate')!=live['creatorFeeBps'] or tx['from'].lower()!=wallet:raise s.Problem('Creation metadata does not match the token',409)
    allocations=dict.fromkeys(LABELS,0);values=pins();gift=None
    seen=set()
    for entry in params['vaults']:
        key=next((k for k,label in LABELS.items() if entry['vault'].lower()==values[label]['address']),None)
        if not key or key in seen or type(entry['bps']) is not int or not 0<entry['bps']<=10000:raise s.Problem('This fee routing is not supported for import yet',409)
        seen.add(key)
        if key=='gift':
            platform,handle=decode(['(uint8,string)'],bytes.fromhex(entry['setupData'][2:]))[0]
            if platform not in {0,1}:raise s.Problem('Unsupported beneficiary platform',409)
            gift=beneficiary({'platform':'X' if platform==1 else 'GitHub','handle':handle})
        elif key=='creator' and decode(['address'],bytes.fromhex(entry['setupData'][2:]))[0]!=wallet or key not in {'creator','gift'} and entry['setupData']!='0x':raise s.Problem('Fee beneficiary does not match this wallet',403)
        allocations[key]=entry['bps']
    if sum(allocations.values())!=10000:raise s.Problem('Fee allocations are incomplete',409)
    pin_allocations(allocations,block['number'])
    return {'allocations':allocations,'beneficiary':gift,'tx':tx['hash'],'block':live['createdBlock'],'created':int(canonical['timestamp'],16)}

def register(who,data):
    user,wallet=v.wallet(who);ident=identity(user,data.get('identity'));token=n.address(data.get('token'))
    proof=creation_proof(token,wallet)
    return attach(user,wallet,token,proof['tx'],proof['block'],proof['created'],{'identity':ident,'allocations':proof['allocations'],'beneficiary':proof['beneficiary']})

def finalized(row,p,outcome,receipt,block):
    d=s.one('SELECT payload FROM nad_drafts WHERE id=? AND user_id=?',(p['args']['draft'],row['user_id']))
    if not d:return
    draft=json.loads(d['payload']);policy=draft['intent'].get('launch')
    if not policy:return
    # The generic recorder has already verified the exact tx input/value and
    # reconcile independently confirmed the Create event and contract identity.
    attach(row['user_id'],p['transaction']['from'],outcome['createdToken'],row['tx'],int(receipt['blockNumber'],16),int(block['timestamp'],16),policy)

def repair_connections():
    for row in s.rows("SELECT r.*,p.payload FROM execution_records r JOIN execution_plans p ON p.id=r.plan WHERE r.state='finalized' AND p.venue='nadfun' AND p.kind='create' AND json_extract(r.outcome,'$.socialConnection')='pending_registration' LIMIT 3"):
        try:
            outcome=json.loads(row['outcome']);receipt=outcome['receipt'];p=json.loads(row['payload'])
            if outcome.get('businessState')!='token_created':continue
            block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
            if not block or block['hash'].lower()!=receipt['blockHash'].lower():continue
            n.token_info(outcome['createdToken'],False)
            finalized(row,p,outcome,receipt,block)
            if s.one('SELECT 1 FROM launch_tokens WHERE token=?',(outcome['createdToken'],)):
                outcome.pop('socialConnection',None)
                s.write('UPDATE execution_records SET outcome=? WHERE id=? AND state=?',(s.dump(outcome),row['id'],'finalized'))
        except Exception:pass
