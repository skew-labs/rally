"""Rally application server. Loopback by default; production origin is explicit."""
import base64
import gzip
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import service as s
import settlement
import venues
import stocks
import journey
import nadfun
import launchpad
import launch_activity
import launch_fees,nad_revenue
import social, algorithms, oauth_sessions, route_quotes, route_execution, wallet_auth, media_pipeline, privy_auth, agent_wallet
import ipaddress
import market_data, route_stream, market_universe, perp_universe, spot_prices
import mainnet_status
import transaction_preflight
import community_tokens
import discovery
import app_assets
import token_images
from serve import candles

PORT=int(os.environ.get('RALLY_PORT','4186'))
ORIGIN=os.environ.get('RALLY_PUBLIC_ORIGIN',f'http://127.0.0.1:{PORT}').rstrip('/')
PUBLIC_ORIGINS={ORIGIN,*filter(None,os.environ.get('RALLY_COMPAT_ORIGINS','').split(','))}
for allowed in PUBLIC_ORIGINS:
    parsed=urlsplit(allowed)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:raise RuntimeError('Invalid public origin configuration')
HOST_ORIGINS={urlsplit(value).netloc:value for value in PUBLIC_ORIGINS}
HOST_ORIGINS.update({f'127.0.0.1:{PORT}':ORIGIN,f'localhost:{PORT}':ORIGIN})
HOSTS=set(HOST_ORIGINS)
SECURE=ORIGIN.startswith('https://')
CDN_BASE=os.environ.get('RALLY_CDN_BASE','').rstrip('/')
if CDN_BASE and not re.fullmatch(r'https://cdn\.rallydot\.com/v/[0-9a-f]{16}',CDN_BASE):raise RuntimeError('Invalid public CDN configuration')
RATE={};RATE_LOCK=threading.Lock()
STATIC_CACHE={};STATIC_LOCK=threading.Lock()


def schema(properties,required=()):return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
STRING={'type':'string'}
TOOLS=[
    {'name':'feed.read','description':'Read public Rally posts with cursor pagination.','inputSchema':schema({'mode':STRING,'feed':STRING,'cursor':STRING}), 'annotations':{'readOnlyHint':True}},
    {'name':'posts.publish','description':'Publish a post as your owned connected agent. Media must be uploaded first. Use a stable request_id for retries.','inputSchema':schema({'text':STRING,'asset':STRING,'media':STRING,'community':STRING,'parent':STRING,'request_id':STRING},['request_id']), 'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True}},
    {'name':'posts.edit','description':'Edit your own post using its current version number.','inputSchema':schema({'id':STRING,'text':STRING,'version':{'type':'integer'}},['id','text','version'])},
    {'name':'media.upload','description':'Upload a small image or video up to 40 KB using base64. For larger files use media.prepare_upload.','inputSchema':schema({'mime':STRING,'base64':STRING},['mime','base64'])},
    {'name':'media.prepare_upload','description':'Get a short-lived single-use upload URL. PUT file bytes with the correct Content-Type, then use the returned media id in posts.publish.','inputSchema':schema({}), 'annotations':{'readOnlyHint':False,'destructiveHint':False}},
    {'name':'markets.search','description':'Read verified Monad token identities and pool prices. A price is not a trade quote.','inputSchema':schema({'query':STRING}), 'annotations':{'readOnlyHint':True}},
    {'name':'profile.read','description':'Read your connected agent profile.','inputSchema':schema({}),'annotations':{'readOnlyHint':True}},
]


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.settimeout(30)
    def log_message(self,*args):pass  # Never log bearer tokens, upload URLs, OAuth codes or wallet signatures.
    def response(self,data,status=200,headers=None,mime='application/json'):
        body=data if isinstance(data,bytes) else s.dump(data).encode() if mime=='application/json' else data.encode()
        if mime=='application/json' and status==200 and self.command=='GET' and urlsplit(self.path).path in {'/api/bootstrap','/api/posts','/api/markets','/api/market-prices','/api/market-catalog','/api/perps','/api/predictions','/api/market-chart','/api/nadfun/tokens','/api/launchpad/tokens','/api/launchpad/activity','/api/discover','/api/discover/preview','/api/performance/leaderboard'} and len(body)>1500 and re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',self.headers.get('Accept-Encoding','')):
            body=gzip.compress(body,compresslevel=5,mtime=0);headers={**(headers or {}),'Content-Encoding':'gzip','Vary':'Accept-Encoding'}
        self.send_response(status)
        lengths={'Content-Length':str(len(body))} if status!=304 else {}
        for k,v in {'Content-Type':mime,**lengths,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin','X-Frame-Options':'SAMEORIGIN',**(headers or {})}.items():self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def who(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:pass
        token=cookie.get('rally_session')
        bearer=self.headers.get('Authorization','')
        return s.identity(token.value if token else '',bearer[7:] if bearer.startswith('Bearer ') else '')
    def public_origin(self):
        return HOST_ORIGINS.get(self.headers.get('Host'),ORIGIN)
    def agent_device(self):
        try:return SimpleCookie(self.headers.get('Cookie','')).get(agent_wallet.COOKIE).value
        except (AttributeError,ValueError):return ''
    def agent_cookie(self,ticket,max_age=30*86400):
        return agent_wallet.COOKIE+'='+ticket+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(max_age)+('; Secure' if SECURE else '')
    def guard(self,write=False):
        if self.headers.get('Host') not in HOSTS:raise s.Problem('Unknown host',403)
        origin=self.headers.get('Origin')
        if origin and origin not in {self.public_origin(),f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}:raise s.Problem('Request origin is not allowed',403)
        public_write=urlsplit(self.path).path in {'/oauth/token','/oauth/register','/oauth/revoke'} or self.path.startswith('/upload/')
        if write and not self.headers.get('Authorization') and not public_write and self.headers.get('X-Rally-Request')!='1':raise s.Problem('Request verification required',403)
        if write:
            address=self.client_address[0]
            # nginx replaces this header with its observed remote address.
            if address in {'127.0.0.1','::1'} and self.headers.get('X-Forwarded-Proto')=='https':
                try:address=str(ipaddress.ip_address(self.headers.get('X-Forwarded-For','')))
                except ValueError:pass
            key=(address,urlsplit(self.path).path)
            maximum=10 if '/auth/' in key[1] else 120
            with RATE_LOCK:
                entries=[t for t in RATE.get(key,[]) if time.monotonic()-t<60]
                if len(entries)>=maximum:raise s.Problem('Too many requests. Try again shortly.',429)
                RATE[key]=entries+[time.monotonic()]
    def body(self,limit=65536):
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:raise s.Problem('Invalid request size')
        if length<0 or length>limit:raise s.Problem('Request too large',413)
        return self.rfile.read(length)
    def data(self):
        raw=self.body()
        try:
            if self.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded'):return {k:v[0] for k,v in parse_qs(raw.decode()).items()}
            value=json.loads(raw or b'{}')
            if not isinstance(value,dict):raise ValueError()
            return value
        except Exception:raise s.Problem('Invalid request body')
    def fail(self,error):
        if isinstance(error,s.Problem):self.response({'error':error.code,'message':str(error)},error.status,{'WWW-Authenticate':'Bearer resource_metadata="'+self.public_origin()+'/.well-known/oauth-protected-resource"'} if error.status==401 else None)
        else:self.response({'error':'service_error','message':'Could not complete this request. Try again.'},500)
    def do_GET(self):
        try:self.guard();self.get()
        except Exception as error:self.fail(error)
    def do_HEAD(self):self.do_GET()
    def get(self):
        u=urlsplit(self.path);path=u.path;params={k:v[0] for k,v in parse_qs(u.query).items()};who=self.who()
        if path=='/api/health':return self.response({'ok':True,'storage':'sqlite','messages':False,'rpc':{'provider':'QuickNode' if (urlsplit(s.RPC_URL).hostname or '').endswith('.quiknode.pro') else 'Public Monad' if s.RPC_URL=='https://rpc.monad.xyz' else 'Configured RPC','networkVerified':bool(s.RPC_CHECKED_AT and time.monotonic()-s.RPC_CHECKED_AT<300)}})
        if path=='/api/auth/config':return self.response({'privy':privy_auth.config(),'agentWallet':agent_wallet.config(who,self.agent_device(),self.public_origin())})
        if path=='/api/agent-wallet/config':return self.response(agent_wallet.config(who,self.agent_device(),self.public_origin()))
        if path=='/api/agent-wallet/request':return self.response(agent_wallet.status(who,self.agent_device(),self.public_origin(),params.get('id')))
        if path=='/api/community-tokens/config':return self.response(community_tokens.config())
        if path=='/api/community-tokens/me':return self.response(community_tokens.status(s.require(who,human=True)))
        if path=='/api/creator/earnings':
            import creator
            return self.response(creator.overview(who,params.get('period','all')))
        if path=='/api/community-deployment/me':
            import community_deployment
            return self.response(community_deployment.status(s.require(who,human=True)))
        if path=='/.well-known/oauth-protected-resource':return self.response({'resource':self.public_origin()+'/mcp','authorization_servers':[self.public_origin()],'scopes_supported':sorted(s.SCOPES)})
        if path in {'/.well-known/oauth-authorization-server','/.well-known/openid-configuration'}:
            origin=self.public_origin()
            return self.response({'issuer':origin,'authorization_endpoint':origin+'/authorize','token_endpoint':origin+'/oauth/token','registration_endpoint':origin+'/oauth/register','response_types_supported':['code'],'grant_types_supported':['authorization_code','refresh_token'],'revocation_endpoint':origin+'/oauth/revoke','code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['none'],'scopes_supported':sorted(s.SCOPES)})
        if path=='/api/algorithms':return self.response(algorithms.listing(who))
        if path=='/api/discover':
            data=discovery.catalog(who,params)
            for item in data['items']:item['cover']=token_images.ready(item.get('cover')) or item.get('cover')
            return self.response(data)
        if path=='/api/discover/preview':return self.response(discovery.preview(who,params.get('id','')))
        if path=='/api/performance/leaderboard':return self.response(discovery.leaderboard(who,params))
        if path=='/api/algorithms/leaderboard':return self.response(algorithms.leaderboard(who))
        if path=='/api/search':return self.response(social.search(who,params.get('q','')))
        if path=='/api/notifications':return self.response(social.notices(who))
        if path=='/api/blocks':
            user=s.require(who,human=True)
            return self.response({'profiles':[s.profile(r['target']) for r in s.rows('SELECT target FROM blocks WHERE owner=?',(user,))]})
        if path=='/api/reports':
            user=s.require(who,human=True)
            return self.response({'reports':s.rows('SELECT id,post,reason,status,created FROM reports WHERE owner=? ORDER BY created DESC LIMIT 50',(user,))})
        if path=='/api/mainnet':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(mainnet_status.status())
        if path=='/api/bootstrap':
            data=s.bootstrap(who,include_markets=params.get('markets')!='0');data['auth']['agentWallet']=agent_wallet.config(who,self.agent_device(),self.public_origin());return self.response(data)
        if path=='/api/posts':return self.response(s.get_feed(who,params))
        if path=='/api/feed':return self.response(journey.preview(who,params))
        if path=='/api/activity':return self.response(journey.activity(who))
        if path=='/api/connections/status':return self.response(journey.connection_status(who))
        if path=='/api/post':
            if who and who['grant']:s.require(who,'feed:read')
            post=social.post(params.get('id'),who['user'] if who else None)
            if not post:raise s.Problem('Post not found',404)
            return self.response(s.post_view(post,who['actor'] if who else None))
        if path=='/api/replies':
            if who and who['grant']:s.require(who,'feed:read')
            social.post(params.get('post'),who['user'] if who else None)
            return self.response({'posts':[s.post_view(x,who['actor'] if who else None) for x in s.rows('SELECT * FROM posts WHERE parent=? AND deleted=0 ORDER BY created',(params.get('post'),)) if social.visible(who['user'] if who else None,x['author'])][:100]})
        if path=='/api/profile':return self.response(s.profile(params.get('id',''),who['user'] if who else None))
        if path=='/api/market-catalog':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(market_universe.catalog(params))
        if path=='/api/market-prices':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(market_universe.references(params.get('assets','')))
        if path=='/api/market-asset':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(market_universe.resolve(params.get('address')))
        if path=='/api/markets':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(s.GATEWAY.markets())
        if path.startswith('/api/launchpad/'):
            if who and who['grant']:s.require(who,'markets:read')
            if path=='/api/launchpad/activity':return self.response(launch_activity.overview(who,params.get('period','30d'),params.get('token'),params.get('limit','50')))
            if path=='/api/launchpad/tokens':return self.response(launchpad.catalog(who))
            if path=='/api/launchpad/token':return self.response(launchpad.detail(params.get('token'),who))
            if path=='/api/launchpad/config':return self.response(launchpad.config())
            if path=='/api/launchpad/me':return self.response(launchpad.me(who))
            if path=='/api/launchpad/fees':return self.response(launch_fees.status(who,params.get('refresh')=='1'))
            if path=='/api/launchpad/revenue':return self.response(nad_revenue.status(who,params.get('token')))
        if path.startswith('/api/nadfun/'):
            if who and who['grant']:s.require(who,'markets:read')
            if path=='/api/nadfun/tokens':
                data=nadfun.catalog(params.get('phase'),params.get('sort','latest'));token_images.decorate(data['tokens']);return self.response(data)
            if path=='/api/nadfun/token':
                data=nadfun.token_info(params.get('token'));token_images.decorate([data]);return self.response(data)
            if path=='/api/nadfun/chart':return self.response(nadfun.chart(params.get('token'),params.get('interval','60')))
            if path=='/api/nadfun/config':return self.response({'chainId':143,'version':'v2','creationFeeMON':s.units(nadfun.creation_fee(),18),'creatorFeeBps':100,'initialBuy':'0','quoteAsset':'MON','fetchedAt':s.now()})
            if path=='/api/nadfun/drafts':return self.response(nadfun.drafts(who))
        if path=='/api/perps':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(s.GATEWAY.perps())
        if path=='/api/perpl/account':return self.response(venues.perpl_status(who))
        if path=='/api/drake/account':
            import drake
            return self.response(drake.status(who,params.get('portfolioType','imp'),params.get('market')))
        if path=='/api/pingu/account':
            import pingu
            return self.response(pingu.status(who))
        if path=='/api/leverup/positions':
            import leverup
            return self.response(leverup.positions(who,params.get('market','')))
        if path=='/api/predictions':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(venues.predictions())
        if path=='/api/predictions/mine':return self.response(venues.my_predictions(who,params.get('offset',0)))
        if path=='/api/executions':
            user=s.require(who,human=True)
            for item in s.rows("SELECT id FROM execution_records WHERE user_id=? AND state IN ('submitted','confirmed') ORDER BY created DESC LIMIT 3",(user,)):
                try:venues.reconcile(item['id'])
                except s.Problem:pass
            return self.response(venues.history(who))
        if path=='/api/stocks':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(stocks.catalog())
        if path=='/api/stocks/portfolio':return self.response(stocks.portfolio(who))
        if path=='/api/market-chart':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(market_data.chart(params.get('asset',''),params.get('kind','spot'),params.get('period','1D')))
        if path=='/api/routes/status':return self.response(route_stream.status(who,params.get('id','')))
        if path=='/api/pool-chart':return self.response(s.GATEWAY.pool_chart(params.get('asset','')))
        if path=='/api/venues':
            with (s.ROOT/'config/venue-inventory.csv').open(encoding='utf-8-sig') as handle:items=list(s.csv.DictReader(handle))
            connected={'kuru','perpl','castora','kyberswap','uniswap','pancakeswap','lfj','nadfun','nad-fun','purps','leverup','octoswap'}
            coverage={'pancakeswap':'V2 and v3 pools','lfj':'V1 ERC20 paths and v2.2 pools without custom hooks','uniswap':'V2 and v3 pools','purps':'V2 exact-input paths','kyberswap':'Aggregator routes','leverup':'25 Monad POOL markets; USDC open and full-close requests; native collateral unverified','octoswap':'V1 and v2 exact-input paths','drake_exchange':'5 markets; owner portfolios, order, cancel and full-close adapter','pingu_exchange':'71 markets; protected requests, cancellation and keeper event reconciliation'}
            with perp_universe.LOCK:
                states={key:dict(perp_universe.CACHE.get(name,{})) for key,name in [('drake_exchange','Drake'),('pingu_exchange','Pingu')]}
            import extra_routes, v2_routes
            return self.response({'venues':[{'id':x['registry_key'],'name':x['name'],'categories':x['categories'].split(';'),'url':x['project_url'],'docs':x['docs_url'],'status':states.get(x['registry_key'],{}).get('state','wallet_flow_connected' if x['registry_key'] in connected else 'access_required'),'coverage':coverage.get(x['registry_key']),'blocker':states.get(x['registry_key'],{}).get('reason','Funded execution acceptance pending' if x['registry_key'] in connected else x['unverified_or_blocker'])} for x in items], 'additionalRoutes':extra_routes.capabilities()+[{'provider':p,'chainId':143,'referenceQuotes':True,'unsignedExecution':True,'walletRequiredForExecution':True,'fundedExecutionVerified':False,'routes':'V2 direct or two-hop paths' if p!='LFJ v1' else 'V1 ERC20 direct or two-hop paths'} for p in sorted(v2_routes.PROVIDERS)]})
        if path=='/api/orders':
            user=s.require(who,human=True)
            return self.response({'orders':s.rows('SELECT id,quote_id,tx,state,receipt,created FROM orders WHERE user_id=? ORDER BY created DESC LIMIT 50',(user,))})
        if path=='/api/portfolio':return self.response(self.portfolio(who))
        if path=='/api/payments':return self.response(settlement.history(who))
        if path=='/api/payment':
            row=settlement.owned(who,params.get('id'))
            if row['tx'] and row['state'] in {'submitted','confirmed'}:settlement.reconcile(row['id'])
            return self.response(settlement.invoice(who,row['id']))
        if path=='/api/export':
            user=s.require(who,human=True)
            return self.response({'version':1,'exportedAt':s.now(),'profile':s.profile(user,user),'agentProfiles':[s.profile(a['id'],user) for a in s.rows('SELECT id FROM accounts WHERE owner=?',(user,))], 'posts':[s.post_view(p,user) for p in s.rows('SELECT * FROM posts WHERE deleted=0 AND (author=? OR author IN (SELECT id FROM accounts WHERE owner=?))',(user,user))], 'follows':[p['target'] for p in s.rows('SELECT target FROM follows WHERE user_id=?',(user,))], 'saved':[p['post'] for p in s.rows("SELECT post FROM reactions WHERE user_id=? AND kind='save'",(user,))], 'watchlist':[t['asset'] for t in s.rows('SELECT asset FROM watches WHERE user_id=?',(user,))]},headers={'Content-Disposition':'attachment; filename="rally-data.json"'})
        if path=='/api/chart':return self.response(candles(params.get('asset',''),params.get('interval','60')))
        if path=='/api/oauth/request':
            if params.get('resource') and params['resource']!=self.public_origin()+'/mcp':raise s.Problem('Unknown requested resource')
            client=s.one('SELECT * FROM clients WHERE id=?',(params.get('client_id'),))
            if not client or params.get('redirect_uri') not in json.loads(client['redirects']) or params.get('code_challenge_method')!='S256' or params.get('response_type')!='code' or not re.fullmatch(r'[A-Za-z0-9_-]{43}',params.get('code_challenge','')):raise s.Problem('Invalid connection request')
            scopes=set(params.get('scope','feed:read posts:write media:upload').split())
            if not scopes<=s.SCOPES or not scopes:raise s.Problem('Invalid requested permissions')
            return self.response({'client':client['name'],'scopes':sorted(scopes)})
        if path.startswith('/media/'):
            ident,_,suffix=path.removeprefix('/media/').partition('/');m=s.one('SELECT * FROM media WHERE id=?',(ident,))
            public=community_tokens.public_image(ident) or any(social.visible(who['user'] if who else None,p['author']) for p in s.rows('SELECT author FROM posts WHERE media=? AND deleted=0',(ident,)))
            if not m or not(public or who and who['user']==m['owner']):raise s.Problem('Media not found',404)
            if suffix=='status':return self.response(media_pipeline.describe(ident))
            target,mime=media_pipeline.delivery(ident,suffix)
            return self.file(target,mime)
        if path=='/mcp':return self.response({'error':'method_not_allowed'},405,{'Allow':'POST'})
        if path=='/app/':return self.response(b'',302,{'Location':'/app'+('?' + u.query if u.query else '')},'text/plain')
        if path in {'/app','/authorize'} or path=='/' and any(k in params for k in ('view','tab','id','market','phase')):return self.file(s.ROOT/'index.html','text/html; charset=utf-8')
        if path=='/':return self.file(s.ROOT/'landing.html','text/html; charset=utf-8')
        # Do not expose database, secrets, source Python, logs or research directories.
        if not path.startswith('/assets/') and path not in {'/landing.js','/landing.css','/live-app.js','/finance.js','/flow.js','/charts.js','/nadfun.js','/community.js','/community.css','/social.css','/ui.css','/checkout.js','/checkout.css','/feed-ui.js','/feed.css','/market-ui.js','/market-logos.js','/market.css','/theme.js','/live.css','/flow.css','/nadfun.css','/favicon.ico','/swipe.js','/swipe-trade.js','/swipe.css','/swipe-motion.js','/auth-ui.js','/auth.css','/community-token.js','/community-token.css','/creator-ui.js','/launchpad.js','/launch-activity.js','/launch-income.js','/launchpad.css','/experience.js','/experience.css','/motion.js','/design.css'}:raise s.Problem('File not found',404)
        if not re.fullmatch(r'/(?:assets/(?:(?:tokens|venues|auth)/)?[A-Za-z0-9_.-]+|[A-Za-z0-9_-]+\.(?:js|css)|favicon\.ico)',path):raise s.Problem('Page not found',404)
        target=(s.ROOT/path.lstrip('/')).resolve()
        if not target.is_relative_to(s.ROOT) or not target.is_file():raise s.Problem('File not found',404)
        import mimetypes
        return self.file(target,mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    def file(self,path,mime):
        # Private media stays uncached and retains permission checks on every read.
        public=path.is_relative_to(s.ROOT) and not path.is_relative_to(s.STATE)
        text=public and (path.suffix in {'.html','.css','.js','.svg'})
        if text and not self.headers.get('Range'):
            stat=path.stat();compressed=bool(re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',self.headers.get('Accept-Encoding','')))
            bundle=app_assets.current(s.ROOT) if path.name=='index.html' else None
            key=(str(path),stat.st_mtime_ns,stat.st_size,compressed,s.dump(bundle) if bundle else '')
            with STATIC_LOCK:
                value=STATIC_CACHE.get(key)
                if value is None:
                    raw=path.read_bytes()
                    if bundle:
                        raw=app_assets.html(raw.decode(),bundle).encode()
                    elif path.name in {'index.html','landing.html'} and CDN_BASE:
                        html=raw.decode()
                        for name in ['landing.js','landing.css','live-app.js','charts.js','finance.js','flow.js','nadfun.js','community.js','live.css','flow.css','nadfun.css','community.css','social.css','ui.css','checkout.js','checkout.css','feed-ui.js','feed.css','market-ui.js','market.css','theme.js','swipe.js','swipe.css','swipe-motion.js','motion.js']:
                            html=html.replace('./'+name,CDN_BASE+'/'+name)
                        if path.name=='landing.html':html=html.replace('./assets/',CDN_BASE+'/assets/')
                        html=html.replace('</head>','<link rel="preconnect" href="https://cdn.rallydot.com" crossorigin /><meta name="rally-cdn" content="'+CDN_BASE+'" /></head>')
                        if path.name=='index.html':
                            # Publish reviewed module changes independently of the
                            # immutable CDN bundle; other assets retain the CDN.
                            changed=('live-app.js','finance.js','market-ui.js','community.js','swipe.js','swipe-trade.js','swipe-motion.js','flow.js','market-logos.js','nadfun.js','checkout.js','auth-ui.js','community-token.js','creator-ui.js','launchpad.js','launch-activity.js','launch-income.js','experience.js','motion.js')
                            imports={CDN_BASE+'/'+name:'/'+name+'?v='+s.digest((s.ROOT/name).read_text())[:16] for name in changed}
                            for name in ('live-app.js','charts.js','finance.js','flow.js','nadfun.js','community.js','swipe.js','swipe-trade.js','checkout.js','feed-ui.js','market-ui.js','market-logos.js','swipe-motion.js','auth-ui.js','community-token.js','creator-ui.js','launchpad.js','launch-activity.js','launch-income.js','experience.js','motion.js'):
                                imports['/'+name]=imports.get(CDN_BASE+'/'+name,CDN_BASE+'/'+name)
                            for name in changed:
                                for attr in ('href','src'):html=html.replace(attr+'="'+CDN_BASE+'/'+name+'"',attr+'="'+imports[CDN_BASE+'/'+name]+'"')
                            for name in ('swipe.css','feed.css','ui.css','market.css','checkout.css'):
                                html=html.replace('href="'+CDN_BASE+'/'+name+'"','href="/'+name+'?v='+s.digest((s.ROOT/name).read_text())[:16]+'"')
                            html=html.replace('href="/experience.css"','href="/experience.css?v='+s.digest((s.ROOT/'experience.css').read_text())[:16]+'"')
                            html=html.replace('href="/design.css"','href="/design.css?v='+s.digest((s.ROOT/'design.css').read_text())[:16]+'"')
                            html=html.replace('href="/launchpad.css"','href="/launchpad.css?v='+s.digest((s.ROOT/'launchpad.css').read_text())[:16]+'"')
                            html=html.replace('<head>','<head><script type="importmap">'+s.dump({'imports':imports})+'</script>')
                        raw=html.encode()
                    body=gzip.compress(raw,compresslevel=6,mtime=0) if compressed else raw
                    value=(body,'"'+hashlib.sha256(body).hexdigest()[:24]+'"')
                    if len(STATIC_CACHE)>=48:STATIC_CACHE.clear()
                    STATIC_CACHE[key]=value
            body,etag=value
            immutable=bool(re.fullmatch(r'rally-app-[0-9a-f]{20}\.(?:js|css)',path.name)) and hashlib.sha256(path.read_bytes()).hexdigest()[:20] in path.name
            headers={'Cache-Control':'no-store' if path.suffix=='.html' else 'public,max-age=31536000,immutable' if immutable else 'public,max-age=0,must-revalidate','Vary':'Accept-Encoding','ETag':etag}
            if compressed:headers['Content-Encoding']='gzip'
            if path.suffix!='.html' and self.headers.get('If-None-Match')==etag:
                return self.response(b'',304,headers,mime)
            return self.response(body,headers=headers,mime=mime)
        total=path.stat().st_size;start=0;end=total-1;status=200
        range_header=self.headers.get('Range','')
        if range_header:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',range_header)
            if not match:raise s.Problem('Unsupported range',416)
            start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
            if start>end:raise s.Problem('Range not available',416)
            status=206
        headers={'Content-Length':str(end-start+1),'Content-Type':mime,'Accept-Ranges':'bytes','X-Content-Type-Options':'nosniff','Cache-Control':'public,max-age=3600' if path.parent.name=='assets' else 'no-store'}
        if status==206:headers['Content-Range']=f'bytes {start}-{end}/{total}'
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,v)
        self.end_headers()
        if self.command=='HEAD':return
        with path.open('rb') as handle:
            handle.seek(start);remaining=end-start+1
            while remaining:
                data=handle.read(min(remaining,65536));self.wfile.write(data);remaining-=len(data)
    def do_POST(self):
        try:self.guard(write=True);self.post()
        except Exception as error:self.fail(error)
    def do_PUT(self):
        try:
            self.guard(write=True);who=self.who()
            if self.path.startswith('/upload/'):
                ticket=s.one('SELECT * FROM uploads WHERE hash=? AND used=0 AND expires>?',(s.digest(self.path.removeprefix('/upload/')),s.now()))
                if not ticket:raise s.Problem('Upload link expired',401)
                if ticket['grant_id'] and not s.one('SELECT 1 FROM grants WHERE id=? AND owner=? AND agent=? AND revoked=0 AND expires>?',(ticket['grant_id'],ticket['owner'],ticket['actor'],s.now())):raise s.Problem('Connection revoked',401)
                if not s.write('UPDATE uploads SET used=1 WHERE hash=? AND used=0',(ticket['hash'],)):raise s.Problem('Upload already used',409)
                who={'user':ticket['owner'],'actor':ticket['actor'],'scopes':{'media:upload'},'grant':ticket['grant_id']}
            elif self.path!='/api/media':raise s.Problem('Upload endpoint not found',404)
            s.require(who,'media:upload')
            return self.response(s.upload_file(who,self.body(25*1024*1024),self.headers.get('Content-Type','').split(';')[0]))
        except Exception as error:self.fail(error)
    def post(self):
        path=urlsplit(self.path).path;who=self.who();data=self.data()
        if path.startswith('/api/community-deployment/'):
            import community_deployment
            action=path.rsplit('/',1)[-1]
            if action not in {'plan','prepare','record'}:raise s.Problem('Deployment action not found',404)
            return self.response(getattr(community_deployment,action)(who,data))
        if path=='/api/discover/alerts':return self.response(discovery.alerts(who,data))
        if path=='/api/discover/performance-sharing':return self.response(discovery.share_performance(who,data))
        if path.removeprefix('/api/') in {'auth/recover','auth/recovery-codes','post/edit','post/report','post/repost','block','notifications/read'}:return self.response(social.action(path.removeprefix('/api/'),who,data))
        if path.startswith('/api/algorithms/'):return self.response(algorithms.action(path.removeprefix('/api/'),who,data))
        if path=='/api/routes':return self.response(route_stream.compare(who,data) if data.get('progressive') is True else route_quotes.compare(who,data))
        if path=='/api/routes/select':return self.response(route_quotes.select(who,data))
        if path=='/api/nadfun/draft':return self.response(nadfun.draft(who,data,self.headers.get('Idempotency-Key','')))
        if path=='/api/launchpad/register':return self.response(launchpad.register(who,data))
        if path=='/api/launchpad/revenue/limits':return self.response(nad_revenue.limits(who,data))
        if path=='/api/launchpad/revenue/bind':return self.response(nad_revenue.bind(who,data))
        if path=='/api/nadfun/quote':
            if who and who['grant']:s.require(who,'markets:read')
            return self.response(nadfun.quote(data.get('token'),data.get('kind'),data.get('amount'),data.get('slippage',100)))
        if path=='/api/auth/wallet/challenge':return self.response(wallet_auth.challenge(data,self.public_origin()))
        if path=='/api/agent-wallet/prepare':return self.response(agent_wallet.prepare(who,self.agent_device(),self.public_origin()))
        if path=='/api/agent-wallet/start':return self.response(agent_wallet.start(who,self.agent_device(),self.public_origin(),data))
        if path=='/api/agent-wallet/complete':
            result,token,ticket=agent_wallet.complete(who,self.agent_device(),self.public_origin(),str(data.get('id','')))
            body=s.dump(result).encode();self.send_response(200)
            for k,v in {'Content-Type':'application/json','Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}.items():self.send_header(k,v)
            if ticket:self.send_header('Set-Cookie',self.agent_cookie(ticket))
            if token:self.send_header('Set-Cookie','rally_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if SECURE else ''))
            self.end_headers();self.wfile.write(body);return
        if path=='/api/agent-wallet/disconnect':return self.response(agent_wallet.disconnect(who,self.public_origin()),headers={'Set-Cookie':self.agent_cookie('',0)})
        if path=='/api/auth/privy':
            profile,token,max_age=privy_auth.login(who,data)
            return self.response({'me':profile},headers={'Set-Cookie':'rally_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age='+str(max_age)+('; Secure' if SECURE else '')})
        if path=='/api/auth/wallet/verify':
            profile,token=wallet_auth.verify(data,self.public_origin())
            return self.response({'me':profile},headers={'Set-Cookie':'rally_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if SECURE else '')})
        if path in {'/api/auth/register','/api/auth/login'}:
            profile,token=s.login(data,path.endswith('register'))
            return self.response({'me':profile},201 if path.endswith('register') else 200,{'Set-Cookie':'rally_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if SECURE else '')})
        if path=='/api/auth/logout':
            cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie.get('rally_session')
            if token:s.write('DELETE FROM sessions WHERE hash=?',(s.digest(token.value),))
            return self.response({'ok':True},headers={'Set-Cookie':'rally_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'+('; Secure' if SECURE else '')})
        if path=='/api/wallet/challenge':
            return self.response(wallet_auth.link_challenge(who,data,self.public_origin()))
        if path=='/api/wallet/verify':
            from eth_account import Account
            from eth_account.messages import encode_defunct
            user=s.require(who,human=True);challenge=s.one('SELECT * FROM challenges WHERE id=? AND user_id=? AND used=0 AND expires>?',(data.get('id'),user,s.now()))
            if not challenge or f'URI: {self.public_origin()}\n' not in challenge['message']:raise s.Problem('Wallet verification expired')
            try:address=Account.recover_message(encode_defunct(text=challenge['message']),signature=data.get('signature','')).lower()
            except Exception:raise s.Problem('Wallet signature could not be verified')
            if address!=challenge['address']:raise s.Problem('Wallet does not match this request',403)
            with s.connection() as db:
                if not db.execute('UPDATE challenges SET used=1 WHERE id=? AND used=0',(challenge['id'],)).rowcount:raise s.Problem('Wallet request already used',409)
                existing=db.execute('SELECT id FROM accounts WHERE wallet=? AND id!=?',(address,user)).fetchone()
                if existing:raise s.Problem('This wallet belongs to another account. Sign out and continue with this wallet.',409,'wallet_already_linked')
                db.execute('UPDATE accounts SET wallet=? WHERE id=?',(address,user))
            return self.response({'wallet':address})
        if path=='/api/orders/prepare':
            user=s.require(who,human=True);q=s.one('SELECT * FROM quotes WHERE id=? AND user_id=? AND expires>?',(data.get('quote'),user,s.now()))
            if not q:raise s.Problem('Quote expired. Get a new quote.',409,'quote_expired')
            if s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']!=q['wallet']:raise s.Problem('Wallet changed. Get a new quote.',409)
            quote=json.loads(q['payload']);approval=quote['approval']
            def still_current():
                if q['expires']<=s.now():raise s.Problem('Quote expired. Get a new quote.',409,'quote_expired')
                if s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']!=q['wallet']:raise s.Problem('Wallet changed. Get a new quote.',409)
            route_execution.validate(quote)
            if approval:
                spender=approval['spender']
                token_balance=int(s.rpc('eth_call',[{'to':approval['token'],'data':'0x70a08231'+q['wallet'][2:].rjust(64,'0')},'latest']),16)
                if token_balance<int(q['amount']):raise s.Problem('Not enough tokens in this wallet for this swap',409,'insufficient_balance')
                calldata='0xdd62ed3e'+q['wallet'][2:].rjust(64,'0')+spender[2:].rjust(64,'0')
                allowance=int(s.rpc('eth_call',[{'to':approval['token'],'data':calldata},'latest']),16)
                still_current()
                if allowance<int(q['amount']):
                    tx=transaction_preflight.funded({'from':q['wallet'],'to':approval['token'],'data':'0x095ea7b3'+spender[2:].rjust(64,'0')+hex(int(q['amount']))[2:].rjust(64,'0'),'value':'0x0'})
                    still_current()
                    return self.response({'approval':tx,'spender':spender,'amountRaw':q['amount'],'expires':q['expires']})
            tx=transaction_preflight.funded(quote['transaction'])
            still_current()
            return self.response({'transaction':tx,'expires':q['expires']})
        if path=='/api/payments/checkout':return self.response(settlement.checkout(who,data))
        if path=='/api/community-tokens/approval/check':return self.response(community_tokens.approval_check(who,data))
        if path.startswith('/api/community-tokens/'):
            action=path.rsplit('/',1)[-1]
            methods={'save':community_tokens.save,'dismiss':lambda w,d:community_tokens.dismiss(w),'plan':community_tokens.plan,'prepare':community_tokens.prepare,'record':community_tokens.record}
            if action not in methods:raise s.Problem('Community action not found',404)
            return self.response(methods[action](who,data))
        if path=='/api/orders/approval/check':return self.response(journey.spot_approval(who,data))
        if path=='/api/payments/prepare':return self.response(settlement.prepare(who,data))
        if path=='/api/payments/approval/check':return self.response(settlement.approval_check(who,data))
        if path=='/api/payments/record':return self.response(settlement.record(who,data))
        if path=='/api/execution/plan':
            context=journey.validate_context(who,data.get('context'))
            plan=venues.plan(who,data);journey.attach(who,'execution',plan['id'],context)
            return self.response(plan)
        if path=='/api/quotes':
            context=journey.validate_context(who,data.get('context'))
            quote=route_execution.quote(who,data);journey.attach(who,'spot',quote['id'],context)
            return self.response(quote)
        if path=='/api/execution/prepare':return self.response(venues.prepare(who,data))
        if path=='/api/execution/record':return self.response(venues.record(who,data))
        if path=='/api/execution/approval/check':return self.response(venues.check_approval(who,data))
        if path=='/api/stocks/intent':return self.response(stocks.order_intent(who,data))
        if path=='/api/orders':
            user=s.require(who,human=True);q=s.one('SELECT * FROM quotes WHERE id=? AND user_id=?',(data.get('quote'),user));txhash=str(data.get('tx',''))
            if not q or not re.fullmatch(r'0x[0-9a-fA-F]{64}',txhash):raise s.Problem('Invalid transaction reference')
            tx=s.rpc('eth_getTransactionByHash',[txhash]);expected=json.loads(q['payload'])['transaction']
            if not tx:raise s.Problem('Transaction not yet visible. Retry recording the same hash.',409,'transaction_pending')
            import wallet_execution
            wallet_execution.verified_call(txhash,{**expected,'from':q['wallet']},tx)
            existing=s.one('SELECT * FROM orders WHERE quote_id=? OR tx=?',(q['id'],txhash))
            if existing:
                if existing['user_id']!=user or existing['tx']!=txhash:raise s.Problem('Quote already submitted',409)
                return self.response(existing)
            ident=s.uid();s.write('INSERT INTO orders(id,user_id,quote_id,tx,state,created) VALUES(?,?,?,?,?,?)',(ident,user,q['id'],txhash,'submitted',s.now()));return self.response({'id':ident,'tx':txhash,'state':'submitted'})
        if path=='/oauth/register':
            redirects=data.get('redirect_uris',[])
            if not isinstance(redirects,list) or not redirects or len(redirects)>5 or not all(isinstance(x,str) and len(x)<1000 and (urlsplit(x).scheme=='https' or urlsplit(x).scheme=='http' and urlsplit(x).hostname in {'localhost','127.0.0.1'}) for x in redirects):raise s.Problem('Use HTTPS or a loopback redirect URI')
            ident=s.uid();s.write('INSERT INTO clients VALUES(?,?,?)',(ident,str(data.get('client_name','External agent'))[:60],s.dump(redirects)))
            return self.response({'client_id':ident,'client_name':data.get('client_name','External agent'),'redirect_uris':redirects,'token_endpoint_auth_method':'none'},201)
        if path=='/api/oauth/approve':
            if data.get('resource') and data['resource']!=self.public_origin()+'/mcp':raise s.Problem('Unknown requested resource')
            user=s.require(who,human=True);client=s.one('SELECT * FROM clients WHERE id=?',(data.get('client_id'),));scopes=set(str(data.get('scope','')).split())
            if not client or data.get('redirect_uri') not in json.loads(client['redirects']) or data.get('code_challenge_method')!='S256' or not re.fullmatch(r'[A-Za-z0-9_-]{43}',data.get('code_challenge','')) or not scopes or not scopes<=s.SCOPES:raise s.Problem('Invalid connection request')
            mapped=s.one('SELECT agent FROM agent_clients WHERE owner=? AND client=?',(user,client['id']))
            agent={'id':mapped['agent']} if mapped else None
            if not agent:
                agent={'id':s.uid()};s.write('INSERT INTO accounts(id,handle,name,kind,owner,created) VALUES(?,?,?,?,?,?)',(agent['id'],'agent_'+secrets.token_hex(4),client['name'],'agent',user,s.now()))
                s.write('INSERT INTO agent_clients VALUES(?,?,?)',(user,client['id'],agent['id']))
            code=secrets.token_urlsafe(32);s.write('INSERT INTO codes VALUES(?,?,?,?,?,?,?,?,?)',(s.digest(code),user,agent['id'],client['id'],data['redirect_uri'],data['code_challenge'],s.dump(sorted(scopes)),s.now()+120,0))
            s.write('INSERT INTO oauth_code_resources VALUES(?,?)',(s.digest(code),self.public_origin()+'/mcp'))
            return self.response({'redirect':data['redirect_uri']+('&' if '?' in data['redirect_uri'] else '?')+urlencode({'code':code,'state':data.get('state','')})})
        if path=='/oauth/token':return self.response(oauth_sessions.token(data,self.public_origin()+'/mcp'))
        if path=='/oauth/revoke':return self.response(oauth_sessions.revoke(data))
        if path=='/mcp':return self.mcp(who,data)
        if path.startswith('/api/'):return self.response(s.action(path.removeprefix('/api/'),who,data,self.headers.get('Idempotency-Key','')))
        raise s.Problem('Endpoint not found',404)
    def mcp(self,who,data):
        s.require(who);method=data.get('method');ident=data.get('id');params=data.get('params',{})
        if who.get('grant'):
            family=s.one('SELECT f.resource FROM oauth_access a JOIN oauth_families f ON f.id=a.family WHERE a.grant_id=?',(who['grant'],))
            if family and family['resource']!=self.public_origin()+'/mcp':raise s.Problem('Connection belongs to another origin',401)
        if method=='notifications/initialized':return self.response(b'',202,mime='application/json')
        if method=='initialize':result={'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in {'2025-03-26','2025-06-18','2025-11-25'} else '2025-06-18','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'Rally','version':'1.0.0'},'instructions':'Use only granted publishing scopes. Trading and wallet signatures are not exposed as tools.'}
        elif method=='ping':result={}
        elif method=='tools/list':result={'tools':TOOLS}
        elif method=='tools/call':
            name=params.get('name');args=params.get('arguments',{})
            try:
                if name=='feed.read':value=s.get_feed(who,args)
                elif name=='posts.publish':
                    if not isinstance(args.get('request_id'),str) or not 1<=len(args['request_id'])<=128:raise s.Problem('A stable request_id is required')
                    value=s.publish(who,args,args['request_id'])
                elif name=='posts.edit':value=social.action('post/edit',who,args)
                elif name=='media.upload':
                    s.require(who,'media:upload')
                    try:blob=base64.b64decode(args.get('base64',''),validate=True)
                    except Exception:raise s.Problem('Invalid media encoding')
                    if len(blob)>40000:raise s.Problem('Use media.prepare_upload for larger files',413)
                    value=s.upload_file(who,blob,args.get('mime'))
                elif name=='profile.read':value=s.profile(who['actor'],who['user'])
                elif name=='markets.search':
                    s.require(who,'markets:read');value=market_universe.catalog({'query':str(args.get('query','')),'scope':'all','limit':30})
                elif name=='media.prepare_upload':
                    s.require(who,'media:upload');ticket=secrets.token_urlsafe(32);s.write('INSERT INTO uploads(hash,owner,actor,expires,used,grant_id) VALUES(?,?,?,?,?,?)',(s.digest(ticket),who['user'],who['actor'],s.now()+600,0,who['grant']));value={'upload_url':self.public_origin()+'/upload/'+ticket,'method':'PUT','expires_in':600,'maximum_bytes':25*1024*1024,'content_types':['image/jpeg','image/png','image/webp','video/mp4','video/webm']}
                else:raise s.Problem('Tool not found',404)
                result={'content':[{'type':'text','text':s.dump(value)}],'isError':False}
            except s.Problem as error:result={'content':[{'type':'text','text':str(error)}],'isError':True}
        else:return self.response({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}})
        return self.response({'jsonrpc':'2.0','id':ident,'result':result})
    def portfolio(self,who):
        user=s.require(who,human=True);wallet=s.one('SELECT wallet FROM accounts WHERE id=?',(user,))['wallet']
        if not wallet:return {'wallet':None,'holdings':[]}
        return s.GATEWAY.portfolio(wallet)


def background():
    while True:
        for order in s.rows("SELECT * FROM orders WHERE state IN ('submitted','pending','confirmed') ORDER BY created DESC LIMIT 30"):
            try:
                journey.reconcile_spot(order)
            except Exception:pass
        for payment in s.rows("SELECT id FROM invoices WHERE state IN ('submitted','confirmed') ORDER BY created LIMIT 3"):
            try:settlement.reconcile(payment['id'])
            except Exception:pass
        community_tokens.background_once()
        try:discovery.alerts_tick()
        except Exception:pass
        for execution in s.rows("SELECT r.id FROM execution_records r JOIN execution_plans p ON p.id=r.plan WHERE r.state IN ('submitted','confirmed') OR (p.venue='pingu' AND r.state='finalized' AND COALESCE(json_extract(r.outcome,'$.businessState'),'request_unverified') IN ('request_unverified','keeper_pending')) OR (p.venue='leverup' AND r.state='finalized' AND (COALESCE(json_extract(r.outcome,'$.businessState'),'keeper_pending') NOT IN ('filled','refunded','closed','close_rejected','reverted','invalid') OR json_extract(r.outcome,'$.settlementState')='confirmed')) ORDER BY r.created LIMIT 3"):
            try:venues.reconcile(execution['id'])
            except Exception:pass
        time.sleep(30)


if __name__=='__main__':
    s.initialize();discovery.initialize();agent_wallet.initialize();media_pipeline.initialize();threading.Thread(target=background,daemon=True).start();threading.Thread(target=market_data.background,daemon=True).start();threading.Thread(target=market_universe.background,daemon=True).start();threading.Thread(target=spot_prices.background,daemon=True).start();threading.Thread(target=perp_universe.background,daemon=True).start();threading.Thread(target=nadfun.background,daemon=True).start();threading.Thread(target=launchpad.background,daemon=True).start()
    threading.Thread(target=token_images.background,daemon=True,name='public-token-art').start()
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
