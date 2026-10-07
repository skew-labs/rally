"""Bounded, public deployment checks. Never authorize, sign or submit an order."""
import copy,re,threading,time
from concurrent.futures import ThreadPoolExecutor
import service as s

LOCK=threading.Lock();BUSY=False;CACHE=None;CHECKED=0.0
MAX_AGE=300;RETRY_AGE=30

def check_deployments():
    import route_execution,venues,leverup,drake,pingu,nadfun
    jobs=[(name,lambda name=name:route_execution.version(name)) for name in sorted(route_execution.PROVIDERS-{'Kuru Flow'})]
    jobs += [('Perpl',lambda:venues.pin('perpl')),('Castora',lambda:venues.pin('castora')),('LeverUp',leverup.pin),('Drake',drake.pin),('Pingu',pingu.pin),('nad.fun v1',lambda:nadfun.pin('v1')),('nad.fun v2',lambda:nadfun.pin('v2',True))]
    def one(job):
        name,fn=job;start=time.monotonic()
        try:
            value=fn()
            return {'venue':name,'status':'verified','interfaceAndDeploymentMatch':True,'elapsedMs':round((time.monotonic()-start)*1000)}
        except Exception as error:
            return {'venue':name,'status':'blocked','interfaceAndDeploymentMatch':False,'error':error.code if isinstance(error,s.Problem) else 'deployment_check_unavailable','elapsedMs':round((time.monotonic()-start)*1000)}
    with ThreadPoolExecutor(max_workers=3) as pool:return list(pool.map(one,jobs))

def refresh():
    global CACHE,CHECKED,BUSY
    started=s.now()
    value={'expectedChainId':143,'observedChainId':None,'status':'blocked','network':{'verified':False},'deployments':[],'checkedAt':started,'error':'network_unavailable'}
    try:
        chain=int(s.rpc('eth_chainId',[]),16)
        if chain!=143:raise s.Problem('Wrong mainnet network',503,'wrong_network')
        # Read finality first: on a fast chain the finalized head can otherwise
        # pass an earlier latest snapshot while other RPC readers are running.
        final=s.rpc('eth_getBlockByNumber',['finalized',False]);latest=s.rpc('eth_getBlockByNumber',['latest',False])
        current=s.now()
        if not latest or not final or not 0<int(final['number'],16)<=int(latest['number'],16) or any(not current-120<=int(b['timestamp'],16)<=current+5 or not re.fullmatch(r'0x[0-9a-fA-F]{64}',b['hash']) for b in (latest,final)) or int(final['timestamp'],16)>int(latest['timestamp'],16) or int(final['number'],16)==int(latest['number'],16) and final['hash'].lower()!=latest['hash'].lower():
            raise s.Problem('Current mainnet finality unavailable',503,'network_unavailable')
        deployments=check_deployments()
        value={'expectedChainId':143,'observedChainId':chain,'status':'verified' if all(d['interfaceAndDeploymentMatch'] for d in deployments) else 'partial','network':{'verified':True,'latestBlock':int(latest['number'],16),'latestTime':int(latest['timestamp'],16),'finalizedBlock':int(final['number'],16),'finalizedHash':final['hash']},'deployments':deployments,'checkedAt':s.now(),'startedAt':started}
    except Exception as error:
        value={'expectedChainId':143,'observedChainId':None,'status':'blocked','network':{'verified':False},'deployments':[],'checkedAt':s.now(),'error':error.code if isinstance(error,s.Problem) else 'network_unavailable'}
    finally:
        with LOCK:CACHE=value;CHECKED=time.monotonic();BUSY=False
    return copy.deepcopy(value)

def status():
    global BUSY
    with LOCK:
        result=copy.deepcopy(CACHE) if CACHE is not None else {'expectedChainId':143,'observedChainId':None,'status':'checking','network':{'verified':False},'deployments':[],'checkedAt':None}
        ttl=RETRY_AGE if CACHE and CACHE['status']=='blocked' else MAX_AGE
        due=CACHE is None or time.monotonic()-CHECKED>=ttl
        if due and not BUSY:
            BUSY=True;threading.Thread(target=refresh,daemon=True,name='rally-mainnet-readonly').start()
        checking=BUSY
    import perp_universe,stocks
    perps=perp_universe.catalog()
    result.update(stale=due and result['checkedAt'] is not None,checking=checking,refreshSeconds=ttl,verificationScope='deployment_and_public_market_reads',walletSubmissionRequired=True,financialTransactionsByThisCheck=0)
    result['perpetuals']=[{**{k:v[k] for k in ('venue','state','total','reason','observedAt') if k in v},'stale':s.now()-v.get('observedAt',0)>60} for v in perps['sources']]
    result['stocks']={'venue':'Anchored','partnerConfigured':stocks.configured(),'status':'contract_review_required' if stocks.configured() else 'partner_required','contractReviewRequired':True}
    result['acceptance']={'spot':'owner_wallet_fill_and_delivery_pending','perpetuals':'owner_wallet_position_and_withdrawal_pending','nadfun':'owner_wallet_buy_sell_launch_pending','predictions':'eligible_open_pool_and_owner_wallet_pending','paidAlgorithms':'buyer_transfer_creator_receipt_access_pending','rwa':'issuer_eligibility_and_redemption_separate'}
    return result
