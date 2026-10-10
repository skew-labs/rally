"""Immutable user formulas, bounded isolated scoring and matched comparisons."""
import json
import math
import secrets
import statistics
import subprocess
import sys
import threading
import time
import service as s
from algorithm_worker import FEATURES, parse

SLOTS=threading.BoundedSemaphore(2)


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS algorithms(id TEXT PRIMARY KEY,owner TEXT,name TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS algorithm_versions(id TEXT PRIMARY KEY,algorithm TEXT,version INTEGER,expression TEXT,created INTEGER,UNIQUE(algorithm,version));
        CREATE TABLE IF NOT EXISTS algorithm_runs(id TEXT PRIMARY KEY,version TEXT,owner TEXT,posts TEXT,metrics TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS algorithm_events(run TEXT,owner TEXT,post TEXT,kind TEXT,created INTEGER,PRIMARY KEY(run,owner,post,kind));
        CREATE TABLE IF NOT EXISTS algorithm_matches(id TEXT PRIMARY KEY,owner TEXT,versions TEXT,candidates TEXT,expires INTEGER);
        CREATE TABLE IF NOT EXISTS algorithm_preferences(owner TEXT,pair TEXT,chosen TEXT,match TEXT,created INTEGER,PRIMARY KEY(owner,pair));
        CREATE TABLE IF NOT EXISTS algorithm_duels(match TEXT PRIMARY KEY,versions TEXT,runs TEXT);
        CREATE TABLE IF NOT EXISTS algorithm_votes(owner TEXT,pair TEXT,chosen TEXT,match TEXT,created INTEGER,PRIMARY KEY(owner,pair));
        CREATE INDEX IF NOT EXISTS algorithm_runs_version ON algorithm_runs(version,created);
        ''')
        if 'algorithm_version' not in [r[1] for r in db.execute('PRAGMA table_info(feeds)')]:db.execute('ALTER TABLE feeds ADD COLUMN algorithm_version TEXT')


def run(expression, items):
    try:parse(expression)
    except (ValueError,SyntaxError,RecursionError):raise s.Problem('Invalid ranking formula',400,'formula_error')
    if not SLOTS.acquire(timeout=.1):raise s.Problem('Feed runner busy. Try again.',503,'runner_busy')
    started=time.monotonic()
    try:
        result=subprocess.run([sys.executable,'-I','-S',str(s.ROOT/'algorithm_worker.py')],input=s.dump({'expression':expression,'items':items}),text=True,capture_output=True,timeout=2,env={'LANG':'C.UTF-8'},cwd='/')
        value=json.loads(result.stdout)
        if result.returncode or value.get('error'):raise s.Problem(value.get('error','Formula could not run'),400,'formula_error')
        scores=value['scores']
        if len(scores)!=len(items) or {r['id'] for r in scores}!={r['id'] for r in items}:raise ValueError('Invalid runner output')
        return scores,round((time.monotonic()-started)*1000,2)
    except (subprocess.TimeoutExpired,ValueError,KeyError):raise s.Problem('Formula exceeded its limit',400,'formula_limit')
    finally:SLOTS.release()


def features(posts,viewer,watched):
    ids=[p['id'] for p in posts];likes={};replies={}
    if ids:
        marks=','.join('?' for _ in ids)
        likes={r['post']:r['n'] for r in s.rows("SELECT post,count(*) n FROM reactions WHERE kind='like' AND post IN ("+marks+') GROUP BY post',ids)}
        replies={r['parent']:r['n'] for r in s.rows('SELECT parent,count(*) n FROM posts WHERE deleted=0 AND parent IN ('+marks+') GROUP BY parent',ids)}
    following={r['target'] for r in s.rows('SELECT target FROM follows WHERE user_id=?',(viewer or '',))}
    authors=list({p['author'] for p in posts})
    agents={r['id'] for r in s.rows("SELECT id FROM accounts WHERE kind='agent' AND id IN ("+','.join('?' for _ in authors)+')',authors)} if authors else set()
    stamp=s.now()
    items=[{'id':p['id'],'features':{'recency':1/(1+max(0,stamp-p['created'])/3600),'likes':min(likes.get(p['id'],0),1e6),'replies':min(replies.get(p['id'],0),1e6),'watched':int(p['asset'] in watched),'following':int(p['author'] in following),'has_media':int(bool(p['media'])),'is_agent':int(p['author'] in agents),'has_asset':int(bool(p['asset']))}} for p in posts]
    return items


def rank(posts, feed, viewer, watched, record=False, snapshot=None):
    version=s.one('SELECT * FROM algorithm_versions WHERE id=?',(feed.get('algorithm_version'),))
    if not version:return None
    items=snapshot if snapshot is not None else features(posts,viewer,watched)
    scores,ms=run(version['expression'],items);mapping={r['id']:r['score'] for r in scores}
    result=sorted([dict(p,rankingReason='Custom formula',score=mapping[p['id']]) for p in posts],key=lambda p:(-p['score'],-p['created'],p['id']))
    top=result[:10]
    metrics={'candidates':len(posts),'topAuthors':len({p['author'] for p in top}),'topAssets':len({p['asset'] for p in top if p['asset']}),'watchMatches':sum(p['asset'] in watched for p in top),'runtimeMs':ms,'topSize':len(top)}
    run_id=None
    if record:
        run_id=s.uid();s.write('INSERT INTO algorithm_runs VALUES(?,?,?,?,?,?)',(run_id,version['id'],viewer,s.dump([p['id'] for p in result]),s.dump(metrics),s.now()))
        s.write('DELETE FROM algorithm_runs WHERE created<?',(s.now()-86400*30,))
        s.write('DELETE FROM algorithm_runs WHERE owner IS ? AND id NOT IN (SELECT id FROM algorithm_runs WHERE owner IS ? ORDER BY created DESC LIMIT 200)',(viewer,viewer))
        s.write('DELETE FROM algorithm_events WHERE run NOT IN (SELECT id FROM algorithm_runs)')
    return {'posts':result,'metrics':metrics,'run':run_id,'version':version['id']}


def listing(who=None):
    import social
    viewer=who['user'] if who else None
    versions=s.rows('SELECT v.*,a.owner,a.name FROM algorithm_versions v JOIN algorithms a ON a.id=v.algorithm ORDER BY v.created DESC LIMIT 100')
    versions=[v for v in versions if social.visible(viewer,v['owner'])]
    for v in versions:
        v['author']=s.profile(v['owner'])
        feed=s.one('SELECT * FROM feeds WHERE algorithm_version=?',(v['id'],))
        if feed and not __import__('settlement').allowed(feed,viewer):v['expression']=None
        samples=s.rows('SELECT metrics FROM algorithm_runs WHERE version=? ORDER BY created DESC LIMIT 100',(v['id'],))
        metrics=[json.loads(r['metrics']) for r in samples]
        v['measuredRuns']=len(metrics)
        v['medianRuntimeMs']=round(statistics.median(r['runtimeMs'] for r in metrics),2) if metrics else None
        v['readerChoices']=s.one('SELECT count(*) n FROM algorithm_preferences WHERE chosen=? AND owner!=?',(v['id'],v['owner']))['n']
        v['events']=s.one('SELECT count(*) n FROM algorithm_events e JOIN algorithm_runs r ON r.id=e.run WHERE r.version=?',(v['id'],))['n']
        v.update(reader_metrics(v['id'],v['owner']))
    return {'algorithms':versions,'features':sorted(FEATURES),'language':'rally-formula-v1','limits':{'candidates':100,'expressionCharacters':1000,'cpuSeconds':1,'memoryMB':96},'competition':'Matched candidate comparisons. Reader events are observed, not investment returns.'}


def reader_metrics(version, creator,cutoff=None,until=None):
    # One reader/post/action/day, irrespective of refreshes or scoring runs.
    query='''SELECT e.owner,e.post,e.kind,e.created/86400 day FROM algorithm_events e
        JOIN algorithm_runs r ON r.id=e.run WHERE r.version=? AND e.owner!=?
        AND e.created>=? GROUP BY e.owner,e.post,e.kind,day'''
    events=s.rows(query,(version,creator,cutoff if cutoff is not None else s.now()-86400*30))
    if until is not None:events=[e for e in events if e['day']<until//86400]
    seen={(e['owner'],e['post'],e['day']) for e in events if e['kind']=='impression'}
    engaged={(e['owner'],e['post'],e['day']) for e in events if e['kind']!='impression'} & seen
    return {'impressions':len(seen),'engagedViews':len(engaged),
        'engagementRate':round(100*len(engaged)/len(seen),1) if seen else None,
        'readers':len({e[0] for e in seen}),'windowDays':30}


def leaderboard(who=None):
    entries=listing(who)['algorithms']
    for entry in entries:
        votes=s.rows('SELECT chosen FROM algorithm_votes WHERE pair LIKE ? OR pair LIKE ?',
            (entry['id']+':%','%:'+entry['id']))
        n=len(votes);wins=sum(v['chosen']==entry['id'] for v in votes);p=wins/n if n else 0;z=1.96
        lower=(p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n) if n else 0
        entry.update({'ballots':n,'wins':wins,'winRate':round(100*p,1) if n else None,
            'confidence':round(lower,6),'rank':None})
    entries.sort(key=lambda v:(v['ballots']>=5,v['confidence'],v['ballots'],v['created']),reverse=True)
    for index,entry in enumerate((e for e in entries if e['ballots']>=5),1):entry['rank']=index
    return {'entries':entries,'minimumBallots':5,'method':'95% Wilson lower bound',
        'rules':'Blind comparisons on identical posts. One ballot per reader and version pair. Creators cannot vote for their own versions.'}


def duel(who):
    user=s.require(who,human=True)
    import social
    from settlement import allowed
    versions=[v for v in s.rows('''SELECT f.* FROM algorithm_versions v
        JOIN algorithms a ON a.id=v.algorithm JOIN feeds f ON f.algorithm_version=v.id
        ORDER BY v.created DESC LIMIT 100''') if v['owner']!=user and social.visible(user,v['owner']) and allowed(v,user)]
    pairs=[(a,b) for i,a in enumerate(versions) for b in versions[i+1:] if a['owner']!=b['owner']]
    if not pairs:raise s.Problem('Two other creators need to publish feeds before a blind comparison can start.',409,'competition_waiting')
    unvoted=[pair for pair in pairs if not s.one('SELECT 1 FROM algorithm_votes WHERE owner=? AND pair=?',(user,':'.join(sorted(v['algorithm_version'] for v in pair))))]
    pair=secrets.choice(unvoted or pairs)
    ids=[v['algorithm_version'] for v in pair]
    compared=action('algorithms/compare',who,{'versions':ids})
    if not compared['candidateIds']:raise s.Problem('Publish a post before comparing feeds.',409,'competition_waiting')
    s.write('INSERT INTO algorithm_duels VALUES(?,?,?)',(compared['match'],s.dump(ids),s.dump([r['run'] for r in compared['comparisons']])))
    return {'match':compared['match'],'candidates':len(compared['candidateIds']),
        'sides':[{'side':label,'posts':r['posts'],'run':r['run']} for label,r in zip(('a','b'),compared['comparisons'])]}


def action(path,who,data):
    user=s.require(who,human=True)
    if path=='algorithms/create':
        name=str(data.get('name','')).strip();expression=data.get('expression','')
        if not name or len(name)>32:raise s.Problem('Choose a name under 32 characters')
        try:parse(expression)
        except (ValueError,SyntaxError,RecursionError):raise s.Problem('Invalid formula. Use the listed features and arithmetic.')
        run(expression,[{'id':'validation','features':{f:0 for f in FEATURES}}])
        ident=data.get('algorithm');version_id=s.uid();feed_id=s.uid()
        with s.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if ident:
                if not db.execute('SELECT 1 FROM algorithms WHERE id=? AND owner=?',(ident,user)).fetchone():raise s.Problem('Algorithm not owned',403)
                version=db.execute('SELECT coalesce(max(version),0)+1 FROM algorithm_versions WHERE algorithm=?',(ident,)).fetchone()[0]
            else:
                if db.execute('SELECT count(*) FROM algorithms WHERE owner=?',(user,)).fetchone()[0]>=20:raise s.Problem('Algorithm limit reached',429)
                ident=s.uid();version=1;db.execute('INSERT INTO algorithms VALUES(?,?,?,?)',(ident,user,name,s.now()))
            db.execute('INSERT INTO algorithm_versions VALUES(?,?,?,?,?)',(version_id,ident,version,expression,s.now()))
            db.execute('INSERT INTO feeds(id,owner,name,weights,assets,created,algorithm_version) VALUES(?,?,?,?,?,?,?)',(feed_id,user,name+' · v'+str(version),'[100,0,0]','[]',s.now(),version_id))
        return {'id':ident,'version':version,'versionId':version_id,'feed':feed_id}
    if path=='algorithms/compare':
        versions=data.get('versions',[])
        if not isinstance(versions,list) or not 1<=len(versions)<=4 or not all(isinstance(v,str) for v in versions) or len(set(versions))!=len(versions):raise s.Problem('Choose up to four different versions')
        import social
        guard,args=social.visibility_sql(user)
        posts=s.rows('SELECT * FROM posts WHERE deleted=0 AND parent IS NULL'+guard+' ORDER BY created DESC,id DESC LIMIT 30',args)
        watched={r['asset'] for r in s.rows('SELECT asset FROM watches WHERE user_id=?',(user,))}
        comparisons=[];snapshot=features(posts,user,watched)
        for v in versions:
            feed=s.one('SELECT * FROM feeds WHERE algorithm_version=?',(v,))
            if not feed:raise s.Problem('Version not found',404)
            if not social.visible(user,feed['owner']):raise s.Problem('Version not found',404)
            from settlement import allowed
            if not allowed(feed,user):raise s.Problem('Subscribe to compare this feed',403)
            r=rank(posts,feed,user,watched,True,snapshot)
            comparisons.append({**r,'name':feed['name'],'posts':[s.post_view(p,user) for p in r['posts'][:10]]})
        match=s.uid()
        s.write('INSERT INTO algorithm_matches VALUES(?,?,?,?,?)',(match,user,s.dump(versions),s.dump([p['id'] for p in posts]),s.now()+3600))
        s.write('DELETE FROM algorithm_matches WHERE expires<?',(s.now()-86400,))
        return {'match':match,'candidateIds':[p['id'] for p in posts],'comparisons':comparisons,'latest':[s.post_view(p,user) for p in posts[:10]],'measuredAt':s.now()}
    if path=='algorithms/duel':return duel(who)
    if path=='algorithms/vote':
        import social
        from settlement import allowed
        match=s.one('SELECT m.*,d.versions choices FROM algorithm_matches m JOIN algorithm_duels d ON d.match=m.id WHERE m.id=? AND m.owner=? AND m.expires>?',(data.get('match'),user,s.now()))
        if not match or data.get('side') not in {'a','b'}:raise s.Problem('Comparison expired or not owned',403)
        ids=json.loads(match['choices']);feeds=[s.one('SELECT * FROM feeds WHERE algorithm_version=?',(v,)) for v in ids]
        if any(not f or f['owner']==user or not social.visible(user,f['owner']) or not allowed(f,user) for f in feeds):raise s.Problem('Comparison is no longer available',403)
        chosen=ids[0 if data['side']=='a' else 1];pair=':'.join(sorted(ids))
        s.write('INSERT INTO algorithm_votes VALUES(?,?,?,?,?) ON CONFLICT(owner,pair) DO UPDATE SET chosen=excluded.chosen,match=excluded.match,created=excluded.created',(user,pair,chosen,match['id'],s.now()))
        return {'chosen':chosen,'feed':next(f['id'] for f in feeds if f['algorithm_version']==chosen),
            'algorithms':[{'id':f['algorithm_version'],'name':f['name'],'creator':s.profile(f['owner'],user),'feed':f['id']} for f in feeds]}
    if path=='algorithms/choose':
        match=s.one('SELECT * FROM algorithm_matches WHERE id=? AND owner=? AND expires>?',(data.get('match'),user,s.now()))
        if not match:raise s.Problem('Comparison expired or not owned',403)
        versions=json.loads(match['versions']);chosen=data.get('version')
        if chosen not in versions:raise s.Problem('Version was not compared')
        feed=s.one('SELECT * FROM feeds WHERE algorithm_version=?',(chosen,))
        import social
        from settlement import allowed
        if not feed or not social.visible(user,feed['owner']) or not allowed(feed,user):raise s.Problem('Feed is no longer available',403)
        if len(versions)>1:
            pair=':'.join(sorted(set(versions)))
            s.write('INSERT INTO algorithm_preferences VALUES(?,?,?,?,?) ON CONFLICT(owner,pair) DO UPDATE SET chosen=excluded.chosen,match=excluded.match,created=excluded.created',(user,pair,chosen,match['id'],s.now()))
        s.action('feeds/use',who,{'id':feed['id']})
        return {'feed':feed['id']}
    if path=='algorithms/event':
        row=s.one('SELECT * FROM algorithm_runs WHERE id=? AND owner=?',(data.get('run'),user))
        ids=data.get('posts',[data.get('post')]);kind=data.get('kind')
        if not row or row['created']<s.now()-3600 or not isinstance(ids,list) or not 1<=len(ids)<=30 or any(not isinstance(p,str) or p not in json.loads(row['posts']) for p in ids) or kind not in {'impression','open','save','like','trade_open'} or kind!='impression' and len(ids)!=1:raise s.Problem('Invalid feed event')
        import social
        for ident in ids:
            social.post(ident,user)
            if kind in {'like','save'} and not s.one('SELECT 1 FROM reactions WHERE user_id=? AND post=? AND kind=?',(user,ident,kind)):raise s.Problem('Reaction not recorded',409)
        with s.connection() as db:db.executemany('INSERT OR IGNORE INTO algorithm_events VALUES(?,?,?,?,?)',[(row['id'],user,ident,kind,s.now()) for ident in set(ids)])
        return {'ok':True}
    raise s.Problem('Action not found',404)
