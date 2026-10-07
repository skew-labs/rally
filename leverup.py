"""Direct, wallet-approved LeverUp USDC requests. No server key or relay grant."""
import json, re
from concurrent.futures import ThreadPoolExecutor
from eth_abi import encode, decode
from eth_utils import keccak
import service as s
import venues as v
import perp_universe as p

DIAMOND=p.POOL
LVUSD='0xfd44b35139ae53fff7d8f2a9869c503d987f00d1'
ABI=json.loads((s.ROOT/'config/leverup-abi.json').read_text())
TERMINAL={'filled','refunded','closed','close_rejected','reverted','invalid'}

def function(name,argc=None):
    return next(f for f in ABI if f.get('type')=='function' and f.get('name')==name and (argc is None or len(f['inputs'])==argc))

def signature(f):return f['name']+'('+','.join(v.typ(x) for x in f['inputs'])+')'
def calldata(name,args=()):
    f=function(name,len(args))
    return '0x'+keccak(text=signature(f)).hex()[:8]+encode([v.typ(x) for x in f['inputs']],args).hex()

def read(name,args=(),block='latest'):
    f=function(name,len(args));result=s.rpc('eth_call',[{'to':DIAMOND,'data':calldata(name,args)},block])
    values=decode([v.typ(x) for x in f['outputs']],bytes.fromhex(result[2:]))
    result=[v.named(x,y) for x,y in zip(f['outputs'],values)]
    return result[0] if len(result)==1 else result

def pin():
    manifest=json.loads((s.ROOT/'config/leverup-pins.json').read_text())
    if manifest['abiHash']!=s.digest(s.dump(ABI)):raise s.Problem('LeverUp interface changed. Review required.',503,'venue_contract_changed')
    if s.digest(s.rpc('eth_getCode',[DIAMOND,'latest']).lower())!=manifest['diamondHash']:raise s.Problem('LeverUp contract changed. Review required.',503,'venue_contract_changed')
    def verify(item):
        selector=bytes.fromhex(item['selector'][2:])
        data='0x'+keccak(text='facetAddress(bytes4)').hex()[:8]+encode(['bytes4'],[selector]).hex()
        address=decode(['address'],bytes.fromhex(s.rpc('eth_call',[{'to':DIAMOND,'data':data},'latest'])[2:]))[0].lower()
        if address!=item['address'] or s.digest(s.rpc('eth_getCode',[address,'latest']).lower())!=item['codeHash']:raise s.Problem('LeverUp trading facet changed. Review required.',503,'venue_contract_changed')
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(verify,manifest['facets']))
    return manifest

def market(ident,opening=False):
    if not re.fullmatch(r'leverup:0x[0-9a-f]{40}',str(ident)):raise s.Problem('Invalid LeverUp market')
    # The official feed also lists markets executed on Hyperliquid. Only POOL
    # pairs are eligible, even if a caller directly supplies an excluded base.
    live=p.leverup();item=next((m for m in live['markets'] if m['id']==ident),None)
    if not item:raise s.Problem('Monad LeverUp market not found',404)
    cfg=read('getPairByBaseV4',[item['pairBase']])
    if cfg['base'].lower()!=item['pairBase'] or cfg['name']!=item['symbol']:raise s.Problem('Market identity changed',503)
    if opening and (not item['open'] or item['stale'] or cfg['status']!=0):raise s.Problem('This market is not open for new positions',409)
    return item,cfg

def oracle(base):
    value=s.http_json('https://service.leverup.xyz/v1/oracle/price/updates/by-position',{'pairBase':base,'collateral':s.USDC,'blockChain':'MONAD','options':{'includeEncodingData':True,'includeFee':True,'includePrice':True,'includePublishTime':True,'allowPartial':False}},headers=p.HEADERS,timeout=6)
    if value.get('failures'):raise s.Problem('LeverUp oracle update unavailable',503,'oracle_unavailable')
    arrays=[]
    for key in ['pythPriceUpdateData','pythProPriceUpdateData']:
        a=value.get(key)
        if not isinstance(a,list) or len(a)>8 or any(not isinstance(x,str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2}){1,20000}',x) for x in a):raise s.Problem('Invalid oracle update',503)
        arrays.append([bytes.fromhex(x[2:]) for x in a])
    times=[int(t) for key in ['pythCorePublishTime','pythProPublishTime','dexOraclePublishTime'] for t in value.get(key,{}).values()]
    if not any(arrays) or not times or any(t<s.now()-15 or t>s.now()+5 for t in times):raise s.Problem('LeverUp oracle update is stale',503,'stale_price')
    fee=int(value['updateFee'])+int(value['verifition_fee'])
    if not 0<=fee<=10**16:raise s.Problem('Oracle fee needs review',503)
    expires=min(s.now()+20,min(times)+25,int(value.get('validUntil',s.now()+20)))
    if expires<=s.now()+5:raise s.Problem('Oracle update expires too soon. Refresh the order.',409,'stale_price')
    return tuple(arrays),fee,expires

def plan(who,data):
    user,address=v.wallet(who);contract_pin=pin();kind=data.get('kind');item,cfg=market(data.get('market'),opening=kind=='order')
    approval=None;value=0;expires=s.now()+60
    if kind=='order':
        direction=data.get('direction','long')
        if direction not in {'long','short'} or data.get('collateral','USDC')!='USDC':raise s.Problem('Choose a side and USDC collateral')
        quantity=v.raw(data.get('quantity'),10);amount=v.raw(data.get('amount'),6,'1000000000')
        try:slippage=int(data.get('slippage',50))
        except (ValueError,TypeError):raise s.Problem('Invalid slippage')
        if not 1<=slippage<=100 or quantity>=2**128 or amount>=2**96:raise s.Problem('Invalid amount or slippage')
        mark=v.raw(str(item['mark']),18)
        bound=mark*(10000+slippage)//10000 if direction=='long' else mark*(10000-slippage)//10000
        open_data=(item['pairBase'],direction=='long',s.USDC,LVUSD,amount,quantity,bound,0,0,0)
        updates,value,expires=oracle(item['pairBase'])
        txdata=calldata('openMarketTradeV2',[open_data,updates,0])
        approval={'token':s.USDC,'spender':DIAMOND,'amountRaw':str(amount)}
        summary={'action':'order','market':item['symbol'],'marketId':item['id'],'direction':direction,'quantity':s.units(quantity,10),'amount':s.units(amount,6),'asset':'USDC','limit':s.units(bound,18),'slippageBps':slippage,'feeBps':cfg['feeConfig']['openFeeP'],'estimatedNotionalUSD':s.units(quantity*mark//10**10,18),'oracleFeeMON':s.units(value,18),'executionModel':'keeper','settlementAsset':'LVUSD'}
    elif kind=='close':
        position_hash=str(data.get('position','')).lower()
        if not re.fullmatch(r'0x[0-9a-f]{64}',position_hash):raise s.Problem('Invalid position')
        if read('getPositionTrader',[bytes.fromhex(position_hash[2:])]).lower()!=address:raise s.Problem('This position belongs to another wallet',403)
        position=read('getPositionByHashV4',[bytes.fromhex(position_hash[2:])])
        if position['pairBase'].lower()!=item['pairBase'] or position['marginToken'].lower()!=LVUSD or not position['qty']:raise s.Problem('Position not available for this market',409)
        if position['earliestCloseTime']>s.now():raise s.Problem('Minimum holding period has not elapsed',409)
        txdata=calldata('closeTrade',[bytes.fromhex(position_hash[2:])])
        summary={'action':'close','market':item['symbol'],'marketId':item['id'],'positionHash':position_hash,'quantity':s.units(position['qty'],10),'asset':'LVUSD','executionModel':'keeper'}
    else:raise s.Problem('Unsupported LeverUp action')
    ident=s.uid();payload={'summary':summary,'transaction':{'from':address,'to':DIAMOND,'data':txdata,'value':hex(value),'chainId':'0x8f'},'approval':approval,'pin':contract_pin,'args':data,'created':s.now(),'expires':expires}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,address,'leverup',kind,s.dump(payload),expires))
    return {'id':ident,**payload}

def prepare(row,payload):
    if pin()!=payload['pin']:raise s.Problem('LeverUp contract changed',503,'venue_contract_changed')
    if payload['transaction']['to']!=DIAMOND or payload['transaction']['from']!=row['wallet'] or payload['transaction']['chainId']!='0x8f':raise s.Problem('Order identity changed',409)
    if row['kind']=='order':market(payload['summary']['marketId'],opening=True)
    else:
        position=bytes.fromhex(payload['summary']['positionHash'][2:])
        if read('getPositionTrader',[position]).lower()!=row['wallet']:raise s.Problem('Position ownership changed',409)

def positions(who,ident):
    _,address=v.wallet(who);item,_=market(ident)
    values=read('getPositionsV4',[address,item['pairBase']])
    for value in values:
        value['quantity']=s.units(value['qty'],10);value['entry']=s.units(value['entryPrice'],18);value['marginAmount']=s.units(value['margin'],18)
    return {'positions':values,'market':item['id'],'wallet':address,'chainId':143}

def events(logs):
    result=[]
    for log in logs:
        if log.get('removed') or log.get('address','').lower()!=DIAMOND or not log.get('topics'):continue
        for event in (e for e in ABI if e.get('type')=='event' and not e.get('anonymous')):
            if log['topics'][0].lower()!='0x'+keccak(text=signature(event)).hex():continue
            try:
                indexed=[x for x in event['inputs'] if x.get('indexed')];plain=[x for x in event['inputs'] if not x.get('indexed')]
                if len(log['topics'])!=len(indexed)+1:continue
                fields={x['name']:v.named(x,y) for x,y in zip(plain,decode([v.typ(x) for x in plain],bytes.fromhex(log['data'][2:])))}
                fields.update({x['name']:v.named(x,decode([v.typ(x)],bytes.fromhex(t[2:]))[0]) for x,t in zip(indexed,log['topics'][1:])})
                result.append({'name':event['name'],'fields':fields,'transactionHash':log.get('transactionHash'),'blockNumber':log.get('blockNumber'),'blockHash':log.get('blockHash')})
            except (ValueError,TypeError):continue
    return result

def reconcile(row):
    payload=json.loads(row['payload']);previous=json.loads(row['outcome']) if row['outcome'] else {}
    if previous.get('businessState') in TERMINAL and previous.get('settlementState') in {None,'finalized'}:return
    receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not block or block['hash'].lower()!=receipt['blockHash'].lower():return
    final=s.rpc('eth_getBlockByNumber',['finalized',False]);final_number=int(final['number'],16) if final else -1
    state='finalized' if final_number>=int(receipt['blockNumber'],16) else 'confirmed'
    out={'receipt':receipt,'businessState':'keeper_pending','reviewExpiredAtInclusion':int(block['timestamp'],16)>payload['expires']}
    if int(receipt['status'],16)!=1:state='failed';out['businessState']='reverted'
    elif int(block['timestamp'],16)<payload['created']-5:state='invalid';out['businessState']='invalid'
    else:
        summary=payload['summary'];wallet=payload['transaction']['from'];request_name='MarketPendingTrade' if row['kind']=='order' else 'CloseTradeRequested'
        matches=[e for e in events(receipt.get('logs',[])) if e['name']==request_name and e['fields']['user'].lower()==wallet]
        if row['kind']=='order':matches=[e for e in matches if e['fields']['trade']['pairBase'].lower()==summary['marketId'].split(':')[1] and e['fields']['trade']['qty']==v.raw(summary['quantity'],10) and e['fields']['trade']['amountIn']==v.raw(summary['amount'],6) and e['fields']['trade']['tokenIn'].lower()==s.USDC and e['fields']['trade']['lvToken'].lower()==LVUSD and e['fields']['trade']['isLong']==(summary['direction']=='long')]
        else:matches=[e for e in matches if e['fields']['positionHash'].lower()==summary['positionHash']]
        if len(matches)!=1:out['businessState']='request_unverified'
        else:
            request=matches[0]['fields'];source=request['tradeHash'] if row['kind']=='order' else request['closeHash'];out['requestHash']=source
            # Scan bounded pages. Inclusion is never relabeled as a fill. Revisit
            # the previous page for canonical readback rather than trusting a cursor.
            first=max(int(receipt['blockNumber'],16),int(previous.get('scanTo',int(receipt['blockNumber'],16)))-64)
            last=min(int(s.rpc('eth_blockNumber',[]),16),first+2047)
            logs=s.rpc('eth_getLogs',[{'address':DIAMOND,'fromBlock':hex(first),'toBlock':hex(last),'topics':[None,'0x'+wallet[2:].rjust(64,'0')]}])
            out['scanTo']=last
            for event in events(logs):
                f=event['fields'];name=event['name'];linked=f.get('sourceHash') or f.get('tradeHash') or f.get('closeHash')
                if linked!=source:continue
                settlement=s.rpc('eth_getTransactionReceipt',[event['transactionHash']]);canonical=s.rpc('eth_getBlockByNumber',[event['blockNumber'],False])
                if not settlement or int(settlement['status'],16)!=1 or not canonical or canonical['hash'].lower()!=event['blockHash'].lower() or settlement['blockHash'].lower()!=event['blockHash'].lower():continue
                if row['kind']=='order' and name in {'OpenPosition','PositionIncreased'}:
                    update=f['update'];position=update['position']
                    if update['sourceHash']!=source or position['pairBase'].lower()!=summary['marketId'].split(':')[1] or position['user'].lower()!=wallet or position['isLong']!=(summary['direction']=='long') or position['lvToken'].lower()!=LVUSD or update['addedQty']!=v.raw(summary['quantity'],10):continue
                    # Query at the settlement block, so later additions/closures
                    # cannot masquerade as this request's result.
                    readback=read('getPositionByHashV4',[bytes.fromhex(f['positionHash'][2:])],event['blockNumber'])
                    if readback['pairBase'].lower()!=position['pairBase'].lower() or readback['qty']!=position['qty']:continue
                    out.update(businessState='filled',positionHash=f['positionHash'],fillQuantity=s.units(update['addedQty'],10),entryPrice=s.units(update['addedEntryPrice'],18))
                elif row['kind']=='order' and name=='PendingTradeRefund':out.update(businessState='refunded',refundReason=f['refund'])
                elif row['kind']=='close' and name=='ClosePosition' and f['positionHash']==summary['positionHash']:out.update(businessState='closed',closeQuantity=s.units(f['closeQty'],10),closePrice=s.units(f['closeInfo']['closePrice'],18),pnlLVUSD=s.units(f['closeInfo']['pnl'],18))
                else:continue
                out.update(settlementTransaction=event['transactionHash'],settlementState='finalized' if final_number>=int(event['blockNumber'],16) else 'confirmed',settlementReceipt=settlement)
                break
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(out),row['id']))
