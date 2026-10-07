"""V2 creator/gift claims. Public API is discovery; contract call gates authority."""
import json,threading,time
from eth_abi import decode
from eth_utils import keccak
import service as s,nadfun as n,launchpad as lp,venues as v

CLAIM='0x'+keccak(text='Claim(address,address,uint256)').hex()
TRANSFER=n.TRANSFER
CACHE={};LOCK=threading.Lock()

def target(kind):
    if kind not in {'creator_claim','gift_claim'}:raise s.Problem('Choose creator or beneficiary fees')
    return lp.pins()['creatorFeeVault' if kind=='creator_claim' else 'giftVault']['address']

def checked(token,wallet,kind):
    token=n.address(token);lp.pin_allocations({'creator' if kind=='creator_claim' else 'gift':10000})
    info=n.token_info(token)
    if info['version']!='v2':raise s.Problem('These claims are for nad.fun V2 tokens',409)
    vault=target(kind)
    if kind=='creator_claim':
        recipient=n.simple(vault,'getCreator',['address'],[token],['address'])
        amount=n.simple(vault,'getBalance',['address'],[token])
        if recipient!=wallet:raise s.Problem('This wallet is not the fee recipient',403)
    else:
        # The official indexer lists tokens associated with the registered wallet.
        # That list cannot authorize withdrawal: the actual claim is simulated
        # from this exact wallet before a plan is returned or signed.
        listing=n.api('/profile/gift-fee/'+wallet+'?page=1&limit=100')
        item=next((x for x in listing.get('tokens',[]) if str(x.get('token_info',{}).get('token_id','')).lower()==token and x.get('token_info',{}).get('version')=='V2'),None)
        reward=item.get('reward_info',{}) if item else {}
        raw=str(reward.get('amount','0'))
        amount=int(raw) if raw.isdigit() and len(raw)<=78 else 0
        if not reward.get('claimable'):raise s.Problem('Verify the beneficiary and recipient wallet on nad.fun before claiming',409,'gift_verification_required')
        recipient=wallet
    if amount<=0:raise s.Problem('No settled fees available to claim',409,'no_claimable_fees')
    tx={'from':wallet,'to':vault,'data':__import__('community_tokens').call('claim',['address'],[token]),'value':'0x0','chainId':'0x8f'}
    s.rpc('eth_call',[{k:x for k,x in tx.items() if k!='chainId'},'latest'])
    return info,amount,tx

def status(who,refresh=False):
    user,wallet=v.wallet(who)
    with LOCK:
        cache=CACHE.get(wallet)
        if not refresh and cache and time.monotonic()-cache[0]<30:return cache[1]
    items=[];errors=[]
    for row in s.rows('SELECT token FROM launch_tokens WHERE owner=? AND wallet=? ORDER BY created DESC LIMIT 20',(user,wallet)):
        try:
            token=row['token'];vault=target('creator_claim');lp.pin_allocations({'creator':10000})
            recipient=n.simple(vault,'getCreator',['address'],[token],['address']);amount=n.simple(vault,'getBalance',['address'],[token])
            t=n.token_info(token,False)
            if recipient==wallet:
                item={'token':token,'name':t['name'],'symbol':t['symbol'],'logoURI':t.get('logoURI'),'kind':'creator_claim','amountRaw':str(amount),'amount':s.units(amount,18),'quoteToken':t['quoteToken'],'currency':'MON' if t['quoteToken']==n.WMON else 'LVMON','claimable':amount>0,'source':'CreatorFeeVault.getBalance'}
                if not amount and t.get('pair'):
                    try:
                        item['pendingPoolFees']=s.units(n.read('v2','fees','accumulatedFee',[t['pair']]),18)
                        item['settlementThreshold']=s.units(n.read('v2','fees','settlementThreshold',[t['pair']]),18)
                    except s.Problem:errors.append({'token':token,'state':'venue_settlement_read_unavailable'})
                items.append(item)
        except s.Problem:errors.append({'token':row['token'],'state':'unavailable'})
    try:
        listing=n.api('/profile/gift-fee/'+wallet+'?page=1&limit=20')
        for row in listing.get('tokens',[])[:20]:
            ti=row.get('token_info',{});reward=row.get('reward_info',{})
            if ti.get('version')!='V2':continue
            try:token=n.address(ti.get('token_id'));info=n.token_info(token,False)
            except s.Problem:continue
            raw=str(reward.get('amount','0'))
            if not raw.isdigit() or len(raw)>78:continue
            items.append({'token':token,'name':info['name'],'symbol':info['symbol'],'logoURI':info.get('logoURI'),'kind':'gift_claim','amountRaw':raw,'amount':s.units(int(raw),18),'quoteToken':info['quoteToken'],'currency':'MON' if info['quoteToken']==n.WMON else 'LVMON','claimable':bool(reward.get('claimable')) and int(raw)>0,'source':'nad.fun indexed beneficiary quote; claim authorization checked on-chain'})
    except s.Problem:errors.append({'state':'beneficiary_index_unavailable'})
    result={'wallet':wallet,'chainId':143,'claims':items,'errors':errors,'fetchedAt':s.now(),'verificationURL':'https://nad.fun/profile/'+wallet}
    with LOCK:CACHE[wallet]=(time.monotonic(),result)
    return result

def plan(who,data):
    user,wallet=v.wallet(who);kind=data.get('kind');info,amount,tx=checked(data.get('token'),wallet,kind)
    now=s.now();ident=s.uid();p={'transaction':tx,'approval':None,'args':data,'created':now,'expires':now+90,'pin':s.digest(s.dump(lp.pins())),'summary':{'action':'claim','asset':'MON' if info['quoteToken']==n.WMON else 'LVMON','amount':s.units(amount,18),'amountRaw':str(amount),'token':info['id'],'quoteToken':info['quoteToken'],'recipient':wallet,'claimKind':kind,'version':'v2'}}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',(ident,user,wallet,'nadfees',kind,s.dump(p),p['expires']))
    return {'id':ident,**p}

def prepare(row,p):
    if p['pin']!=s.digest(s.dump(lp.pins())):raise s.Problem('Fee contracts changed. Refresh the claim.',409)
    info,amount,tx=checked(p['summary']['token'],row['wallet'],row['kind'])
    if tx!=p['transaction'] or info['quoteToken']!=p['summary']['quoteToken'] or amount<int(p['summary']['amountRaw']):raise s.Problem('Claim changed. Refresh before signing.',409)

def native_delivery(tx,vault,wallet):
    # The WMON vault can unwrap before payout. Verify the actual internal native
    # transfer; never infer recipient delivery from transaction success alone.
    try:
        trace=s.rpc('debug_traceTransaction',[tx,{'tracer':'callTracer','timeout':'4s'}])
        def walk(node):
            if not isinstance(node,dict) or node.get('error'):return 0
            amount=int(node.get('value','0x0'),16) if node.get('type','').upper()=='CALL' and node.get('from','').lower()==vault and node.get('to','').lower()==wallet else 0
            return amount+sum(walk(child) for child in node.get('calls',[]))
        if isinstance(trace,dict) and trace.get('to','').lower()==vault and not trace.get('error'):return walk(trace)
    except (s.Problem,ValueError,TypeError):pass
    return 0

def reconcile(row):
    p=json.loads(row['payload']);r=s.rpc('eth_getTransactionReceipt',[row['tx']])
    if not r:return
    b=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False]);f=s.rpc('eth_getBlockByNumber',['finalized',False])
    if not b or b['hash'].lower()!=r['blockHash'].lower():return
    state='confirmed' if not f or int(f['number'],16)<int(r['blockNumber'],16) else 'finalized'
    if int(r['status'],16)!=1:state='failed';out={'businessState':'reverted','receipt':r}
    else:
        wallet=p['transaction']['from'];summary=p['summary'];vault=p['transaction']['to'];matches=[]
        for log in r.get('logs',[]):
            if log.get('removed') or log.get('address','').lower()!=summary['quoteToken'] or len(log.get('topics',[]))!=3 or log['topics'][0].lower()!=TRANSFER:continue
            if '0x'+log['topics'][1][-40:].lower()==vault and '0x'+log['topics'][2][-40:].lower()==wallet:matches.append(int(log['data'],16))
        # ERC20 quote delivery is independently evidenced by exact recipient logs.
        # If the venue unwraps MON, retain a receipt for native transfer tracing
        # instead of presenting a successful transaction as a verified payout.
        delivered=sum(matches);native=native_delivery(row['tx'],vault,wallet) if summary['quoteToken']==n.WMON and delivered<int(summary['amountRaw']) else 0
        verified=delivered>=int(summary['amountRaw']) or native>=int(summary['amountRaw'])
        out={'receipt':r,'businessState':'fees_claimed' if verified else 'claim_delivery_verification_pending','recipient':wallet,'quoteToken':summary['quoteToken'],'deliveredRaw':str(delivered),'nativeDeliveredRaw':str(native),'deliveryAsset':'MON' if native>=int(summary['amountRaw']) else ('WMON' if summary['quoteToken']==n.WMON else 'LVMON'),'quotedRaw':summary['amountRaw']}
        if state=='finalized' and verified:
            with LOCK:CACHE.pop(wallet,None)
    s.write('UPDATE execution_records SET state=?,outcome=? WHERE id=?',(state,s.dump(out),row['id']))
