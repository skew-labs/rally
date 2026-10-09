"""Wallet-approved venue transactions built from official ABIs; no server signer."""
import json,threading,time
from decimal import Decimal,localcontext
from eth_abi import encode,decode
from eth_utils import keccak
import service as s
import transaction_preflight
import wallet_execution

PERPL='0x34b6552d57a35a1d042ccae1951bd1c370112a6f'
CASTORA='0x9e1e6f277df3f2cd150ae1e08b05f45b3297be6d'
# Castora's prediction references are oracle identifiers, not spendable tokens.
# Pinned against its official frontend/src/schemas/tokens.ts and
# server/shared/src/utils/contract.ts. They must never enter token_map.
PREDICTION_REFERENCES={
    'MON':{'symbol':'MON','name':'Monad','logoURI':'/assets/MON.png','chartMarket':10},
    '0x294c2647d9f3eaca43a364859c6e6a1e0e582dbd':{'symbol':'ETH','name':'Ethereum','logoURI':'/assets/ETH.png','chartMarket':20},
    '0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac6':{'symbol':'BTC','name':'Bitcoin','logoURI':'/assets/BTC.png','chartMarket':1},
    '0xd31a59c85ae9d8edefec411d448f90841571b89c':{'symbol':'SOL','name':'Solana','logoURI':'/assets/SOL.png','chartMarket':31},
}

def prediction_reference(asset):
    return PREDICTION_REFERENCES.get(asset) or s.GATEWAY.token_map.get(asset)
AUSD='0x00000000efe302beaa2b3e6e1b18d08d69a9012a'
GETTERS='0xf08959e66614027ae76303f4c5359ebffd00bc30'
ROOT=s.ROOT/'config/venues'
IMPL_SLOT='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
ABIS={};POOL_CACHE=None;POOL_AT=0;POOL_LOCK=threading.Lock()
REQUEST_LOCK=threading.Lock();LAST_REQUEST=0

def request_id():
    global LAST_REQUEST
    with REQUEST_LOCK:
        # Official SDK default: unsigned 64-bit Unix milliseconds.
        LAST_REQUEST=max(time.time_ns()//1000000,LAST_REQUEST+1)
        return LAST_REQUEST

def initialize():
    with s.connection() as db:db.executescript('''
    CREATE TABLE IF NOT EXISTS execution_plans(id TEXT PRIMARY KEY,user_id TEXT,wallet TEXT,venue TEXT,kind TEXT,payload TEXT,expires INTEGER);
    CREATE TABLE IF NOT EXISTS execution_records(id TEXT PRIMARY KEY,user_id TEXT,plan TEXT UNIQUE,tx TEXT UNIQUE,state TEXT,outcome TEXT,created INTEGER);
    ''')

def abi(venue):
    if venue not in ABIS:ABIS[venue]=json.loads((ROOT/({'perpl':'perpl-abi.json','castora':'castoraAbi.json','getters':'castoraGettersAbi.json'}[venue])).read_text())
    return ABIS[venue]

def typ(item):
    return '('+','.join(typ(c) for c in item['components'])+')'+item['type'][5:] if item['type'].startswith('tuple') else item['type']

def function(venue,name):return next(f for f in abi(venue) if f.get('type')=='function' and f.get('name')==name)
def call_data(venue,name,args=()):
    f=function(venue,name);types=[typ(x) for x in f['inputs']]
    return '0x'+keccak(text=name+'('+','.join(types)+')').hex()[:8]+encode(types,list(args)).hex()

def named(item,value):
    if item['type']=='tuple':return {c['name'] or str(i):named(c,v) for i,(c,v) in enumerate(zip(item['components'],value))}
    if item['type']=='tuple[]':return [named({**item,'type':'tuple'},v) for v in value]
    if isinstance(value,bytes):return '0x'+value.hex()
    if isinstance(value,tuple):return list(value)
    return value

def read(venue,name,args=(),wallet=None,allow_missing=False,block='latest'):
    tx={'to':{'perpl':PERPL,'castora':CASTORA,'getters':GETTERS}[venue],'data':call_data(venue,name,args)}
    if wallet:tx['from']=wallet
    response=s.rpc_response('eth_call',[tx,block])
    if response.get('error'):
        error=response['error'];missing='0x03a0e277'+str(args[0])[2:].lower().rjust(64,'0') if allow_missing else None
        if allow_missing and venue=='perpl' and name=='getAccountByAddr' and error.get('code')==3 and str(error.get('data','')).lower()==missing:return None
        raise s.Problem('The venue could not complete this read. Try again.',502,'venue_read_failed')
    result=response.get('result');outs=function(venue,name)['outputs']
    try:values=decode([typ(o) for o in outs],bytes.fromhex(result[2:]))
    except Exception:raise s.Problem('Venue contract interface changed. Review required.',503,'venue_interface_changed')
    return named(outs[0],values[0]) if len(outs)==1 else {o['name'] or str(i):named(o,v) for i,(o,v) in enumerate(zip(outs,values))}

def pin(venue):
    manifest=json.loads((ROOT/'contract-pins.json').read_text())[venue]
    if manifest['abiHash']!=s.digest(s.dump(abi(venue))):raise s.Problem('Venue interface changed. Review required.',503,'venue_contract_changed')
    address=PERPL if venue=='perpl' else CASTORA
    proxy=s.rpc('eth_getCode',[address,'latest'])
    slot=s.rpc('eth_getStorageAt',[address,IMPL_SLOT,'latest'])
    implementation='0x'+slot[-40:].lower()
    implementation_code=s.rpc('eth_getCode',[implementation,'latest']) if implementation!=s.ZERO else proxy
    current={'address':address,'proxyHash':s.digest(proxy.lower()),'implementation':implementation,'implementationHash':s.digest(implementation_code.lower())}
    if any(current[k]!=manifest[k] for k in current):raise s.Problem('Venue contract changed. Review required.',503,'venue_contract_changed')
    return current

def raw(value,decimals,maximum='1000000000'):
    try:
        if len(str(value))>80:raise ValueError()
        with localcontext() as ctx:
            ctx.prec=96;amount=Decimal(str(value));scaled=amount*10**decimals
            if not amount.is_finite() or amount<=0 or amount>Decimal(maximum) or scaled!=int(scaled):raise ValueError()
            return int(scaled)
    except Exception:raise s.Problem('Enter a positive amount with valid precision')

def wallet(who):
    user=s.require(who,human=True);address=(s.one('SELECT wallet FROM accounts WHERE id=?',(user,)) or {}).get('wallet')
    if not address:raise s.Problem('Connect your wallet first',409,'wallet_required')
    return user,address

def perpl_status(who):
    _,address=wallet(who);info=read('perpl','getExchangeInfo');minimum=read('perpl','getMinAccountOpenCNS')
    if info['collateralToken'].lower()!=AUSD or info['collateralDecimals']!=6:raise s.Problem('Collateral configuration changed',503)
    account=read('perpl','getAccountByAddr',[address],address,allow_missing=True)
    if account and account['accountAddr'].lower()!=address:raise s.Problem('Exchange account identity mismatch',503)
    return {'wallet':address,'exchange':PERPL,'collateral':AUSD,'collateralSymbol':'AUSD','minimumDeposit':s.units(minimum,6),'account':account,'balance':s.units(account['balanceCNS'],6) if account else '0','locked':s.units(account['lockedBalanceCNS'],6) if account else '0','available':s.units(account['balanceCNS']-account['lockedBalanceCNS'],6) if account else '0','chainId':143,'execution':'wallet_transactions'}

def plan(who,data):
    if data.get('venue')=='wallet':return __import__('wallet_transfer').plan(who,data)
    if data.get('venue') in {'nadfees','nadrevenue'}:
        return __import__('launch_fees' if data['venue']=='nadfees' else 'nad_revenue').plan(who,data)
    if data.get('venue') in {'drake','pingu'}:
        module=__import__(data['venue'])
        return module.plan(who,data)
    if data.get('venue')=='leverup':
        import leverup
        return leverup.plan(who,data)
    if data.get('venue')=='nadfun':
        import nadfun
        return nadfun.plan(who,data)
    user,address=wallet(who);venue=data.get('venue');kind=data.get('kind');approval=None
    if venue not in {'perpl','castora'}:raise s.Problem('Unsupported venue')
    contract_pin=pin(venue);target=PERPL if venue=='perpl' else CASTORA;value=0
    if venue=='perpl':
        status=perpl_status(who)
        if kind in {'deposit','withdraw'}:
            amount=raw(data.get('amount'),6)
            if kind=='deposit':
                if not status['account'] and amount<raw(status['minimumDeposit'],6):raise s.Problem('Minimum opening deposit is '+status['minimumDeposit']+' AUSD')
                method='depositCollateral' if status['account'] else 'createAccount'
                approval={'token':AUSD,'spender':PERPL,'amountRaw':str(amount)}
            else:
                if not status['account'] or amount>status['account']['balanceCNS']-status['account']['lockedBalanceCNS']:raise s.Problem('Not enough available exchange collateral',409)
                method='withdrawCollateral'
            calldata=call_data(venue,method,[amount]);summary={'action':kind,'amount':s.units(amount,6),'asset':'AUSD','accountId':status['account']['accountId'] if status['account'] else None}
        elif kind=='order':
            if not status['account']:raise s.Problem('Deposit AUSD to open your Perpl account first',409,'perpl_account_required')
            if status['account']['frozen']:raise s.Problem('This exchange account is frozen',409)
            s.GATEWAY.perpl_markets();m=next((m for m in s.GATEWAY.perpl['markets'] if str(m['id'])==str(data.get('market'))),None)
            if not m or not m['config']['is_open']:raise s.Problem('Market is not open',409)
            config=read(venue,'getPerpetualInfo',[m['perpetual_id']]);direction=data.get('direction','long');reduce=data.get('reduceOnly',False)
            if config['status']!=4 or config['priceDecimals']!=m['config']['price_decimals'] or config['lotDecimals']!=m['config']['size_decimals']:raise s.Problem('Market configuration changed. Refresh markets.',409)
            if direction not in {'long','short'} or not isinstance(reduce,bool):raise s.Problem('Invalid order direction')
            quantity=raw(data.get('quantity'),config['lotDecimals']);limit=raw(data.get('limit'),config['priceDecimals']);leverage=int(data.get('leverage',1))
            if not 1<=leverage<=5:raise s.Problem('Choose leverage from 1x to 5x')
            order_type=(3 if direction=='long' else 2) if reduce else (0 if direction=='long' else 1)
            head=int(s.rpc('eth_blockNumber',[]),16)
            desc=(request_id(),m['perpetual_id'],order_type,0,limit,quantity,head+1000,False,False,True,20,leverage*100,head+500,0,100)
            calldata=call_data(venue,'execOrders',[[desc],True]);summary={'action':'order','market':m['name'],'marketId':m['id'],'perpetualId':m['perpetual_id'],'direction':direction,'reduceOnly':reduce,'quantity':s.units(quantity,config['lotDecimals']),'limit':s.units(limit,config['priceDecimals']),'priceDecimals':config['priceDecimals'],'lotDecimals':config['lotDecimals'],'leverage':leverage,'timeInForce':'IOC','accountId':status['account']['accountId'],'requestId':str(desc[0])}
        else:raise s.Problem('Unsupported Perpl action')
    else:
        if kind not in {'predict','claim'}:raise s.Problem('Unsupported prediction action')
        pool_id=int(data.get('pool',0));pool=read(venue,'getPool',[pool_id]);seeds=pool['seeds']
        if pool['poolId']!=pool_id or not pool_id:raise s.Problem('Prediction pool not found',404)
        if kind=='predict':
            if seeds['windowCloseTime']<=s.now() or pool['completionTime'] or seeds['isUnlisted']:raise s.Problem('This pool is closed',409)
            prediction_asset=prediction_reference('MON' if seeds['predictionToken'].lower()==CASTORA else seeds['predictionToken'].lower())
            if not prediction_asset:raise s.Problem('Prediction asset has not been reviewed',409)
            prediction=raw(data.get('price'),8)
            native=seeds['stakeToken'].lower()==CASTORA
            t=s.GATEWAY.token_map.get('MON' if native else seeds['stakeToken'].lower())
            if not t:raise s.Problem('Stake token has not been reviewed',409)
            amount=seeds['stakeAmount'];value=amount if native else 0
            if not native:approval={'token':t['address'].lower(),'spender':CASTORA,'amountRaw':str(amount)}
            calldata=call_data(venue,'predict',[pool_id,prediction]);summary={'action':'predict','pool':pool_id,'predictionPrice':s.units(prediction,8),'stake':s.units(amount,t['decimals']),'asset':t['symbol'],'feeBps':seeds['feesPercent'],'snapshotTime':seeds['snapshotTime'],'multiplier':seeds['multiplier']}
        else:
            prediction_id=int(data.get('prediction',0));p=read(venue,'predictions',[pool_id,prediction_id])
            if p['predicter'].lower()!=address or not p['isAWinner'] or p['claimedWinningsTime'] or not pool['completionTime']:raise s.Problem('No claimable payout for this prediction',409)
            calldata=call_data(venue,'claimWinnings',[pool_id,prediction_id]);summary={'action':'claim','pool':pool_id,'prediction':prediction_id}
    ident=s.uid();payload={'summary':summary,'transaction':{'from':address,'to':target,'data':calldata,'value':hex(value),'chainId':'0x8f'},'approval':approval,'pin':contract_pin,'args':data,'created':s.now(),'expires':s.now()+90}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,address,venue,kind,s.dump(payload),payload['expires']))
    return {'id':ident,**payload}

def owned(who,ident):
    user,address=wallet(who);row=s.one('SELECT * FROM execution_plans WHERE id=? AND user_id=?',(ident,user))
    if not row:raise s.Problem('Execution plan not found',404)
    if row['wallet']!=address:raise s.Problem('Connected wallet changed',409)
    return row,json.loads(row['payload'])

def prepare(who,data):
    row,p=owned(who,data.get('plan'))
    if row['expires']<=s.now():raise s.Problem('Review expired. Get a fresh plan.',409)
    if s.one('SELECT 1 FROM execution_records WHERE plan=?',(row['id'],)):raise s.Problem('This plan already has a submitted transaction',409)
    if row['venue']=='wallet':__import__('wallet_transfer').prepare(row,p)
    elif row['venue']=='nadfun':
        import nadfun
        nadfun.prepare(row,p)
    elif row['venue'] in {'nadfees','nadrevenue'}:
        __import__('launch_fees' if row['venue']=='nadfees' else 'nad_revenue').prepare(row,p)
    elif row['venue']=='leverup':
        import leverup
        leverup.prepare(row,p)
    elif row['venue'] in {'drake','pingu'}:__import__(row['venue']).prepare(row,p)
    else:pin(row['venue'])
    approval=p['approval']
    if approval:
        balance=int(s.rpc('eth_call',[{'to':approval['token'],'data':'0x70a08231'+row['wallet'][2:].rjust(64,'0')},'latest']),16)
        if balance<int(approval['amountRaw']):raise s.Problem('Not enough '+p['summary'].get('inputAsset',p['summary']['asset'])+' in this wallet',409,'insufficient_balance')
        allowance=int(s.rpc('eth_call',[{'to':approval['token'],'data':'0xdd62ed3e'+row['wallet'][2:].rjust(64,'0')+approval['spender'][2:].rjust(64,'0')},'latest']),16)
        if allowance<int(approval['amountRaw']):
            tx=transaction_preflight.funded({'from':row['wallet'],'to':approval['token'],'value':'0x0','chainId':'0x8f','data':'0x095ea7b3'+approval['spender'][2:].rjust(64,'0')+hex(int(approval['amountRaw']))[2:].rjust(64,'0')},150)
            if row['expires']<=s.now():raise s.Problem('Review expired. Get a fresh plan.',409)
            return {'approval':tx,'spender':approval['spender'],'amountRaw':approval['amountRaw']}
    tx=p['transaction']
    deploying=row['venue']=='nadrevenue' and row['kind']=='revenue_deploy'
    tx=transaction_preflight.funded(tx,110 if deploying else 120 if row['venue']=='nadfees' else 150)
    if deploying:
        price=int(s.rpc('eth_gasPrice',[]),16)
        if int(tx['gas'],16)*price>__import__('nad_revenue').GAS_CAP:raise s.Problem('Vault activation exceeds the 0.3 MON gas cap',409)
        tx['gasPrice']=hex(price)
    if row['venue']=='nadfun' and row['kind']=='create':nadfun.simulate_creation(p)
    expires=min(row['expires'],p['expires'])
    if expires<=s.now():raise s.Problem('Review expired. Get a fresh plan.',409)
    return {'transaction':tx,'expires':expires,'summary':p['summary']}

def record(who,data):
    row,p=owned(who,data.get('plan'));txhash=str(data.get('tx','')).lower()
    if not s.re.fullmatch(r'0x[0-9a-f]{64}',txhash):raise s.Problem('Invalid transaction hash')
    prior=s.one('SELECT * FROM execution_records WHERE plan=? OR tx=?',(row['id'],txhash))
    if prior:
        if prior['plan']!=row['id'] or prior['tx']!=txhash:raise s.Problem('Transaction already recorded',409)
        return prior
    tx=s.rpc('eth_getTransactionByHash',[txhash]);expected=p['transaction']
    if not tx:raise s.Problem('Transaction not indexed yet. Retry the same hash.',409,'transaction_pending')
    wallet_execution.verified_call(txhash,{**expected,'from':row['wallet']},tx)
    if row['venue']=='nadrevenue':__import__('nad_revenue').transaction_check(p,tx)
    ident=s.uid()
    try:s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',(ident,row['user_id'],row['id'],txhash,'submitted',None,s.now()))
    except s.sqlite3.IntegrityError:raise s.Problem('Transaction already recorded',409)
    return {'id':ident,'tx':txhash,'state':'submitted'}

def check_approval(who,data):
    row,p=owned(who,data.get('plan'));approval=p['approval'];txhash=str(data.get('tx','')).lower()
    if not approval or not s.re.fullmatch(r'0x[0-9a-f]{64}',txhash):raise s.Problem('Invalid approval reference')
    tx=s.rpc('eth_getTransactionByHash',[txhash])
    if not tx:return {'state':'pending'}
    try:receipt=wallet_execution.approval_receipt(txhash,row['wallet'],approval['token'],approval['spender'],approval['amountRaw'],tx)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending'}
        raise
    return {'state':'approved' if int(receipt['status'],16)==1 else 'failed','receipt':receipt}

def predictions():
    global POOL_CACHE,POOL_AT
    with POOL_LOCK:
        if POOL_CACHE is not None and time.monotonic()-POOL_AT<30:return prediction_view(POOL_CACHE)
        # Coalesced public catalog refresh; bounded 50-pool batches preserve
        # exact pool IDs and share the Monad RPC request budget.
        if read('getters','castora').lower()!=CASTORA:raise s.Problem('Prediction reader changed. Review required.',503,'venue_interface_changed')
        stats=read('castora','allStats');count=stats['noOfPools'];pools=[]
        ids=list(range(count,max(0,count-400),-1))
        records=[]
        for offset in range(0,len(ids),50):records.extend(read('getters','pools',[ids[offset:offset+50]]))
        if len(records)!=len(ids) or any(p['poolId']!=ident for ident,p in zip(ids,records)):
            raise s.Problem('Prediction reader changed. Review required.',503,'venue_interface_changed')
        for ident,p in zip(ids,records):
            seed=p['seeds']
            if seed['isUnlisted']:continue
            stake_id='MON' if seed['stakeToken'].lower()==CASTORA else seed['stakeToken'].lower()
            asset_id='MON' if seed['predictionToken'].lower()==CASTORA else seed['predictionToken'].lower()
            stake=s.GATEWAY.token_map.get(stake_id);asset=prediction_reference(asset_id)
            pools.append({'id':ident,'assetId':asset_id,'asset':asset['symbol'] if asset else seed['predictionToken'],'predictionReviewed':bool(asset),'assetInfo':dict(asset,kind='price_reference') if asset_id in PREDICTION_REFERENCES else None,'stake':s.units(seed['stakeAmount'],stake['decimals']) if stake else None,'stakeAssetId':stake_id,'stakeAsset':stake['symbol'] if stake else seed['stakeToken'],'stakeReviewed':bool(stake),'close':seed['windowCloseTime'],'snapshot':seed['snapshotTime'],'feeBps':seed['feesPercent'],'multiplier':seed['multiplier'],'predictions':p['noOfPredictions'],'settlementPrice':s.units(p['snapshotPrice'],8) if p['completionTime'] else None,'completedAt':p['completionTime'],'winners':p['noOfWinners'],'state':'settled' if p['completionTime'] else 'open' if seed['windowCloseTime']>s.now() else 'awaiting_settlement'})
        POOL_CACHE={'venue':'Castora','chainId':143,'contract':CASTORA,'pools':pools,'totalPools':count,'scannedPools':len(ids),'scope':'all' if len(ids)==count else 'latest_400','fetchedAt':s.now(),'model':'staked_price_predictions'};POOL_AT=time.monotonic();return prediction_view(POOL_CACHE)

def prediction_view(data):
    # A pool can close during the cache window. Never return a cached open state
    # past its deadline, and do not mutate the shared catalog for another reader.
    return {**data,'pools':[{**p,'state':p['state'] if p['state']=='settled' else 'open' if p['close']>s.now() else 'awaiting_settlement'} for p in data['pools']]}

def history(who):
    user=s.require(who,human=True)
    records=s.rows('SELECT r.*,p.venue,p.kind,p.payload FROM execution_records r JOIN execution_plans p ON r.plan=p.id WHERE r.user_id=? ORDER BY r.created DESC LIMIT 50',(user,))
    for record in records:
        record['summary']=json.loads(record.pop('payload'))['summary']
        record['outcome']=json.loads(record['outcome']) if record['outcome'] else None
    return {'transactions':records}

def my_predictions(who,offset=0):
    _,address=wallet(who);offset=max(0,min(int(offset),10000))
    records=read('getters','userPredictionRecordsPaginated',[address,offset,10]);items=[]
    for record in records:
        prediction=read('castora','predictions',[record['poolId'],record['predictionId']])
        if prediction['predicter'].lower()!=address:raise s.Problem('Prediction ownership mismatch',502)
        items.append({**record,'price':s.units(prediction['predictionPrice'],8),'winner':prediction['isAWinner'],'claimed':bool(prediction['claimedWinningsTime']),'created':prediction['predictionTime']})
    return {'predictions':items,'nextOffset':offset+10 if len(records)==10 else None,'wallet':address}

def reconcile(ident):
    row=s.one('SELECT r.*,p.venue,p.kind,p.payload,p.wallet FROM execution_records r JOIN execution_plans p ON r.plan=p.id WHERE r.id=?',(ident,))
    if row and row['venue'] in {'nadfees','nadrevenue'}:
        if row['state'] not in {'finalized','failed','invalid'}:
            return __import__('launch_fees' if row['venue']=='nadfees' else 'nad_revenue').reconcile(row)
        return
    if row and row['venue']=='leverup':
        import leverup
        return leverup.reconcile(row)
    if row and row['venue']=='pingu':return __import__('pingu').reconcile(row)
    if not row or row['state'] in {'finalized','failed','invalid'}:return
    if row['venue']=='drake':return __import__('drake').reconcile(row)
    if row['venue']=='nadfun':
        import nadfun
        return nadfun.reconcile(row)
    receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not block or block.get('hash','').lower()!=receipt.get('blockHash','').lower():return
    payload=json.loads(row['payload'])
    if int(block['timestamp'],16)<payload['created']-5:
        s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',('invalid',s.dump({'businessState':'outside_review_window','receipt':receipt}),ident));return
    if int(receipt['status'],16)!=1:state='failed'
    else:
        final=s.rpc('eth_getBlockByNumber',['finalized',False]);state='finalized' if final and int(final['number'],16)>=int(receipt['blockNumber'],16) else 'confirmed'
    outcome={'receipt':receipt,'businessState':'check_venue_result','events':[],'reviewExpiredAtInclusion':int(block['timestamp'],16)>payload['expires']}
    if row['venue']=='wallet':
        outcome.update(__import__('wallet_transfer').outcome(payload,receipt))
        if state=='finalized' and outcome.get('businessState')=='sent':
            __import__('wallet_assets').invalidate(row['wallet'],int(receipt['blockNumber'],16))
        s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(outcome),ident))
        return
    address=PERPL if row['venue']=='perpl' else CASTORA
    for log in receipt.get('logs',[]):
        if log.get('removed') or (log.get('address') or '').lower()!=address or not log.get('topics'):continue
        for event in (e for e in abi(row['venue']) if e['type']=='event' and not e.get('anonymous')):
            signature=event['name']+'('+','.join(typ(x) for x in event['inputs'])+')'
            if log['topics'][0].lower()!='0x'+keccak(text=signature).hex():continue
            try:
                indexed=[x for x in event['inputs'] if x.get('indexed')];plain=[x for x in event['inputs'] if not x.get('indexed')]
                if len(log['topics'])!=1+len(indexed):continue
                values=decode([typ(x) for x in plain],bytes.fromhex(log['data'][2:]))
                if encode([typ(x) for x in plain],values).hex()!=log['data'][2:].lower():continue
                fields={x['name']:named(x,v) for x,v in zip(plain,values)}
                for x,t in zip(indexed,log['topics'][1:]):fields[x['name']]=named(x,decode([typ(x)],bytes.fromhex(t[2:]))[0])
                outcome['events'].append({'name':event['name'],'fields':fields})
            except Exception:pass
    summary=payload['summary'];events=outcome['events']
    if state=='failed':outcome['businessState']='reverted'
    elif row['venue']=='perpl' and summary['action']=='order':
        active=False;fills=[];ioc=[]
        for event in events:
            fields=event['fields']
            if event['name'] in {'OrderRequest','OrderRequestV2'}:
                active=fields['accountId']==summary['accountId'] and fields['perpId']==summary['perpetualId'] and str(fields['orderDescId'])==summary['requestId']
            elif active and event['name'] in {'TakerOrderFilled','TakerOrderFilledV2'}:fills.append(fields)
            elif active and event['name']=='ImmediateOrCancelExecuted':ioc.append(fields)
        lots=sum(f['lotLNS'] for f in fills);requested=raw(summary['quantity'],summary['lotDecimals'])
        if lots and lots<=requested:
            with localcontext() as ctx:
                ctx.prec=96;entry=Decimal(sum(f['entryPricePNS']*f['lotLNS'] for f in fills))/lots/(10**summary['priceDecimals'])
            outcome.update(businessState='filled' if lots==requested else 'partial_fill',fillQuantity=s.units(lots,summary['lotDecimals']),entryPrice=format(entry,'f'),feeAUSD=s.units(sum(f['feeCNS'] for f in fills),6))
        elif not lots and len(ioc)==1 and ioc[0]['totalLotLNS']==requested and ioc[0]['unmatchedLotLNS']==requested:outcome['businessState']='unfilled'
        else:outcome['businessState']='venue_result_pending'
    elif row['venue']=='perpl':
        event_name='CollateralDeposit' if summary['action']=='deposit' else 'CollateralWithdrawal'
        account=read('perpl','getAccountByAddr',[row['wallet']],row['wallet'],allow_missing=True,block=receipt['blockNumber'])
        account_id=account.get('accountId') if account and account['accountAddr'].lower()==row['wallet'] else None
        matches=[e for e in events if e['name']==event_name and e['fields']['amountCNS']==raw(summary['amount'],6) and e['fields']['accountId']==account_id and (summary.get('accountId') is None or summary['accountId']==account_id)]
        sender,recipient=(row['wallet'],PERPL) if summary['action']=='deposit' else (PERPL,row['wallet'])
        transfers=[log for log in receipt.get('logs',[]) if not log.get('removed') and (log.get('address') or '').lower()==AUSD and len(log.get('topics',[]))==3 and log['topics'][0].lower()=='0x'+keccak(text='Transfer(address,address,uint256)').hex() and '0x'+log['topics'][1][-40:].lower()==sender and '0x'+log['topics'][2][-40:].lower()==recipient and int(log.get('data','0x0'),16)==raw(summary['amount'],6)]
        if len(matches)==1 and len(transfers)==1:outcome.update(businessState='collateral_'+summary['action'],exchangeBalanceAUSD=s.units(matches[0]['fields']['balanceCNS'],6))
    elif row['venue']=='castora':
        if summary['action']=='predict':
            matches=[e for e in events if e['name']=='Predicted' and e['fields']['poolId']==summary['pool'] and e['fields']['predicter'].lower()==payload['transaction']['from'] and e['fields']['predictionPrice']==raw(summary['predictionPrice'],8)]
            if len(matches)==1:outcome.update(businessState='prediction_entered',predictionId=matches[0]['fields']['predictionId'])
        else:
            matches=[e for e in events if e['name']=='ClaimedWinnings' and e['fields']['poolId']==summary['pool'] and e['fields']['predictionId']==summary['prediction'] and e['fields']['winner'].lower()==payload['transaction']['from']]
            if len(matches)==1:outcome.update(businessState='winnings_claimed',payoutRaw=str(matches[0]['fields']['wonAmount']),payoutToken=matches[0]['fields']['stakeToken'])
    # Chain inclusion, business execution and finality are separate fields.
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(outcome),ident))
