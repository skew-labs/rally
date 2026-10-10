"""Disposable, provider-blocked interaction fixture. Never use with production state."""
import json,os,sys,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
assert os.environ.get('RALLY_TESTING')=='1'
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
port=int(os.environ.get('RALLY_PREVIEW_PORT','33211'))
with tempfile.TemporaryDirectory(prefix='rally-social-loop-') as directory:
    os.environ.update(RALLY_STATE_DIR=directory,RALLY_PORT=str(port),RALLY_PUBLIC_ORIGIN=f'http://127.0.0.1:{port}',RALLY_PUSH_DISABLED='1',RALLY_CDN_BASE='',RALLY_RPC_URL='https://rpc.invalid',RALLY_COMMUNITY_FACTORY='',RALLY_COMMUNITY_DEPLOYER='',RALLY_PRIVY_APP_ID='',RALLY_AGENT_BRIDGE_CONFIG=str(Path(directory)/'unpaired.json'))
    import service as s
    def offline(*args,**kwargs):raise s.Problem('Provider blocked in QA fixture',503)
    s.rpc=offline;s.http_json=offline;s.rpc_read_batch=offline
    import live_server as app,discovery,social_loop as loop,algorithm_league as league,token_benefits as benefits
    s.initialize();app.agent_wallet.initialize()
    TOKEN='0x'+'a'*40;WALLET='0x'+'b'*40;OTHER='0x'+'c'*40;TX='0x'+'d'*64;BLOCK='0x'+'e'*64
    for owner,wallet in [('creator',OTHER),('reader',WALLET)]:s.write('INSERT INTO accounts(id,handle,name,kind,wallet,avatar,created) VALUES(?,?,?,?,?,?,?)',(owner,owner,'QA '+owner,'person',wallet,'/assets/community-rally.png',s.now()))
    who=lambda owner:{'user':owner,'actor':owner,'grant':None,'scopes':s.SCOPES}
    s.GATEWAY.token_map[TOKEN]={'id':TOKEN,'address':TOKEN,'name':'QA Token','symbol':'TEST','decimals':18,'logoURI':'/assets/community-rally.png','chainId':143}
    s.GATEWAY.token_map[s.USDC]={'id':s.USDC,'address':s.USDC,'symbol':'USDC','name':'USDC','decimals':6,'logoURI':'/assets/USDC.png'}
    s.GATEWAY.prices[TOKEN]={'price':'0.01','fetchedAt':s.now(),'source':'QA reference'}
    # Avoid market/provider requests in every fixture render.
    s.GATEWAY.markets=lambda *a,**k:{'tokens':[dict(t,price=.01 if t['id']==TOKEN else 1,change=0,fetchedAt=s.now()) for t in s.GATEWAY.token_map.values() if t['id']in{TOKEN,s.USDC}],'venues':[],'fetchedAt':s.now()}
    s.write('INSERT INTO communities VALUES(?,?,?)',('qa-community','QA community','Disposable UI fixture'))
    s.write('INSERT INTO members VALUES(?,?)',('creator','qa-community'))
    draft={'name':'QA Token','symbol':'TEST','imageURI':'/assets/community-rally.png','buybackBps':2000,'burnBps':10000}
    s.write('INSERT INTO creator_tokens(owner,wallet,draft,state,token,vault,pair,community,stats,verified) VALUES(?,?,?,?,?,?,?,?,?,?)',('creator',OTHER,s.dump(draft),'live',TOKEN,'0x'+'1'*40,'0x'+'2'*40,'qa-community','{}',s.now()))
    s.write('INSERT INTO community_onboarding VALUES(?,?,?)',('creator','configured',s.now()))
    s.write('INSERT INTO feeds(id,owner,name,weights,assets,created,price_raw,version,recipient,algorithm_version) VALUES(?,?,?,?,?,?,?,?,?,?)',('qa-feed','creator','QA algorithm','[100,0,0]','[]',s.now(),'1000000',1,OTHER,'qa-version'))
    s.write('INSERT INTO algorithms VALUES(?,?,?,?)',('qa-algo','creator','QA algorithm',s.now()))
    s.write('INSERT INTO algorithm_versions VALUES(?,?,?,?,?)',('qa-version','qa-algo',1,'recency',s.now()))
    signal=s.publish(who('creator'),{'text':'QA signal card. Disposable fixture; no real trade claim.','asset':TOKEN,'signal':{'direction':'up','target':'.02','invalidation':'.005','hours':24}},'qa-signal')
    benefits.save(who('creator'),{'tiers':[{'label':'Member','minimum':'100','discountBps':1000,'feeds':['qa-feed']}],'gatedFeeds':['qa-feed']})
    receipt={'status':'0x1','transactionHash':TX,'blockHash':BLOCK,'blockNumber':'0x64','logs':[{'address':s.USDC,'topics':[discovery.TRANSFER,'0x'+WALLET[2:].rjust(64,'0'),'0x'+OTHER[2:].rjust(64,'0')],'data':hex(1000000)},{'address':TOKEN,'topics':[discovery.TRANSFER,'0x'+OTHER[2:].rjust(64,'0'),'0x'+WALLET[2:].rjust(64,'0')],'data':hex(10**18)}]}
    s.write('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',('qa-quote','reader',WALLET,s.USDC,TOKEN,'1000000',s.dump({'provider':'QA Kuru reference'}),s.now()+60))
    s.write('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',('qa-order','reader','qa-quote',TX,'finalized',s.dump(receipt),s.now()))
    trade=loop.share(who('reader'),{'trade':'qa-order'})
    perpl_tx='0x'+'f'*64
    perpl_receipt={**receipt,'transactionHash':perpl_tx,'logs':[]}
    payload={'summary':{'marketId':7,'market':'QA BTC','direction':'long'}}
    outcome={'receipt':perpl_receipt,'businessState':'filled','fillQuantity':'0.001','entryPrice':'63000'}
    s.write('INSERT INTO execution_plans VALUES(?,?,?,?,?,?,?)',('qa-perpl-plan','creator',OTHER,'perpl','order',s.dump(payload),s.now()+60))
    s.write('INSERT INTO execution_records VALUES(?,?,?,?,?,?,?)',('qa-perpl-fill','creator','qa-perpl-plan',perpl_tx,'finalized',s.dump(outcome),s.now()))
    perpl=loop.share(who('creator'),{'trade':'qa-perpl-fill'})
    s.write('INSERT INTO follows VALUES(?,?)',('creator','reader'))
    s.write('INSERT INTO watches VALUES(?,?)',('creator',TOKEN))
    cookie=s.session_for('creator');file=Path(os.environ['RALLY_FIXTURE_FILE']);file.write_text(s.dump({'cookie':cookie,'signal':signal['id'],'trade':trade['id'],'perpl':perpl['id'],'token':TOKEN}));file.chmod(0o600)
    ThreadingHTTPServer(('127.0.0.1',port),app.Handler).serve_forever()
