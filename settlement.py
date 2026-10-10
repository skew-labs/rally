"""Prepaid feed access with receipt-verified creator revenue allocations."""
from decimal import Decimal,InvalidOperation
from eth_utils import keccak
from eth_abi import decode
import json
import service as s
import wallet_execution

PERIOD=30*86400
TRANSFER_TOPIC='0x'+keccak(text='Transfer(address,address,uint256)').hex()

def initialize():
    with s.connection() as db:
        columns={x[1] for x in db.execute('PRAGMA table_info(feeds)')}
        for name,definition in [('price_raw',"TEXT NOT NULL DEFAULT '0'"),('recipient','TEXT'),('version','INTEGER NOT NULL DEFAULT 1')]:
            if name not in columns:db.execute('ALTER TABLE feeds ADD COLUMN '+name+' '+definition)
        db.executescript('''
        CREATE TABLE IF NOT EXISTS invoices(id TEXT PRIMARY KEY,buyer TEXT,feed TEXT,version INTEGER,wallet TEXT,recipient TEXT,amount_raw TEXT,created INTEGER,expires INTEGER,tx TEXT UNIQUE,state TEXT,receipt TEXT,settled INTEGER);
        CREATE TABLE IF NOT EXISTS entitlements(buyer TEXT,feed TEXT,version INTEGER,expires INTEGER,PRIMARY KEY(buyer,feed,version));
        CREATE INDEX IF NOT EXISTS invoices_pending ON invoices(state,created);
        CREATE INDEX IF NOT EXISTS invoices_buyer ON invoices(buyer,created);
        ''')
        if 'community_terms' not in {x[1] for x in db.execute('PRAGMA table_info(invoices)')}:
            db.execute('ALTER TABLE invoices ADD COLUMN community_terms TEXT')

def allowed(feed,user):
    if feed['owner']==user or bool(user and s.one('SELECT 1 FROM entitlements WHERE buyer=? AND feed=? AND version=? AND expires>?',(user,feed['id'],feed['version'],s.now()))):return True
    benefit=__import__('token_benefits').access(feed,user)
    return benefit if benefit is not None else not int(feed.get('price_raw') or '0')

def view(feed,user):
    access=allowed(feed,user)
    pricing=__import__('token_benefits').price(feed,user)
    ent=s.one('SELECT expires FROM entitlements WHERE buyer=? AND feed=? AND version=?',(user or '',feed['id'],feed['version']))
    owner=s.one('SELECT handle,name FROM accounts WHERE id=?',(feed['owner'],))
    token=__import__('nad_revenue').public(feed) or __import__('community_tokens').public(feed['owner'])
    return {'algorithm_version':feed.get('algorithm_version'),'formula':(s.one('SELECT expression FROM algorithm_versions WHERE id=?',(feed.get('algorithm_version'),)) or {}).get('expression') if access else None,**{k:feed[k] for k in ['id','owner','name','created','version']},'creator':owner,'weights':json.loads(feed['weights']) if access else None,'assets':json.loads(feed['assets']) if access else [],'price':s.units(int(pricing['amountRaw']),6),'priceRaw':pricing['amountRaw'],'holderDiscountBps':pricing['discountBps'],'originalPriceRaw':pricing['originalRaw'],'currency':'USDC','periodDays':30,'access':access,'accessExpires':ent['expires'] if ent and ent['expires']>s.now() else None,'recipient':feed['recipient'],'creatorShareBps':10000-(token['buybackBps'] if token else 0),'communityToken':token,'autoRenew':False}

def price(value):
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0 or amount>10000 or amount*1_000_000!=int(amount*1_000_000):raise ValueError()
        if amount and amount<Decimal('0.1'):raise ValueError()
        return str(int(amount*1_000_000))
    except (InvalidOperation,ValueError,OverflowError):raise s.Problem('Choose a price from 0.10 to 10,000 USDC, or 0 for a free feed')

def checkout(who,data):
    user=s.require(who,human=True)
    f=s.one('SELECT * FROM feeds WHERE id=?',(data.get('feed'),))
    if not f:raise s.Problem('Feed not found',404)
    if not int(f['price_raw']) or f['owner']==user:raise s.Problem('This feed does not need a payment')
    wallet=s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
    if not wallet:raise s.Problem('Connect your wallet to pay',409,'wallet_required')
    if not f['recipient'] or f['recipient']==s.ZERO:raise s.Problem('Creator payment address unavailable',409)
    terms=__import__('nad_revenue').route(f) or __import__('community_tokens').route(f)
    recipient=terms['vault'] if terms else f['recipient']
    amount=__import__('token_benefits').price(f,user)['amountRaw']
    ident=s.uid();created=s.now()
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute("SELECT * FROM invoices WHERE buyer=? AND feed=? AND version=? AND wallet=? AND (state IN ('submitted','confirmed') OR (state='awaiting_payment' AND expires>?)) ORDER BY created DESC LIMIT 1",(user,f['id'],f['version'],wallet,created)).fetchone()
        if existing and not existing['tx'] and (existing['recipient']!=recipient or existing['amount_raw']!=amount or json.loads(existing['community_terms'] or 'null')!=terms):
            db.execute("UPDATE invoices SET state='expired' WHERE id=?",(existing['id'],));existing=None
        if existing:ident=existing['id']
        else:db.execute('INSERT INTO invoices(id,buyer,feed,version,wallet,recipient,amount_raw,created,expires,state,community_terms) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,user,f['id'],f['version'],wallet,recipient,amount,created,created+900,'awaiting_payment',s.dump(terms) if terms else None))
    s.audit('feed.checkout',who,ident)
    return invoice(who,ident)

def owned(who,ident):
    user=s.require(who,human=True)
    row=s.one('SELECT * FROM invoices WHERE id=? AND buyer=?',(ident,user))
    if not row:raise s.Problem('Payment not found',404)
    return row

def terms(row):return json.loads(row.get('community_terms') or 'null')

def calldata(row):
    t=terms(row)
    if t:
        import community_tokens as ct
        return ct.call('pay',['bytes32','bytes32','uint256','uint64'],[ct.word(row['id']),ct.word(row['feed']),int(row['amount_raw']),t['policyNonce']])
    return '0xa9059cbb'+row['recipient'][2:].rjust(64,'0')+hex(int(row['amount_raw']))[2:].rjust(64,'0')

def allocation(row):
    t=terms(row);gross=int(row['amount_raw']);reserved=gross*t['buybackBps']//10000 if t else 0
    return {'settlementKind':'community_vault' if t else 'direct','communityTerms':t,'creatorRecipient':t['creator'] if t else row['recipient'],'creatorShareBps':10000-(t['buybackBps'] if t else 0),'creatorAmount':s.units(gross-reserved,6),'buybackAmount':s.units(reserved,6)}

def invoice(who,ident):
    row=owned(who,ident)
    f=s.one('SELECT name FROM feeds WHERE id=?',(row['feed'],))
    ent=s.one('SELECT expires FROM entitlements WHERE buyer=? AND feed=? AND version=?',(row['buyer'],row['feed'],row['version']))
    return {'id':row['id'],'feed':row['feed'],'feedName':f['name'],'version':row['version'],'amount':s.units(int(row['amount_raw']),6),'amountRaw':row['amount_raw'],'currency':'USDC','token':s.USDC,'recipient':row['recipient'],'wallet':row['wallet'],'chainId':143,'created':row['created'],'expires':row['expires'],'state':row['state'] if row['tx'] or s.now()<=row['expires'] else 'expired','tx':row['tx'],'periodDays':30,'accessExpires':ent['expires'] if ent else None,**allocation(row),'autoRenew':False,'receipt':json.loads(row['receipt']) if row['receipt'] else None}

def prepare(who,data):
    row=owned(who,data.get('invoice'))
    current=s.one('SELECT wallet FROM accounts WHERE id=?',(row['buyer'],))['wallet']
    if row['wallet']!=current:raise s.Problem('The connected wallet changed. Start a new checkout.',409)
    if row['tx'] or row['state']!='awaiting_payment':raise s.Problem('This payment already has a transaction',409)
    if row['expires']<s.now():raise s.Problem('Checkout expired. Start a new checkout.',409)
    feed=s.one('SELECT * FROM feeds WHERE id=?',(row['feed'],))
    if not feed or feed['version']!=row['version'] or __import__('token_benefits').price(feed,row['buyer'])['amountRaw']!=row['amount_raw']:
        raise s.Problem('The subscription price changed. Start a fresh checkout.',409,'price_changed')
    balance=s.rpc('eth_call',[{'to':s.USDC,'data':'0x70a08231'+row['wallet'][2:].rjust(64,'0')},'latest'])
    if int(balance,16)<int(row['amount_raw']):raise s.Problem('Not enough USDC in this wallet',409,'insufficient_balance')
    t=terms(row)
    if t:
        import community_tokens as ct
        if t.get('kind')=='nad_revenue':__import__('nad_revenue').verify_terms(t)
        else:
            ct.pin()
            if ct.read(t['vault'],'policyNonce',outs=['uint64'])!=t['policyNonce']:raise s.Problem('Creator allocation changed. Start a fresh checkout.',409,'policy_changed')
        if ct.read(s.USDC,'allowance',['address','address'],[row['wallet'],t['vault']])<int(row['amount_raw']):
            approval,cost=ct.gas({'from':row['wallet'],'to':s.USDC,'data':ct.call('approve',['address','uint256'],[t['vault'],int(row['amount_raw'])]),'value':'0x0','chainId':'0x8f'})
            return {'invoice':invoice(who,row['id']),'approval':approval,'estimatedGasCostMON':cost}
    tx={'from':row['wallet'],'to':t['vault'] if t else s.USDC,'data':calldata(row),'value':'0x0','chainId':'0x8f'}
    gas=s.rpc('eth_estimateGas',[{k:v for k,v in tx.items() if k!='chainId'}])
    gas_limit=(int(gas,16)*120+99)//100
    fee=gas_limit*int(s.rpc('eth_gasPrice',[]),16)
    if int(s.rpc('eth_getBalance',[row['wallet'],'latest']),16)<fee:raise s.Problem('Add MON to cover network fees',409,'insufficient_gas')
    tx['gas']=hex(gas_limit)
    return {'invoice':invoice(who,row['id']),'transaction':tx,'estimatedGasCostMON':s.units(fee,18)}

def record(who,data):
    row=owned(who,data.get('invoice'));tx=str(data.get('tx','')).lower()
    if not s.re.fullmatch(r'0x[0-9a-f]{64}',tx):raise s.Problem('Invalid transaction hash')
    if row['tx']:
        if row['tx']!=tx:raise s.Problem('This payment already uses another transaction',409)
    else:
        observed=s.rpc('eth_getTransactionByHash',[tx])
        if not observed:raise s.Problem('Transaction is not indexed yet. Retry the same hash.',409,'transaction_pending')
        target=row['recipient'] if terms(row) else s.USDC
        wallet_execution.verified_call(tx,{'from':row['wallet'],'to':target,'data':calldata(row),'value':'0x0'},observed)
        try:
            with s.connection() as db:
                updated=db.execute('UPDATE invoices SET tx=?,state=? WHERE id=? AND tx IS NULL',(tx,'submitted',row['id'])).rowcount
                if not updated and db.execute('SELECT tx FROM invoices WHERE id=?',(row['id'],)).fetchone()['tx']!=tx:raise s.Problem('This payment already uses another transaction',409)
        except s.sqlite3.IntegrityError:raise s.Problem('Transaction has already paid another checkout',409)
    reconcile(row['id'])
    return invoice(who,row['id'])

def reconcile(ident):
    row=s.one('SELECT * FROM invoices WHERE id=?',(ident,))
    if not row or not row['tx'] or row['state'] in {'paid','failed','invalid'}:return
    receipt=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not receipt:return
    block=s.rpc('eth_getBlockByNumber',[receipt['blockNumber'],False])
    if not block or block.get('hash','').lower()!=receipt.get('blockHash','').lower():return
    final=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not final or int(final['number'],16)<int(receipt['blockNumber'],16):
        s.write('UPDATE invoices SET state=?,receipt=? WHERE id=?',('confirmed',s.dump(receipt),ident));return
    if int(receipt['status'],16)!=1:
        s.write('UPDATE invoices SET state=?,receipt=? WHERE id=?',('failed',s.dump(receipt),ident));return
    when=int(block['timestamp'],16)
    logs=[log for log in receipt.get('logs',[]) if (log.get('address') or '').lower()==s.USDC and not log.get('removed') and len(log.get('topics',[]))==3 and log['topics'][0].lower()==TRANSFER_TOPIC and '0x'+log['topics'][1][-40:].lower()==row['wallet'] and '0x'+log['topics'][2][-40:].lower()==row['recipient'] and int(log.get('data','0x0'),16)==int(row['amount_raw'])]
    # Preparation expires; a transfer already approved in the wallet can land
    # later. Honor the exact payment instead of taking funds without access.
    valid=len(logs)==1 and when>=row['created']-5
    t=terms(row)
    if valid and t:
        import community_tokens as ct
        events=[l for l in receipt.get('logs',[]) if not l.get('removed') and l.get('address','').lower()==t['vault'] and len(l.get('topics',[]))==4 and l['topics'][0].lower()==ct.REVENUE_TOPIC and l['topics'][1].lower()=='0x'+ct.word(row['id']).hex() and l['topics'][2].lower()=='0x'+ct.word(row['feed']).hex() and '0x'+l['topics'][3][-40:].lower()==row['wallet']]
        reserved=int(row['amount_raw'])*t['buybackBps']//10000;payout=int(row['amount_raw'])-reserved
        valid=len(events)==1
        if valid:
            try:valid=decode(['uint256','uint256','uint256','uint64'],bytes.fromhex(events[0]['data'][2:]))==(int(row['amount_raw']),payout,reserved,t['policyNonce'])
            except Exception:valid=False
        if valid and payout:
            paid=[l for l in receipt.get('logs',[]) if not l.get('removed') and l.get('address','').lower()==s.USDC and len(l.get('topics',[]))==3 and l['topics'][0].lower()==TRANSFER_TOPIC and '0x'+l['topics'][1][-40:].lower()==t['vault'] and '0x'+l['topics'][2][-40:].lower()==t['creator'] and int(l.get('data','0x0'),16)==payout]
            valid=len(paid)==1
    if not valid:
        s.write('UPDATE invoices SET state=?,receipt=? WHERE id=?',('invalid',s.dump(receipt),ident));return
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        check=db.execute('SELECT settled FROM invoices WHERE id=?',(ident,)).fetchone()
        if check['settled']:return
        ent=db.execute('SELECT expires FROM entitlements WHERE buyer=? AND feed=? AND version=?',(row['buyer'],row['feed'],row['version'])).fetchone()
        until=max(when,ent['expires'] if ent else 0)+PERIOD
        db.execute('INSERT INTO entitlements VALUES(?,?,?,?) ON CONFLICT(buyer,feed,version) DO UPDATE SET expires=excluded.expires',(row['buyer'],row['feed'],row['version'],until))
        db.execute('UPDATE invoices SET state=?,receipt=?,settled=? WHERE id=?',('paid',s.dump(receipt),s.now(),ident))

def history(who):
    user=s.require(who,human=True)
    purchases=[invoice(who,x['id']) for x in s.rows('SELECT id FROM invoices WHERE buyer=? ORDER BY created DESC LIMIT 50',(user,))]
    payouts=s.rows("SELECT i.id,i.feed,f.name feedName,i.version,i.amount_raw,i.recipient,i.tx,i.settled,i.community_terms FROM invoices i JOIN feeds f ON f.id=i.feed WHERE f.owner=? AND i.state='paid' ORDER BY i.settled DESC LIMIT 50",(user,))
    return {'purchases':purchases,'payouts':[{**p,**allocation(p),'amount':allocation(p)['creatorAmount'],'grossAmount':s.units(int(p['amount_raw']),6),'currency':'USDC'} for p in payouts]}

def approval_check(who,data):
    row=owned(who,data.get('invoice'));t=terms(row)
    if not t:raise s.Problem('This checkout does not need an allowance')
    tx=str(data.get('tx') or '').lower()
    if not s.re.fullmatch('0x[0-9a-f]{64}',tx):raise s.Problem('Invalid transaction hash')
    observed=s.rpc('eth_getTransactionByHash',[tx])
    if not observed:return {'state':'pending','tx':tx}
    try:r=wallet_execution.approval_receipt(tx,row['wallet'],s.USDC,t['vault'],row['amount_raw'],observed)
    except s.Problem as error:
        if error.code=='transaction_pending':return {'state':'pending','tx':tx}
        raise
    return {'state':'confirmed' if int(r['status'],16)==1 else 'failed','tx':tx}
