"""A bounded identity-only adapter for the already paired MetaMask CLI runtime."""
import fcntl,json,os,re,subprocess,time
from pathlib import Path
import service as s
import agent_wallet as a

CLI=os.environ.get('RALLY_MM_CLI','mm')
RUNTIME=os.environ.get('RALLY_MM_RUNTIME','/usr/local/bin')
PLUGIN=os.environ.get('RALLY_MM_PLUGIN_ROOT','')
WORKDIR=os.environ.get('RALLY_MM_WORKDIR',str(s.STATE/'agent-cli'))
TERMINAL={'SIGNED','CONFIRMED','DENIED','EXPIRED','FAILED','APPROVED'}

def cli_env():
    # Only the existing official login environment reaches the CLI, never app secrets.
    env={k:os.environ[k] for k in ['HOME','LANG','XDG_CONFIG_HOME','XDG_STATE_HOME'] if k in os.environ}
    env.update(PATH=RUNTIME+':/usr/bin:/bin',MM_PLUGIN_ROOT=PLUGIN)
    return env

def documents(raw):
    result=[];decoder=json.JSONDecoder();offset=0
    while offset<len(raw):
        match=re.search(r'(?:^|\n)\s*(?=\{)',raw[offset:])
        if not match:break
        start=offset+match.end()
        try:doc,length=decoder.raw_decode(raw[start:]);result.append(doc);offset=start+length
        except ValueError:offset=start+1
    if not result:raise RuntimeError('Invalid CLI result')
    return result

def read(command):
    allowed={('doctor',),('wallet','address'),('wallet','trading-mode','get'),('wallet','requests','list')}
    if tuple(command) not in allowed:raise RuntimeError('Unsupported CLI read')
    p=subprocess.run([CLI,*command,'--json'],cwd=WORKDIR,env=cli_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=35)
    items=documents(p.stdout)
    final=next((d for d in reversed(items) if isinstance(d,dict) and 'ok' in d),None)
    if p.returncode or not final or not final.get('ok'):raise RuntimeError('MetaMask session unavailable')
    return final.get('data',{})

def preflight(row,reader=read):
    profile=a.profiles().get(row['owner'])
    if not profile or profile['address']!=row['address'] or profile['origin']!=row['origin']:raise RuntimeError('Paired agent changed')
    ready=reader(['doctor'])
    if not ready.get('authenticated') or not ready.get('initialized'):raise RuntimeError('MetaMask login needs reconnecting')
    wallet=reader(['wallet','address']);mode=reader(['wallet','trading-mode','get'])
    if wallet.get('mode')!='server' or str(wallet.get('address','')).lower()!=row['address'] or mode.get('mode')!='guard' or str(mode.get('address','')).lower()!=row['address']:raise RuntimeError('Use the existing paired Guard wallet')
    requests=reader(['wallet','requests','list']).get('requests',[])
    active=[r for r in requests if r.get('status') not in TERMINAL]
    if row['polling_id']:
        if any(r.get('pollingId')!=row['polling_id'] for r in active):raise RuntimeError('Another MetaMask approval is pending')
    elif active:raise RuntimeError('An existing MetaMask approval is pending. Complete it before reconnecting.')
    return requests

def consume(ident,doc):
    if isinstance(doc,dict) and isinstance(doc.get('_notice'),dict):a.notice(ident,doc['_notice']);return False
    if not isinstance(doc,dict) or 'ok' not in doc:return False
    if not doc.get('ok'):raise RuntimeError('MetaMask did not finish this request')
    data=doc.get('data',{});found=set()
    def visit(item,depth=0):
        if not isinstance(item,(dict,list)) or depth>6:return
        if isinstance(item,dict) and re.fullmatch(r'0x[0-9a-fA-F]{130}',str(item.get('signature',''))):found.add(item['signature'])
        for child in (item.values() if isinstance(item,dict) else item):visit(child,depth+1)
    visit(data)
    if len(found)>1:raise RuntimeError('Ambiguous signature result')
    if found:a.verified(ident,found.pop());return True
    job=data.get('pendingJob') or data.get('finalJob') or data.get('request') or data if isinstance(data,dict) else {}
    polling=job.get('pollingId') if isinstance(job,dict) else None
    if polling and re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',str(polling)):
        s.write("UPDATE agent_wallet_requests SET polling_id=?,state='waiting',updated=? WHERE id=? AND state!='verified'",(polling,s.now(),ident))
    return False

def run_signature(row,popen=subprocess.Popen):
    # The web client cannot supply CLI commands, messages, chain IDs or addresses.
    if row['state'] not in {'starting','waiting','uncertain'} or row['revoked'] or row['expires']<=s.now():raise RuntimeError('Connection request is no longer valid')
    if row['polling_id']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',row['polling_id']):raise RuntimeError('Invalid pending request')
        command=['wallet','requests','watch',row['polling_id'],'--wallet-timeout','600','--json']
    else:command=['wallet','sign-message','--chain-id','143','--message',row['message'],'--wait','--wallet-timeout','600','--json']
    p=popen([CLI,*command],cwd=WORKDIR,env=cli_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    completed=False;size=0;output=[]
    try:
        for line in p.stdout:
            size+=len(line)
            if size>256*1024:raise RuntimeError('Unexpected CLI response size')
            output.append(line)
            try:doc=json.loads(line)
            except ValueError:continue
            completed=consume(row['id'],doc) or completed
        code=p.wait(timeout=10)
        if not completed:
            for doc in documents(''.join(output)):
                completed=consume(row['id'],doc) or completed
                if completed:break
        if not completed:raise RuntimeError('MetaMask request still needs checking' if code else 'MetaMask approval is pending')
    finally:
        if p.poll() is None:p.terminate()

def tick(reader=read,runner=run_signature):
    row=s.one("SELECT * FROM agent_wallet_requests WHERE state IN ('queued','starting','waiting','uncertain') ORDER BY created LIMIT 1")
    if not row:return False
    # Never redispatch after a crash with an unknown job identity.
    if row['state'] in {'starting','uncertain'} and not row['polling_id']:
        s.write("UPDATE agent_wallet_requests SET state='uncertain',notice='Check the existing MetaMask request before reconnecting.',updated=? WHERE id=?",(s.now(),row['id']));return False
    if row['revoked'] or row['expires']<=s.now():
        if row['polling_id']:
            pending=reader(['wallet','requests','list']).get('requests',[])
            found=next((r for r in pending if r.get('pollingId')==row['polling_id']),None)
            if not found or found.get('status') not in TERMINAL:return False
        s.write("UPDATE agent_wallet_requests SET state=?,updated=? WHERE id=?",('revoked' if row['revoked'] else 'expired',s.now(),row['id']));return True
    try:
        requests=preflight(row,reader)
        if row['polling_id']:
            pending=next((r for r in requests if r.get('pollingId')==row['polling_id']),None)
            if not pending:return False
            if pending.get('status') in {'DENIED','EXPIRED','FAILED'}:
                state='expired' if pending['status']=='EXPIRED' else 'failed'
                s.write('UPDATE agent_wallet_requests SET state=?,notice=?,updated=? WHERE id=?',(state,'MetaMask request '+pending['status'].lower()+'.',s.now(),row['id']));return True
    except Exception as error:
        # Before dispatch, failure is terminal. An existing pending job remains resumable.
        state='waiting' if row['polling_id'] else 'failed'
        s.write('UPDATE agent_wallet_requests SET state=?,notice=?,updated=? WHERE id=?',(state,str(error)[:250],s.now(),row['id']));return False
    with s.connection() as db:
        if not db.execute("UPDATE agent_wallet_requests SET state='starting',updated=? WHERE id=? AND revoked=0 AND expires>? AND state IN ('queued','starting','waiting','uncertain')",(s.now(),row['id'],s.now())).rowcount:return False
    try:runner(s.one('SELECT * FROM agent_wallet_requests WHERE id=?',(row['id'],)))
    except Exception:
        current=s.one('SELECT * FROM agent_wallet_requests WHERE id=?',(row['id'],))
        if current['state']!='verified':s.write("UPDATE agent_wallet_requests SET state='uncertain',updated=? WHERE id=?",(s.now(),row['id']))
    return True

def main():
    lock=open(s.STATE/'agent-wallet-worker.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    a.initialize()
    while True:
        try:tick()
        except Exception:pass  # Do not emit credentials, signing results or command payloads.
        time.sleep(3)

if __name__=='__main__':main()
