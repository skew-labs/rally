"""Forward-only weekly contests on identical frozen candidates and features."""
import json
import math
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import service as s
import social
import algorithms
import social_loop


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS league_entries(week TEXT,feed TEXT,owner TEXT,version TEXT,enrolled INTEGER,PRIMARY KEY(week,feed));
        CREATE TABLE IF NOT EXISTS league_rounds(id TEXT PRIMARY KEY,week TEXT,created INTEGER,digest TEXT,candidates TEXT,features TEXT,prices TEXT);
        CREATE TABLE IF NOT EXISTS league_runs(round TEXT,feed TEXT,version TEXT,state TEXT,selected TEXT,runtime REAL,error TEXT,PRIMARY KEY(round,feed));
        CREATE TABLE IF NOT EXISTS league_marks(round TEXT,asset TEXT,entry TEXT,closing TEXT,state TEXT,PRIMARY KEY(round,asset));
        CREATE INDEX IF NOT EXISTS league_week_rounds ON league_rounds(week,created);
        ''')
        if 'post_times' not in {r[1] for r in db.execute('PRAGMA table_info(league_runs)')}:
            db.execute('ALTER TABLE league_runs ADD COLUMN post_times TEXT')


def period(stamp=None):
    date=datetime.fromtimestamp(s.now() if stamp is None else stamp,timezone.utc)
    start=(date-timedelta(days=date.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    return start.strftime('%Y-%m-%d'),int(start.timestamp()),int((start+timedelta(days=7)).timestamp())


def enroll(who,data):
    user=s.require(who,human=True);feed=s.one('SELECT * FROM feeds WHERE id=? AND owner=?',(data.get('feed'),user))
    if not feed or not feed.get('algorithm_version'):raise s.Problem('Publish a custom algorithm before entering the league',409)
    week,_,_=period()
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT version FROM league_entries WHERE week=? AND feed=?',(week,feed['id'])).fetchone()
        if old and old['version']!=feed['algorithm_version']:raise s.Problem('This week keeps your entered version. Enter the new version next week.',409)
        if not old:
            if db.execute('SELECT count(*) FROM league_entries WHERE week=?',(week,)).fetchone()[0]>=50:raise s.Problem('This week has reached its entry limit',409)
            db.execute('INSERT INTO league_entries VALUES(?,?,?,?,?)',(week,feed['id'],user,feed['algorithm_version'],s.now()))
    return listing(who)


def capture():
    week,_,_=period();slot=s.now()//3600*3600;ident=str(slot)
    if s.now()-slot>300 or s.one('SELECT 1 FROM league_rounds WHERE id=?',(ident,)):return
    if not s.one('SELECT 1 FROM league_entries WHERE week=? AND enrolled<=?',(week,slot)):return
    # User-neutral features: no entrant's watchlist or follow graph advantage.
    posts=s.rows('SELECT * FROM posts WHERE deleted=0 AND parent IS NULL AND created<=? ORDER BY created DESC,id DESC LIMIT 30',(slot,))
    if not posts:return
    features=algorithms.features(posts,None,set());prices={}
    for p in posts:
        if p['asset'] and p['asset'] not in prices:
            ref=social_loop.reference(p['asset'])
            if ref:prices[p['asset']]=ref
    raw=s.dump({'posts':posts,'features':features,'prices':prices});digest=s.digest(raw)
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM league_rounds WHERE id=?',(ident,)).fetchone():return
        db.execute('INSERT INTO league_rounds VALUES(?,?,?,?,?,?,?)',(ident,week,s.now(),digest,s.dump(posts),s.dump(features),s.dump(prices)))
        for row in db.execute('SELECT * FROM league_entries WHERE week=? AND enrolled<=?',(week,slot)):
            db.execute("INSERT INTO league_runs(round,feed,version,state) VALUES(?,?,?,'pending')",(ident,row['feed'],row['version']))
        for asset,ref in prices.items():db.execute("INSERT INTO league_marks(round,asset,entry,state) VALUES(?,?,?,'pending')",(ident,asset,s.dump(ref)))


def run_pending():
    for row in s.rows("SELECT r.*,c.candidates,c.features,c.created FROM league_runs r JOIN league_rounds c ON c.id=r.round WHERE r.state='pending' ORDER BY c.created,r.feed LIMIT 5"):
        if s.now()-row['created']>300:
            s.write("UPDATE league_runs SET state='missed' WHERE round=? AND feed=?",(row['round'],row['feed']));continue
        version=s.one('SELECT expression FROM algorithm_versions WHERE id=?',(row['version'],))
        try:
            if not version:raise s.Problem('Version unavailable')
            scores,ms=algorithms.run(version['expression'],json.loads(row['features']));mapping={p['id']:p['score'] for p in scores}
            posts=sorted(json.loads(row['candidates']),key=lambda p:(-mapping[p['id']],-p['created'],p['id']))
            selected=list(dict.fromkeys(p['asset'] for p in posts[:10] if p['asset']))[:5]
            post_times={}
            for p in posts[:10]:
                if p['asset'] in selected and p['asset'] not in post_times:post_times[p['asset']]=p['created']
            s.write("UPDATE league_runs SET state='scored',selected=?,post_times=?,runtime=? WHERE round=? AND feed=?",(s.dump(selected),s.dump(post_times),ms,row['round'],row['feed']))
        except Exception:
            s.write("UPDATE league_runs SET state='failed',error='Formula could not complete within its limit' WHERE round=? AND feed=?",(row['round'],row['feed']))


def mark():
    for row in s.rows("SELECT m.*,r.created FROM league_marks m JOIN league_rounds r ON r.id=m.round WHERE m.state='pending' AND r.created<=? ORDER BY r.created LIMIT 200",(s.now()-86400,)):
        ref=social_loop.reference(row['asset']);due=row['created']+86400
        if ref and due<=ref['observedAt']<=due+600:
            s.write("UPDATE league_marks SET closing=?,state='measured' WHERE round=? AND asset=?",(s.dump(ref),row['round'],row['asset']))
        elif s.now()>due+600:s.write("UPDATE league_marks SET state='unmeasured' WHERE round=? AND asset=?",(row['round'],row['asset']))


def listing(who=None,week=None):
    import discovery
    viewer=who['user'] if who else None
    if who and who.get('grant'):s.require(who,'feed:read')
    current,start,end=period()
    if week:
        try:
            parsed=datetime.strptime(week,'%Y-%m-%d').replace(tzinfo=timezone.utc);requested=period(int(parsed.timestamp()))
            if requested[0]!=week or requested[1]>start:raise ValueError()
            current,start,end=requested
        except (ValueError,TypeError):raise s.Problem('Choose a UTC week starting on Monday')
    entries=[]
    marks={(m['round'],m['asset']):m for m in s.rows('SELECT m.* FROM league_marks m JOIN league_rounds r ON r.id=m.round WHERE r.week=?',(current,))}
    for e in s.rows('SELECT e.*,f.name FROM league_entries e JOIN feeds f ON f.id=e.feed WHERE e.week=?',(current,)):
        if not social.visible(viewer,e['owner']):continue
        measured=[];delays=[];pending=0;missing=0;runs=s.rows('SELECT r.*,c.created FROM league_runs r JOIN league_rounds c ON c.id=r.round WHERE r.feed=? AND r.version=? AND c.week=?',(e['feed'],e['version'],current))
        for run in runs:
            delays.extend(max(0,run['created']-t) for t in json.loads(run['post_times'] or '{}').values())
            for asset in json.loads(run['selected'] or '[]'):
                m=marks.get((run['round'],asset))
                if m and m['state']=='measured':measured.append(float((Decimal(json.loads(m['closing'])['price'])/Decimal(json.loads(m['entry'])['price'])-1)*100))
                elif m and m['state']=='pending':pending+=1
                else:missing+=1
        reader=algorithms.reader_metrics(e['version'],e['owner'],cutoff=start,until=end)
        f=s.one('SELECT * FROM feeds WHERE id=?',(e['feed'],));pnl=discovery.performance(f,cutoff=start,until=end)
        entries.append({**e,'author':s.profile(e['owner'],viewer),'priceChangePercent':sum(measured)/len(measured) if measured else None,
            'samples':len(measured),'pending':pending,'unmeasured':missing,'rounds':len(runs),'failedRounds':sum(r['state']in {'failed','missed'} for r in runs),
            'discoveryDelaySeconds':sum(delays)/len(delays) if delays else None,'discoveryDelaySamples':len(delays),
            'reader':reader,'performance':pnl,'rank':None})
    entries.sort(key=lambda e:(e['samples']<3,-(e['priceChangePercent'] or 0),e['enrolled'],e['feed']))
    for i,e in enumerate([e for e in entries if e['samples']>=3],1):e['rank']=i
    rounds=s.rows('SELECT id,created,digest FROM league_rounds WHERE week=? ORDER BY created DESC LIMIT 24',(current,))
    return {'week':current,'starts':start,'ends':end,'entries':entries,'rounds':rounds,'minimumSamples':3,
        'method':'Same hourly candidates and frozen neutral features. Top five distinct tokens; observed USD price after 24h. Missing prices are excluded.',
        'basis':'Price discovery, reader engagement and realized USDC spot results are separate metrics.'}


def tick():
    capture();run_pending();mark()
