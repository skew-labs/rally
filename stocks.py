"""Anchored partner API. No server signing, broadcasting, or delegated execution."""
import hashlib,hmac,json,os,time,uuid,threading
from decimal import Decimal,InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
import service as s

BASE='https://rwa-api.anchored.finance/rwa/trading'
ROUTER='0x4f090d817fd83753988a7b0c1d76f170f8461be8'
CACHE=None;AT=0;LOCK=threading.Lock()
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise s.Problem('Stock provider redirected this authenticated request',502,'stock_provider_unavailable')
CLIENT=build_opener(NoRedirect())

def configured():return bool(os.environ.get('RALLY_ANCHORED_KEY') and os.environ.get('RALLY_ANCHORED_SECRET'))

def auth(method,path,query=None,body=None,timestamp=None,nonce=None):
    uri=path+('?' + urlencode(sorted(query.items())) if query else '')
    raw='' if body is None else json.dumps(body,separators=(',',':'),ensure_ascii=False)
    ts=str(timestamp if timestamp is not None else int(time.time()*1000));nonce=nonce or str(uuid.uuid4())
    payload='\n'.join([method.upper(),uri,ts,nonce,raw])
    signature=hmac.new(os.environ.get('RALLY_ANCHORED_SECRET','').encode(),payload.encode(),hashlib.sha256).hexdigest()
    return uri,raw,{'Content-Type':'application/json','x-api-key':os.environ.get('RALLY_ANCHORED_KEY',''),'x-api-ts':ts,'x-api-nonce':nonce,'x-api-sign':signature,'x-api-chain-id':'143','x-api-p':'Anchored'}

def request(method,path,query=None,body=None):
    if not configured():raise s.Problem('Stock trading is awaiting partner activation',503,'stock_partner_required')
    if not path.startswith('/api/v1/') or '/send' in path:raise s.Problem('Unsupported provider operation')
    uri,raw,headers=auth(method,path,query,body)
    req=Request(BASE+uri,data=raw.encode() if body is not None else None,headers=headers,method=method)
    try:
        with CLIENT.open(req,timeout=15) as response:data=json.loads(response.read(2000000))
    except HTTPError as exc:
        if exc.code in {401,403}:raise s.Problem('Stock partner access or server IP is not approved',503,'stock_partner_access_denied')
        raise s.Problem('Stock provider could not complete this request',502,'stock_provider_unavailable')
    except Exception:raise s.Problem('Stock provider is unavailable',503,'stock_provider_unavailable')
    # Never surface raw provider errors, headers, or key-scoped metadata.
    if not isinstance(data,dict) or 'data' not in data or data.get('success') is False or data.get('code') not in {None,0,'0',200,'200'}:raise s.Problem('Stock provider rejected this request',502,'stock_request_rejected')
    return data['data']

def catalog():
    global CACHE,AT
    if not configured():return {'venue':'Anchored','chainId':143,'status':'partner_required','orderStatus':'contract_review_required','symbols':[],'fetchedAt':None}
    with LOCK:
        if CACHE and s.now()-AT<30:return CACHE
        symbols=request('GET','/api/v1/symbols');config=request('GET','/api/v1/config')
        fee=config.get('exchangeFeeConfig',{})
        if fee.get('chainId')!=143 or fee.get('productType')!='Anchored':raise s.Problem('Stock provider returned another market',502,'stock_scope_mismatch')
        if not isinstance(symbols,list):raise s.Problem('Stock catalog format changed',502)
        items=[]
        for item in symbols:
            address=str(item.get('contractAddress','')).lower()
            if not s.re.fullmatch(r'0x[0-9a-f]{40}',address) or not isinstance(item.get('onChainDecimals'),int) or not 0<=item['onChainDecimals']<=18:continue
            fields=['symbol','contractSymbol','contractName','onChainDecimals','tradable','fractionable','price','change24HPercent','logoUrl','lastUpdateTimestamp','name','pdfUrl','volume24H']
            items.append({**{f:item.get(f) for f in fields},'contractAddress':address})
        CACHE={'venue':'Anchored','chainId':143,'status':'market_data_connected','orderStatus':'contract_review_required','symbols':items,'config':config,'fetchedAt':s.now()};AT=s.now();return CACHE

def portfolio(who):
    user=s.require(who,human=True);wallet=s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
    if not wallet:raise s.Problem('Connect your wallet first',409,'wallet_required')
    result=request('GET','/api/v1/users/'+wallet+'/balance',{'spenderAddress':ROUTER})
    if result.get('chainId')!=143 or result.get('productType')!='Anchored' or str(result.get('address','')).lower()!=wallet:raise s.Problem('Stock balance identity mismatch',502,'stock_scope_mismatch')
    return result

def order_intent(who,data):
    user=s.require(who,human=True);wallet=s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
    if not wallet:raise s.Problem('Connect your wallet first',409,'wallet_required')
    stock=next((x for x in catalog()['symbols'] if x['contractAddress']==str(data.get('stock','')).lower()),None)
    if not stock or not stock['tradable']:raise s.Problem('Stock is not currently tradable',409)
    if data.get('side') not in {'Buy','Sell'} or data.get('type') not in {'Market','Limit'}:raise s.Problem('Invalid stock order')
    args={'stockAddress':stock['contractAddress'],'side':data['side'],'type':data['type'],'deadline':s.now()+90,'deferred':False}
    for field in (['notional'] if data['type']=='Market' and data['side']=='Buy' else ['quantity','price'] if data['type']=='Limit' else ['quantity']):
        try:
            value=Decimal(str(data.get(field,'')))
            if not value.is_finite() or value<=0 or value>1000000 or len(str(value))>60:raise ValueError()
        except (InvalidOperation,ValueError):raise s.Problem('Enter a valid '+field)
        args[field]=format(value,'f')
    if data['type']=='Limit':args['timeInForce']='DAY'
    unsigned=request('POST','/api/v1/orders/calldata',body=args)
    if unsigned.get('chainId')!=143 or unsigned.get('productType')!='Anchored' or str(unsigned.get('toAddress','')).lower()!=ROUTER or str(unsigned.get('value'))!='0' or unsigned.get('method')!=('placeMarketOrder' if data['type']=='Market' else 'placeLimitOrder'):raise s.Problem('Stock transaction identity mismatch',502,'stock_transaction_mismatch')
    # Published linked contract repository and ABI return 404. A target address and
    # method label do not prove calldata economics. Fail closed before wallet approval.
    s.audit('stock.unsigned_intent',who,stock['contractAddress'])
    return {'status':'contract_review_required','intent':args,'wallet':wallet,'chainId':143,'message':'Trading will open after the provider contract interface is verified.'}
