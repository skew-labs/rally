"""Owner-only Drake portfolios and orders from the official integration ABI."""
import json,re
from eth_abi import encode,decode
from eth_utils import keccak
import service as s
import venues as v
import extra_routes as e
import pyth_oracle as oracle
from venue_pins import pin as deployment_pin

ROOT=s.ROOT/'config/drake'
CONFIG=json.loads((ROOT/'mainnet.json').read_text())
TRADING=CONFIG['contracts']['trading'].lower();FACTORY=CONFIG['contracts']['portfolioFactory'].lower()
ORACLE=CONFIG['contracts']['oracleRouter'].lower();AUSD=v.AUSD
ABIS={}

def abi(name):
    if name not in ABIS:ABIS[name]=json.loads((ROOT/(name+'.json')).read_text())
    return ABIS[name]

def calldata(name,method,args):
    choices=[f for f in abi(name) if f.get('type')=='function' and f['name']==method and len(f['inputs'])==len(args)]
    if len(choices)!=1:raise s.Problem('Unreviewed Drake function',503,'venue_interface_changed')
    f=choices[0];types=[v.typ(x) for x in f['inputs']]
    return '0x'+keccak(text=method+'('+','.join(types)+')').hex()[:8]+encode(types,args).hex()

def read(target,name,method,args=(),block='latest'):
    f=next(f for f in abi(name) if f.get('type')=='function' and f['name']==method and len(f['inputs'])==len(args))
    raw=s.rpc('eth_call',[{'to':target,'data':calldata(name,method,list(args))},block]);values=decode([v.typ(o) for o in f['outputs']],bytes.fromhex(raw[2:]))
    if encode([v.typ(o) for o in f['outputs']],values).hex()!=raw[2:].lower():raise s.Problem('Drake response identity changed',502,'venue_interface_changed')
    return values

def pin():
    value=deployment_pin('drake');manifest=json.loads((ROOT/'abi-pins.json').read_text())
    if CONFIG['chainId']!=143 or CONFIG['contracts']['settlementToken'].lower()!=AUSD or s.digest(s.dump(CONFIG))!=manifest['config']:raise s.Problem('Drake configuration changed',503,'venue_contract_changed')
    for name,digest in manifest['abis'].items():
        if s.digest(s.dump(abi(name)))!=digest:raise s.Problem('Drake interface changed',503,'venue_contract_changed')
    return value

def instrument(ident):
    if not re.fullmatch('drake:[1-9][0-9]*',str(ident)):raise s.Problem('Invalid Drake market')
    number=int(ident.split(':')[1]);item=CONFIG['instruments'].get(str(number))
    if not item:raise s.Problem('Unknown Monad Drake market',404)
    return number,item

def portfolio_type(value):
    if value not in {'imp','cmp'}:raise s.Problem('Choose isolated or cross margin')
    # Official SDK src/cli.ts: IMP = 1, CMP = 2.
    return 1 if value=='imp' else 2

def account(address,kind='imp',ident=None,block='latest'):
    target=read(FACTORY,'PortfolioFactory','userPortfolio',[address,portfolio_type(kind)],block)[0]
    result={'wallet':address,'portfolio':target,'portfolioType':kind,'asset':'AUSD','chainId':143}
    if target==s.ZERO:return result
    name='IsolatedMarginPortfolio' if kind=='imp' else 'CrossMarginPortfolio'
    if read(target,name,'owner',block=block)[0].lower()!=address:raise s.Problem('Portfolio ownership mismatch',503,'portfolio_identity')
    result.update(balanceRaw=str(e.read(AUSD,'balanceOf(address)',['address'],[target],['uint256'],block)[0]),availableRaw=str(read(target,name,'getAvailableAssetBalance',block=block)[0]))
    if ident:
        number,item=instrument(ident);position=read(target,name,'getPosByInstId',[number],block)[0]
        helper=read(target,name,'h',block=block)[0];book=read(helper,'CommonHelper','getOrderBookByInstId',[number],block)[0]
        pending=read(book,'OrderBook','getPortfolioPendingOrdersData',[target],block)[1]
        result.update(market=ident,leverage=read(target,name,'getLeverage',[number],block)[0],position={'state':position[0],'side':position[1],'sizeRaw':str(position[2]),'averageRaw':str(position[3])},pendingOrderIds=[str(x) for x in pending])
    return result

def status(who,kind='imp',ident=None):
    _,address=v.wallet(who);pin();return account(address,kind,ident)

def order_bytes(portfolio,number,side,size,bound,reduce,updates):
    if portfolio==s.ZERO or side not in (1,2) or not isinstance(reduce,bool) or not 0<size<2**64 or not 0<bound<2**64:raise s.Problem('Invalid Drake order')
    return calldata('Trading','executeMarketOrder',[((number,size,portfolio,side,reduce),bound),updates])

def plan(who,data):
    user,address=v.wallet(who);contract_pin=pin();kind=data.get('kind');ptype=data.get('portfolioType','imp');before=account(address,ptype,data.get('market'));target=before['portfolio'];approval=None;summary={'action':kind,'asset':'AUSD','portfolio':target,'portfolioType':ptype};updates=[]
    if kind=='create':
        if target!=s.ZERO:raise s.Problem('This portfolio already exists',409)
        target=FACTORY;encoded=calldata('PortfolioFactory','deployPortfolio',[portfolio_type(ptype)])
    else:
        if target==s.ZERO:raise s.Problem('Create a Drake portfolio first',409,'drake_portfolio_required')
        name='IsolatedMarginPortfolio' if ptype=='imp' else 'CrossMarginPortfolio'
        if kind in {'deposit','withdraw'}:
            amount=v.raw(data.get('amount'),6);summary['amount']=s.units(amount,6)
            if kind=='deposit':encoded=e.call('transfer(address,uint256)',['address','uint256'],[target,amount]);target=AUSD
            else:
                if amount>int(before['availableRaw']):raise s.Problem('Not enough available collateral',409)
                encoded=calldata(name,'withdraw',[AUSD,amount])
        elif kind in {'order','close'}:
            number,item=instrument(data.get('market'));updates,reference=oracle.signed(item['pythFeedId'])
            actual,scale=e.read(ORACLE,'updateAndGetInstPrice(uint256,bytes[])',['uint256','bytes[]'],[number,updates],['uint256','uint256'])
            if scale!=10**6 or actual<=0:raise s.Problem('Drake price scale changed',503,'oracle_identity')
            bound=v.raw(data.get('limit'),6);reduce=data.get('reduceOnly',False)
            if not isinstance(reduce,bool):raise s.Problem('Invalid reduce-only setting')
            if kind=='close':
                if any(k in data for k in ('quantity','direction','reduceOnly')):raise s.Problem('Full close derives size and side from the open position')
                position=before['position']
                if position['state']!=1 or position['side'] not in (1,2) or int(position['sizeRaw'])<=0 or before['pendingOrderIds']:raise s.Problem('Cancel pending orders before closing an open position',409)
                side=2 if position['side']==1 else 1;quantity=int(position['sizeRaw']);reduce=True
            else:
                if data.get('direction') not in {'long','short'}:raise s.Problem('Choose Long or Short')
                side=1 if data['direction']=='long' else 2;quantity=v.raw(data.get('quantity'),4)
            if side==1 and bound<actual or side==2 and bound>actual:raise s.Problem('Protection price would reject the current quote',409,'price_limit')
            encoded=order_bytes(before['portfolio'],number,side,quantity,bound,reduce,updates);target=TRADING
            summary.update(market=item['symbol'],marketId=data['market'],quantity=s.units(quantity,4),sizeRaw=str(quantity),direction='long' if side==1 else 'short',limit=s.units(bound,6),reduceOnly=reduce,leverage=before.get('leverage'),price=s.units(actual,6),oraclePublishedAt=reference['time'])
        elif kind=='cancel':
            number,_=instrument(data.get('market'));order=int(data.get('order',0))
            if str(order) not in before['pendingOrderIds']:raise s.Problem('Order does not belong to this portfolio and market',403)
            encoded=calldata('Trading','cancelPendingOrder',[order]);target=TRADING;summary.update(marketId=data['market'],orderId=str(order))
        else:raise s.Problem('Unsupported Drake action')
    ident=s.uid();payload={'summary':summary,'transaction':{'from':address,'to':target,'data':encoded,'value':'0x0','chainId':'0x8f'},'approval':approval,'pin':contract_pin,'args':data,'before':before,'oracleUpdates':['0x'+x.hex() for x in updates],'created':s.now(),'expires':s.now()+90}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,address,'drake',kind,s.dump(payload),payload['expires']))
    return {'id':ident,**payload}

def prepare(row,payload):
    if pin()!=payload['pin']:raise s.Problem('Drake deployment changed',503,'venue_contract_changed')
    tx=payload['transaction'];summary=payload['summary'];args=payload['args']
    if tx['from']!=row['wallet'] or tx['value']!='0x0' or tx['chainId']!='0x8f':raise s.Problem('Order identity changed',409,'venue_identity')
    current=account(row['wallet'],summary['portfolioType'],args.get('market'))
    if row['kind']=='create':
        if current['portfolio']!=s.ZERO:raise s.Problem('Portfolio already created. Refresh your account.',409)
        expected={'from':row['wallet'],'to':FACTORY,'data':calldata('PortfolioFactory','deployPortfolio',[portfolio_type(summary['portfolioType'])]),'value':'0x0','chainId':'0x8f'}
    else:
        if current['portfolio']!=payload['before']['portfolio']:raise s.Problem('Portfolio changed',409,'portfolio_identity')
        if row['kind'] in {'order','close'}:
            number,item=instrument(summary['marketId']);side=1 if summary['direction']=='long' else 2
            quantity=int(summary['sizeRaw']);bound=v.raw(summary['limit'],6)
            previous=order_bytes(current['portfolio'],number,side,quantity,bound,summary['reduceOnly'],[bytes.fromhex(x[2:]) for x in payload['oracleUpdates']])
            if tx['to']!=TRADING or tx['data']!=previous:raise s.Problem('Stored Drake request changed',409,'venue_identity')
            if row['kind']=='order' and (side!=(1 if args['direction']=='long' else 2) or quantity!=v.raw(args['quantity'],4) or bound!=v.raw(args['limit'],6) or summary['reduceOnly']!=args.get('reduceOnly',False)):raise s.Problem('Reviewed order changed',409,'venue_identity')
            if row['kind']=='close' and (current['position']!=payload['before']['position'] or current['pendingOrderIds']):raise s.Problem('Position changed. Review again.',409,'position_changed')
            if row['kind']=='close' and (not summary['reduceOnly'] or quantity!=int(current['position']['sizeRaw']) or side!=(2 if current['position']['side']==1 else 1)):raise s.Problem('Full-close identity changed',409,'venue_identity')
            updates,reference=oracle.signed(item['pythFeedId'])
            actual,scale=e.read(ORACLE,'updateAndGetInstPrice(uint256,bytes[])',['uint256','bytes[]'],[number,updates],['uint256','uint256'])
            if scale!=10**6 or actual<=0 or (side==1 and bound<actual) or (side==2 and bound>actual):raise s.Problem('Price moved outside your protection price. Review again.',409,'price_limit')
            encoded=order_bytes(current['portfolio'],number,side,quantity,bound,summary['reduceOnly'],updates)
            payload['transaction']={**tx,'data':encoded};payload['oracleUpdates']=['0x'+x.hex() for x in updates];payload['summary']['oraclePublishedAt']=reference['time']
            payload['expires']=min(row['expires'],reference['time']+12)
            if payload['expires']<=s.now()+2:raise s.Problem('Oracle update expires too soon. Review again.',409,'stale_price')
            s.write('UPDATE execution_plans SET payload=? WHERE id=?',(s.dump(payload),row['id']));return
        name='IsolatedMarginPortfolio' if summary['portfolioType']=='imp' else 'CrossMarginPortfolio'
        if row['kind']=='deposit':
            amount=v.raw(summary['amount'],6)
            if e.read(AUSD,'balanceOf(address)',['address'],[row['wallet']],['uint256'])[0]<amount:raise s.Problem('Not enough AUSD in this wallet',409,'insufficient_balance')
            expected={**tx,'to':AUSD,'data':e.call('transfer(address,uint256)',['address','uint256'],[current['portfolio'],amount])}
        elif row['kind']=='withdraw':
            amount=v.raw(summary['amount'],6)
            if amount>int(current['availableRaw']):raise s.Problem('Available collateral changed',409)
            expected={**tx,'to':current['portfolio'],'data':calldata(name,'withdraw',[AUSD,amount])}
        elif row['kind']=='cancel':
            if summary['orderId'] not in current['pendingOrderIds']:raise s.Problem('Order is no longer pending',409)
            expected={**tx,'to':TRADING,'data':calldata('Trading','cancelPendingOrder',[int(summary['orderId'])])}
        else:raise s.Problem('Unsupported Drake action')
    if tx!=expected:raise s.Problem('Stored Drake request changed',409,'venue_identity')

def reconcile(row):
    payload=json.loads(row['payload']);receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False]);final=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not block or block['hash'].lower()!=receipt['blockHash'].lower():return
    state='finalized' if final and int(final['number'],16)>=int(receipt['blockNumber'],16) else 'confirmed'
    result={'receipt':receipt,'businessState':'effect_unverified'}
    if int(block['timestamp'],16)<payload['created']-5:state='invalid';result['businessState']='outside_review_window'
    elif int(receipt['status'],16)!=1:state='failed';result['businessState']='reverted'
    else:
        summary=payload['summary'];args=payload['args'];current=account(row['wallet'],summary['portfolioType'],args.get('market'),receipt['blockNumber']);result['account']=current
        if row['kind']=='create' and current['portfolio']!=s.ZERO:result['businessState']='portfolio_created'
        elif row['kind']=='cancel' and summary['orderId'] not in current.get('pendingOrderIds',[]):result['businessState']='cancelled'
        elif row['kind'] in {'deposit','withdraw'}:
            expected_delta=v.raw(summary['amount'],6)*(1 if row['kind']=='deposit' else -1)
            source,destination=(row['wallet'],current['portfolio']) if expected_delta>0 else (current['portfolio'],row['wallet'])
            matched=any(log.get('address','').lower()==AUSD and len(log.get('topics',[]))==3 and log['topics'][0].lower()=='0x'+keccak(text='Transfer(address,address,uint256)').hex() and '0x'+log['topics'][1][-40:].lower()==source and '0x'+log['topics'][2][-40:].lower()==destination and int(log.get('data','0x0'),16)==abs(expected_delta) for log in receipt.get('logs',[]) if not log.get('removed'))
            if matched and int(current['balanceRaw'])-int(payload['before']['balanceRaw'])==expected_delta:result['businessState']='credited' if expected_delta>0 else 'withdrawn'
        elif row['kind'] in {'order','close'}:
            matching=[]
            for log in receipt.get('logs',[]):
                if log.get('removed') or log.get('address','').lower()!=TRADING or len(log.get('topics',[]))!=4:continue
                event=next(f for f in abi('Trading') if f.get('type')=='event' and f['name']=='TakerOrderExecuted')
                signature='0x'+keccak(text=event['name']+'('+','.join(v.typ(x) for x in event['inputs'])+')').hex()
                if log['topics'][0].lower()!=signature or '0x'+log['topics'][2][-40:].lower()!=current['portfolio'] or int(log['topics'][3],16)!=instrument(summary['marketId'])[0]:continue
                side,kind,price,book,volume=decode(['uint8','uint8','uint256','uint256','uint256'],bytes.fromhex(log['data'][2:]))
                bound=v.raw(summary['limit'],6)
                if side==(1 if summary['direction']=='long' else 2) and price>0 and ((side==1 and price<=bound) or (side==2 and price>=bound)):matching.append(book+volume)
            size=sum(matching)
            if 0<size<=int(summary['sizeRaw']):
                result['businessState']='filled' if size==int(summary['sizeRaw']) else 'partial_fill';result['executedSizeRaw']=str(size)
                if row['kind']=='close' and size==int(summary['sizeRaw']) and current['position']['state']!=1 and int(current['position']['sizeRaw'])==0:result['businessState']='closed'
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(result),row['id']))
