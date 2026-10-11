"""Public Monad swap research and free, first-party discovery feeds.

No financial submission, signing, user impersonation or runtime network reads
while ranking. A bounded remote collector supplies timestamped evidence.
"""
from collections import defaultdict
from decimal import Decimal
import json
import re
import threading
import time
import service as s

ADDRESS=re.compile(r'0x[0-9a-fA-F]{40}\Z')
HASH=re.compile(r'0x[0-9a-fA-F]{64}\Z')
TRANSFER='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
TTL=7200
RECIPES={
    'wallet-reentry':('Wallet Re-entry','40 * wallet_reentry + 4 * watched + recency','New buys after a verified profitable round trip'),
    'wallet-confluence':('Wallet Confluence','40 * wallet_buyers + 4 * following + recency','Tokens bought by multiple researched wallets'),
    'wallet-exits':('Wallet Exit Watch','40 * wallet_exits + 4 * watched + recency','Sell activity from researched wallets'),
}


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS wallet_research_state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT,updated INTEGER);
        CREATE TABLE IF NOT EXISTS wallet_research_receipts(tx TEXT PRIMARY KEY,payload TEXT,created INTEGER);
        ''')
        # First-party curated feeds have a service author, never a third-party
        # identity or an invented human session. Existing versions stay immutable.
        for ident,(name,expression,_) in RECIPES.items():
            version=ident+'-v1'
            db.execute('INSERT OR IGNORE INTO algorithms VALUES(?,?,?,?)',(ident,'rally',name,s.now()))
            db.execute('INSERT OR IGNORE INTO algorithm_versions VALUES(?,?,?,?,?)',(version,ident,1,expression,s.now()))
            db.execute('INSERT OR IGNORE INTO feeds(id,owner,name,weights,assets,created,algorithm_version,price_raw) VALUES(?,?,?,?,?,?,?,?)',(ident,'rally',name+' · v1','[100,0,0]','[]',s.now(),version,'0'))


def snapshot():
    row=s.one('SELECT payload,updated FROM wallet_research_state WHERE id=1')
    if not row:return {'asOf':None,'wallets':[],'signals':{},'markets':[],'state':'collecting','stale':True}
    value=json.loads(row['payload']);value['stale']=s.now()-row['updated']>TTL
    value['state']='stale' if value['stale'] else 'ready'
    return value


def context(feed):
    recipe=RECIPES.get(feed['id'])
    if not recipe:return None
    value=snapshot()
    return {'description':recipe[2],'asOf':value['asOf'],'stale':value['stale'],
            'wallets':len(value['wallets']),'markets':len(value['markets']),
            'activeAssets':len(value.get('signals',{})),
            'source':'Public nad.fun trades + finalized Monad receipts',
            'url':'/api/wallet-research','method':'Sampled market round trips; not a global wallet ranking'}


def feature_map(assets):
    value=snapshot()
    if value['stale']:return {}
    result={}
    for asset in assets:
        if not ADDRESS.fullmatch(str(asset or '')):continue
        signal=value.get('signals',{}).get(asset.lower())
        if not signal:continue
        result[asset]={k:min(1,max(0,float(signal.get(k,0)))) for k in ('wallet_reentry','wallet_buyers','wallet_exits')}
    return result


def public():
    return {**snapshot(),'chainId':143,'price':'0','currency':'MON',
            'method':'Closed sampled nad.fun round trips: canonical finalized receipts, native call-trace cash flows, matched swap gas and zero token inventory at both boundaries. Unknown transfers inside the interval are rejected.',
            'scope':'Sampled markets only. Distinct addresses do not establish independent people. Not all Monad wallets, audited whole-wallet PnL or a strategy backtest. Separate approval and failed-transaction costs outside matched swaps are excluded.',
            'sourceURL':'https://github.com/Naddotfun/api-intergration',
            'recipes':[{'id':i,'name':r[0],'description':r[2],'expression':r[1]} for i,r in RECIPES.items()]}


def native_cash(frame,wallet):
    # DELEGATECALL repeats the inherited msg.value without moving money.
    # Failed child trees have no landed effect, even if caught by a parent.
    if frame.get('error'):return 0
    amount=int(frame.get('value','0x0'),16) if frame.get('type') in {'CALL','CREATE','CREATE2','SELFDESTRUCT'} else 0
    credit=amount if frame.get('to','').lower()==wallet else 0
    debit=amount if frame.get('from','').lower()==wallet else 0
    return credit-debit+sum(native_cash(c,wallet) for c in frame.get('calls',[]))


def token_delta(logs,token,wallet):
    total=0
    for log in logs:
        topics=log.get('topics',[])
        if log.get('removed') or log.get('address','').lower()!=token or len(topics)!=3 or topics[0].lower()!=TRANSFER:continue
        quantity=int(log['data'],16)
        if ('0x'+topics[2][-40:]).lower()==wallet:total+=quantity
        if ('0x'+topics[1][-40:]).lower()==wallet:total-=quantity
    return total


def cycles(cohort):
    """Candidate selection only. Provider fields do not establish realized PnL."""
    candidates=[]
    for market in cohort:
        token=market['token']['address'].lower()
        if market['token'].get('quoteToken','').lower()!='0x3bd359c1119da7da1d913d1c4d2b7c461115433a':continue
        wallets=defaultdict(list)
        for item in market['swaps']:
            wallets[item['account_info']['account_id'].lower()].append(item)
        for wallet,items in wallets.items():
            quantity=0;trades=[];seen=set()
            for item in sorted(items,key=lambda r:(r['swap_info']['created_at'],r['swap_info']['transaction_hash'])):
                swap=item['swap_info'];tx=swap['transaction_hash']
                if tx in seen:continue
                seen.add(tx);amount=int(swap['token_amount'])
                if amount<=0:continue
                if swap['event_type']=='BUY':quantity+=amount;trades.append(item)
                elif swap['event_type']=='SELL' and quantity>=amount:
                    quantity-=amount;trades.append(item)
                    if quantity==0:
                        reported=sum((Decimal(t['swap_info']['value'])*(1 if t['swap_info']['event_type']=='SELL' else -1) for t in trades),Decimal(0))
                        if reported>0 and 2<=len(trades)<=12:
                            candidates.append({'wallet':wallet,'token':token,'symbol':market['token']['symbol'],'trades':trades,'reportedUSD':str(reported)})
                        trades=[]
                else:quantity=0;trades=[]
    return sorted(candidates,key=lambda c:Decimal(c['reportedUSD']),reverse=True)


def evidence(tx):
    if not HASH.fullmatch(tx):raise ValueError('Invalid transaction')
    row=s.one('SELECT payload FROM wallet_research_receipts WHERE tx=?',(tx,))
    if row:return json.loads(row['payload'])
    receipt=s.rpc('eth_getTransactionReceipt',[tx])
    if not receipt or receipt.get('status')!='0x1':raise ValueError('Receipt not successful')
    trace=s.rpc('debug_traceTransaction',[tx,{'tracer':'callTracer'}])
    value={'receipt':receipt,'trace':trace}
    s.write('INSERT OR IGNORE INTO wallet_research_receipts VALUES(?,?,?)',(tx,s.dump(value),s.now()))
    s.write('DELETE FROM wallet_research_receipts WHERE tx NOT IN (SELECT tx FROM wallet_research_receipts ORDER BY created DESC,tx DESC LIMIT 256)')
    return value


def verify(candidate,finalized):
    wallet=candidate['wallet'];token=candidate['token'];events=[]
    for item in candidate['trades']:
        swap=item['swap_info'];ev=evidence(swap['transaction_hash']);r=ev['receipt'];trace=ev['trace']
        if r.get('status')!='0x1' or r.get('transactionHash','').lower()!=swap['transaction_hash'].lower() or r.get('from','').lower()!=wallet or trace.get('from','').lower()!=wallet or trace.get('error') or trace.get('type')!='CALL':raise ValueError('Receipt identity changed')
        block=int(r['blockNumber'],16)
        if block>finalized:raise ValueError('Not finalized')
        canonical=s.rpc('eth_getBlockByNumber',[r['blockNumber'],False])
        if not canonical or canonical['hash'].lower()!=r['blockHash'].lower():raise ValueError('Noncanonical receipt')
        delta=token_delta(r['logs'],token,wallet)
        expected=int(swap['token_amount'])*(1 if swap['event_type']=='BUY' else -1)
        if delta!=expected:raise ValueError('Provider token amount differs from landed amount')
        # Multi-asset cash flow must not be attributed entirely to this token.
        other_assets={l.get('address','').lower() for l in r['logs'] if len(l.get('topics',[]))==3 and l['topics'][0].lower()==TRANSFER}
        for other in other_assets-{token,'0x3bd359c1119da7da1d913d1c4d2b7c461115433a'}:
            if token_delta(r['logs'],other,wallet):raise ValueError('Other token cash flows require separate accounting')
        cash=native_cash(trace,wallet);gas=int(r['gasUsed'],16)*int(r['effectiveGasPrice'],16)
        if cash>=0 and expected>0 or cash<=0 and expected<0:raise ValueError('Cash direction does not match swap')
        events.append({'tx':swap['transaction_hash'],'block':block,'index':int(r['transactionIndex'],16),'time':int(canonical['timestamp'],16),'cash':cash,'gas':gas,'delta':delta})
    events.sort(key=lambda e:(e['block'],e['index']))
    first=events[0]['block'];last=events[-1]['block']
    if last-first>50000:raise ValueError('Round trip exceeds the bounded log window')
    data='0x70a08231'+wallet[2:].rjust(64,'0')
    if any(int(s.rpc('eth_call',[{'to':token,'data':data},hex(block)]),16)!=0 for block in (first-1,last)):raise ValueError('Inventory boundary is not zero')
    topic='0x'+wallet[2:].rjust(64,'0');known={e['tx'].lower() for e in events}
    # The configured Monad provider caps a log request at 1,000 blocks.
    for start in range(first,last+1,1000):
        for topics in ([TRANSFER,topic],[TRANSFER,None,topic]):
            logs=s.rpc('eth_getLogs',[{'address':token,'fromBlock':hex(start),'toBlock':hex(min(last,start+999)),'topics':topics}])
            if not isinstance(logs,list) or len(logs)>1000:raise ValueError('Transfer history exceeds the bound')
            if any(l.get('removed') or l['transactionHash'].lower() not in known for l in logs):raise ValueError('Unknown transfer inside the round trip')
    net=sum(e['cash']-e['gas'] for e in events)
    if net<=0:raise ValueError('Round trip is not profitable after matched swap gas')
    spent=sum(-e['cash']+e['gas'] for e in events if e['delta']>0)
    return {'wallet':wallet,'token':token,'symbol':candidate['symbol'],'pnlMON':s.units(net,18),
            'costMON':s.units(spent,18),'returnPct':str(Decimal(net)*100/Decimal(spent)),
            'closedAt':events[-1]['time'],'holdingSeconds':events[-1]['time']-events[0]['time'],
            'transactions':[e['tx'] for e in events],'profileURL':'https://nad.fun/profile/'+wallet,
            'verification':'finalized_closed_round_trip','currency':'MON'}


def build(cohort,verified,stamp):
    by_wallet=defaultdict(list)
    for row in verified:by_wallet[row['wallet']].append(row)
    rankings=[]
    for wallet,rows in by_wallet.items():
        total=sum((Decimal(r['pnlMON']) for r in rows),Decimal(0))
        rankings.append({'wallet':wallet,'pnlMON':format(total,'f'),'roundTrips':len(rows),
                         'latestClose':max(r['closedAt'] for r in rows),'profileURL':'https://nad.fun/profile/'+wallet,'trades':rows})
    rankings.sort(key=lambda r:Decimal(r['pnlMON']),reverse=True)
    rankings=rankings[:10];tracked={w['wallet']:w['latestClose'] for w in rankings};signals={}
    for market in cohort:
        buyers=set();sellers=set();reentry=set();activity=[];seen=set()
        for item in market['swaps']:
            swap=item['swap_info'];wallet=item['account_info']['account_id'].lower();when=swap['created_at'];tx=swap['transaction_hash']
            if wallet not in tracked or not stamp-86400<=when<=stamp or tx in seen:continue
            seen.add(tx)
            if swap['event_type']=='BUY':
                buyers.add(wallet)
                if when>tracked[wallet]:reentry.add(wallet)
            elif swap['event_type']=='SELL':sellers.add(wallet)
            activity.append({'wallet':wallet,'side':swap['event_type'],'time':when,'tx':tx,'source':'nad.fun public swap history','finality':'provider_observation'})
        if activity:
            token=market['token']['address'].lower()
            signals[token]={'wallet_buyers':min(1,len(buyers)/3),'wallet_reentry':min(1,len(reentry)/3),'wallet_exits':min(1,len(sellers)/3),'activity':sorted(activity,key=lambda a:a['time'],reverse=True)[:25]}
    return {'asOf':stamp,'wallets':rankings,'signals':signals,
            'markets':[{'address':c['token']['address'],'symbol':c['token']['symbol'],'sourceCount':c['total'],'sampleCount':len(c['swaps']),'completeProviderHistory':c['complete']} for c in cohort],
            'selection':'Six recent markets by holder count and six leading markets by reference market cap. Up to 400 public swaps per market, at most 12 swaps and 50,000 blocks per verified round trip.',
            'window':'Latest collected swaps; each verified round trip shows its own observation interval',
            'concentration':{'tokens':len({t['token'] for w in rankings for t in w['trades']}),'note':'A short profitable round trip does not establish repeatable skill; distinct addresses may have common control.'}}


def save(value):
    if not value.get('wallets'):raise ValueError('No verified profitable round trips; preserve the previous snapshot')
    s.write('INSERT INTO wallet_research_state VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',(s.dump(value),value['asOf']))


def collect():
    import nadfun
    tokens=[json.loads(r['info']) for r in s.rows('SELECT info FROM nad_tokens ORDER BY coalesce(json_extract(info,"$.created"),0) DESC LIMIT 100')]
    cap=[json.loads(r['info']) for r in s.rows('SELECT info FROM nad_tokens WHERE coalesce(json_extract(info,"$.marketCap"),0)>0 ORDER BY CAST(json_extract(info,"$.marketCap") AS REAL) DESC LIMIT 6')]
    selected=sorted(tokens,key=lambda t:t.get('holders') or 0,reverse=True)[:6]+cap
    cohort=[];seen=set()
    for token in selected:
        addr=token['address'].lower()
        if addr in seen:continue
        seen.add(addr)
        try:
            first=nadfun.api('/trade/swap-history/'+addr+'?page=1&limit=100&direction=DESC')
            rows=first['swaps'];total=first['total_count']
            if total<=400:
                for page in range(2,(total+99)//100+1):rows+=nadfun.api('/trade/swap-history/'+addr+f'?page={page}&limit=100&direction=DESC')['swaps']
            cohort.append({'token':token,'swaps':rows,'total':total,'complete':len(rows)==total})
        except Exception:continue
    candidates=cycles(cohort);verified=[]
    final=int(s.rpc('eth_getBlockByNumber',['finalized',False])['number'],16)
    for candidate in candidates[:20]:
        try:verified.append(verify(candidate,final))
        except Exception:continue
    if verified:save(build(cohort,verified,s.now()))
    return {'markets':len(cohort),'candidates':len(candidates),'verified':len(verified)}


def background():
    # Provider requests never block the public feed or order path.
    while True:
        value=snapshot()
        if value.get('asOf') and s.now()-value['asOf']<3600:
            time.sleep(max(1,3600-(s.now()-value['asOf'])));continue
        try:collect()
        except Exception:pass
        time.sleep(3600)
