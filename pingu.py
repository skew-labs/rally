"""Protected Pingu requests, cancellation and keeper event reconciliation.

Source: PinguProtocol/pingu-exchange-contracts (BUSL-1.1 ABI interfaces).
No keeper impersonation or server signing. A request receipt is not a fill.
"""
import json,re,time,threading
from eth_abi import decode
from eth_utils import keccak
import service as s
import venues as v
import extra_routes as e
import pyth_oracle as oracle
from venue_pins import pin as deployment_pin

MARKET='(string,string,address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,bytes32,bool,bool,uint256,uint256)'
ORDER='(uint256,address,address,string,uint256,uint256,uint256,uint256,bool,uint8,bool,uint256,uint256,uint256)'
POSITION='(address,address,string,bool,uint256,uint256,int256,uint256,uint256)'
EVENTS={name:'0x'+keccak(text=name+'(uint256,address,address,string,bool,uint256,uint256,uint256,uint256,uint256,uint256,int256,uint256'+(',int256,int256,int256' if name=='PositionDecreased' else '')+')').hex() for name in ('PositionIncreased','PositionDecreased')}
HEALTH_LOCK=threading.Lock();HEALTH={};HEALTH_AT=0

def contracts():return {k:p['address'] for k,p in json.loads((s.ROOT/'config/venue-pins.json').read_text())['venues']['pingu'].items()}
def read(module,signature,types=(),values=(),outputs=('bool',),block='latest'):return e.read(contracts()[module],signature,types,values,outputs,block)
def pin():
    value=deployment_pin('pingu');c=contracts();labels=['assetStore','fundStore','marketStore','orderStore','riskStore','referralStore']
    results=e.batch([e.request(c['orders'],label+'()') for label in labels],'latest')
    if any(not ok or e.decoded(['address'],raw)[0].lower()!=c[label] for label,(ok,raw) in zip(labels,results)):raise s.Problem('Pingu module linkage changed',503,'venue_contract_changed')
    if read('pythUpdater','pyth()',outputs=['address'])[0].lower()!=oracle.PYTH:raise s.Problem('Pingu oracle changed',503,'oracle_identity')
    return value

def health(block=None):
    global HEALTH,HEALTH_AT
    with HEALTH_LOCK:
        if time.monotonic()-HEALTH_AT<20:return dict(HEALTH)
        block=block or s.rpc('eth_blockNumber',[]);head=int(block,16);c=contracts()
        flags=[read('orderStore',x+'()',block=block)[0] for x in ('areNewOrdersPaused','isProcessingPaused')]
        logs=[]
        for start in range(max(0,head-249),head+1,100):
            logs+=s.rpc('eth_getLogs',[{'address':c['positions'],'fromBlock':hex(start),'toBlock':hex(min(head,start+99)),'topics':[list(EVENTS.values())]}])
        recent=None
        for log in sorted(logs,key=lambda x:(int(x['blockNumber'],16),int(x['logIndex'],16)),reverse=True):
            if log.get('removed'):continue
            observed=s.rpc('eth_getBlockByNumber',[log['blockNumber'],False])
            if not observed or observed['hash'].lower()!=log['blockHash'].lower() or int(observed['timestamp'],16)<s.now()-120:continue
            tx=s.rpc('eth_getTransactionByHash',[log['transactionHash']])
            if not tx or not read('pool','isKeeperYellowlisted(address)',['address'],[tx['from']])[0]:continue
            recent={'at':int(observed['timestamp'],16),'tx':log['transactionHash'],'block':int(log['blockNumber'],16)};break
        HEALTH={'newOrdersPaused':flags[0],'processingPaused':flags[1],'keeperRecent':recent,'ready':not any(flags) and bool(recent),'observedAt':s.now(),'block':head};HEALTH_AT=time.monotonic();return dict(HEALTH)

def market(ident,block='latest'):
    if not re.fullmatch(r'pingu:[A-Za-z0-9._/\-]{1,40}',str(ident)):raise s.Problem('Invalid Pingu market')
    name=ident.split(':',1)[1];values=read('marketStore','get(string)',['string'],[name],[MARKET],block)[0]
    if values[3]<=0:raise s.Problem('Unknown Monad Pingu market',404)
    return name,values

def account(address,block='latest'):
    orders=read('orderStore','getUserOrders(address)',['address'],[address],[ORDER+'[]'],block)[0]
    positions=read('positionStore','getUserPositions(address)',['address'],[address],[POSITION+'[]'],block)[0]
    return {'wallet':address,'orders':[{'id':str(x[0]),'asset':x[2],'market':'pingu:'+x[3],'sizeRaw':str(x[5]),'expiry':x[12]} for x in orders],'positions':[{'asset':x[1],'market':'pingu:'+x[2],'direction':'long' if x[3] else 'short','sizeRaw':str(x[4]),'marginRaw':str(x[5]),'priceRaw':str(x[7])} for x in positions if x[4]>0]}

def status(who):
    _,address=v.wallet(who);pin();return account(address)

def request(address,data,block='latest'):
    name,m=market(data.get('market'),block);asset=s.ZERO if data.get('asset','MON')=='MON' else str(data['asset']).lower();token=s.GATEWAY.token_map.get('MON' if asset==s.ZERO else asset)
    if not token:raise s.Problem('Unreviewed Pingu collateral')
    minimum,_=read('assetStore','get(address)',['address'],[asset],['(uint256,address)'],block)[0]
    if minimum<=0:raise s.Problem('Pingu does not support this collateral',409)
    close=data['kind']=='close';margin=0 if close else v.raw(data.get('amount'),token['decimals'])
    if close:
        if any(k in data for k in ('direction','quantity','size','leverage')):raise s.Problem('Full close derives size and side from the open position')
        pos=read('positionStore','getPosition(address,address,string)',['address','address','string'],[address,asset,name],[POSITION],block)[0]
        if pos[0].lower()!=address or pos[4]<=0:raise s.Problem('No open position to close',409)
        size=pos[4];long=not pos[3]
    else:
        if data.get('direction') not in {'long','short'}:raise s.Problem('Choose Long or Short')
        leverage=data.get('leverage',1)
        if type(leverage) is not int or not 1<=leverage<=min(10,m[3]):raise s.Problem('Invalid leverage')
        size=margin*leverage;long=data['direction']=='long'
        if size<minimum or m[12]:raise s.Problem('Market is reduce-only or order is below its minimum',409)
    protection=v.raw(data.get('limit'),18)
    reference=oracle.onchain(['0x'+m[10].hex()],max_age=m[9],block=block).get('0x'+m[10].hex())
    if not reference:raise s.Problem('Fresh Pingu oracle price unavailable',503,'stale_price')
    price=v.raw(str(reference['price']),18)
    if long and protection<price or not long and protection>price:raise s.Problem('Protection price would reject this quote',409,'price_limit')
    fee=size*m[5]//10000;discount=read('referralStore','getReferralFeeShare(address)',['address'],[address],['uint256'],block)[0]
    if not 0<=discount<=10000:raise s.Problem('Referral fee configuration changed',503)
    fee-=fee*discount//10000
    ttl=read('orderStore','maxMarketOrderTTL()',outputs=['uint256'],block=block)[0]
    expiry=int(data.get('orderExpiry',s.now()+min(120,ttl)))
    if not s.now()+5<expiry<=s.now()+min(120,ttl):raise s.Problem('Order expires too soon. Review again.',409)
    params=(0,address,asset,name,margin,size,protection,fee,long,0,close,0,expiry,0)
    tx={'from':address,'to':contracts()['orders'],'data':e.call('submitOrder('+ORDER+',uint256,uint256)',[ORDER,'uint256','uint256'],[params,0,0]),'value':hex(margin+fee if asset==s.ZERO and not close else 0),'chainId':'0x8f'}
    approval=None if asset==s.ZERO or close else {'token':asset,'spender':contracts()['fundStore'],'amountRaw':str(margin+fee)}
    summary={'action':data['kind'],'market':name,'marketId':data['market'],'asset':token['symbol'],'collateral':asset,'amount':s.units(margin,token['decimals']),'sizeRaw':str(size),'direction':'long' if long else 'short','limit':s.units(protection,18),'fee':s.units(fee,token['decimals']),'feeBps':m[5],'orderExpiry':expiry,'reduceOnly':close,'price':reference['price'],'oraclePublishedAt':reference['time']}
    return tx,approval,summary

def plan(who,data):
    user,address=v.wallet(who);identity=pin();kind=data.get('kind')
    if kind in {'order','close'}:
        if not health()['ready']:raise s.Problem('Pingu keeper execution is not currently verified. New requests are unavailable.',503,'keeper_unverified')
        tx,approval,summary=request(address,data);data={**data,'orderExpiry':summary['orderExpiry']}
    elif kind=='cancel':
        oid=int(data.get('order',0))
        if not read('orderStore','isUserOrder(uint256,address)',['uint256','address'],[oid,address])[0]:raise s.Problem('Order does not belong to this wallet',403)
        tx={'from':address,'to':contracts()['orders'],'data':e.call('cancelOrders(uint256[])',['uint256[]'],[[oid]]),'value':'0x0','chainId':'0x8f'};approval=None;summary={'action':'cancel','orderId':str(oid),'asset':'MON'}
    else:raise s.Problem('Unsupported Pingu action')
    ident=s.uid();payload={'summary':summary,'transaction':tx,'approval':approval,'pin':identity,'args':data,'created':s.now(),'expires':s.now()+60}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,address,'pingu',kind,s.dump(payload),payload['expires']));return {'id':ident,**payload}

def prepare(row,payload):
    if pin()!=payload['pin']:raise s.Problem('Pingu deployment changed',503,'venue_contract_changed')
    if row['kind']=='cancel':
        oid=int(payload['summary']['orderId'])
        if not read('orderStore','isUserOrder(uint256,address)',['uint256','address'],[oid,row['wallet']])[0]:raise s.Problem('Order is no longer pending',409)
        expected={'from':row['wallet'],'to':contracts()['orders'],'data':e.call('cancelOrders(uint256[])',['uint256[]'],[[oid]]),'value':'0x0','chainId':'0x8f'}
        if payload['transaction']!=expected:raise s.Problem('Cancellation identity changed',409,'venue_identity')
        return
    if not health()['ready']:raise s.Problem('Pingu keeper execution unavailable',503,'keeper_unverified')
    tx,approval,summary=request(row['wallet'],payload['args'])
    if tx!=payload['transaction'] or approval!=payload['approval'] or any(summary[k]!=payload['summary'][k] for k in summary if k not in ('price','oraclePublishedAt')):raise s.Problem('Pingu request changed. Review again.',409,'venue_identity')

def reconcile(row):
    if row['state'] in {'failed','invalid'}:return
    receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False]);final=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not block or block['hash'].lower()!=receipt['blockHash'].lower():return
    state='finalized' if final and int(final['number'],16)>=int(receipt['blockNumber'],16) else 'confirmed';payload=json.loads(row['payload']);summary=payload['summary'];result=json.loads(row['outcome']) if row.get('outcome') else {'receipt':receipt,'businessState':'request_unverified'}
    if int(block['timestamp'],16)<payload['created']-5:state='invalid';result['businessState']='outside_review_window'
    elif int(receipt['status'],16)!=1:state='failed';result['businessState']='reverted'
    elif row['kind']=='cancel':
        signature='0x'+keccak(text='OrderCancelled(uint256,address,string)').hex()
        if any(l.get('address','').lower()==contracts()['orders'] and len(l.get('topics',[]))==3 and l['topics'][0].lower()==signature and int(l['topics'][1],16)==int(summary['orderId']) and '0x'+l['topics'][2][-40:].lower()==row['wallet'] for l in receipt.get('logs',[]) if not l.get('removed')):result['businessState']='cancelled'
    else:
        signature='0x'+keccak(text='OrderCreated(uint256,address,address,string,uint256,uint256,uint256,uint256,bool,uint8,bool,uint256,uint256)').hex()
        for l in receipt.get('logs',[]) if not result.get('orderId') else []:
            if l.get('removed') or l.get('address','').lower()!=contracts()['orders'] or len(l.get('topics',[]))!=4 or l['topics'][0].lower()!=signature or '0x'+l['topics'][2][-40:].lower()!=row['wallet'] or '0x'+l['topics'][3][-40:].lower()!=summary['collateral']:continue
            values=decode(['string','uint256','uint256','uint256','uint256','bool','uint8','bool','uint256','uint256'],bytes.fromhex(l['data'][2:]))
            if values[0]!=summary['market'] or values[2]!=int(summary['sizeRaw']) or values[3]!=v.raw(summary['limit'],18) or values[5]!=(summary['direction']=='long') or values[6]!=0 or values[7]!=summary['reduceOnly']:continue
            result.update(orderId=str(int(l['topics'][1],16)),businessState='keeper_pending',scanNextBlock=result.get('scanNextBlock',int(receipt['blockNumber'],16)))
        if result.get('orderId') and result['businessState']=='keeper_pending':
            start=result['scanNextBlock'];head=int(final['number'],16) if final else int(receipt['blockNumber'],16);end=min(start+99,head)
            if end>=start:
                topics=[list(EVENTS.values()),hex(int(result['orderId']))[2:].rjust(64,'0'),'0x'+row['wallet'][2:].rjust(64,'0'),'0x'+summary['collateral'][2:].rjust(64,'0')];topics[1]='0x'+topics[1]
                logs=s.rpc('eth_getLogs',[{'address':contracts()['positions'],'fromBlock':hex(start),'toBlock':hex(end),'topics':topics}])
                for l in logs:
                    if l.get('removed') or l.get('address','').lower()!=contracts()['positions'] or len(l.get('topics',[]))!=4 or any(l['topics'][i].lower()!=topics[i] for i in range(1,4)) or l['topics'][0].lower() not in EVENTS.values():continue
                    observed=s.rpc('eth_getBlockByNumber',[l['blockNumber'],False])
                    if not start<=int(l['blockNumber'],16)<=end or not observed or observed['hash'].lower()!=l['blockHash'].lower():continue
                    decreased=l['topics'][0].lower()==EVENTS['PositionDecreased'];types=['string','bool']+['uint256']*6+['int256','uint256']+(['int256']*3 if decreased else [])
                    values=decode(types,bytes.fromhex(l['data'][2:]));limit=v.raw(summary['limit'],18)
                    expected_long=(summary['direction']=='long')!=summary['reduceOnly']
                    if decreased!=summary['reduceOnly'] or values[1]!=expected_long or values[0]!=summary['market'] or values[2]!=int(summary['sizeRaw']) or values[4]<=0 or (summary['direction']=='long' and values[4]>limit) or (summary['direction']=='short' and values[4]<limit):continue
                    position=read('positionStore','getPosition(address,address,string)',['address','address','string'],[row['wallet'],summary['collateral'],summary['market']],[POSITION],l['blockNumber'])[0]
                    if position[4]!=values[6]:continue
                    result.update(businessState='closed' if decreased and row['kind']=='close' and values[6]==0 else 'filled',settlementTx=l['transactionHash'],executedPriceRaw=str(values[4]),settledAtBlock=int(l['blockNumber'],16))
                result['scanNextBlock']=end+1
                if result['businessState']=='keeper_pending':
                    cancel=s.rpc('eth_getLogs',[{'address':contracts()['orders'],'fromBlock':hex(start),'toBlock':hex(end),'topics':['0x'+keccak(text='OrderCancelled(uint256,address,string)').hex(),topics[1],topics[2]]}])
                    for log in cancel:
                        if log.get('removed') or log.get('address','').lower()!=contracts()['orders'] or len(log.get('topics',[]))!=3 or log['topics'][0].lower()!='0x'+keccak(text='OrderCancelled(uint256,address,string)').hex() or any(log['topics'][i].lower()!=topics[i] for i in (1,2)):continue
                        observed=s.rpc('eth_getBlockByNumber',[log['blockNumber'],False])
                        if not start<=int(log['blockNumber'],16)<=end or not observed or observed['hash'].lower()!=log['blockHash'].lower():continue
                        result.update(businessState='cancelled',settlementTx=log['transactionHash'],settledAtBlock=int(log['blockNumber'],16));break
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(result),row['id']))
