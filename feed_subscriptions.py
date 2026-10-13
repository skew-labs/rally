"""Saved feed subscriptions. Paid access remains receipt-verified by settlement."""
import threading
import service as s

LOCK = threading.Lock()
READY = False


def initialize():
    global READY
    with LOCK:
        if READY:
            return
        s.write('CREATE TABLE IF NOT EXISTS feed_subscriptions(owner TEXT,feed TEXT,enabled INTEGER NOT NULL,updated INTEGER NOT NULL,PRIMARY KEY(owner,feed))')
        READY = True


def decorate(data, who):
    initialize()
    user = who['user'] if who and not who.get('grant') else None
    saved = {r['feed']: r for r in s.rows('SELECT feed,enabled FROM feed_subscriptions WHERE owner=?', (user,))} if user else {}
    paid = {r['feed'] for r in s.rows('SELECT DISTINCT feed FROM entitlements WHERE buyer=?', (user,))} if user else set()
    feeds = []
    for feed in data.get('feeds', []):
        explicit = saved.get(feed['id'])
        included = bool(explicit['enabled']) if explicit else bool(user and (feed['id'] in paid or feed['id'] == data.get('activeFeed')))
        included = included and feed['id'] != 'latest'
        feeds.append({**feed, 'subscribed': bool(included and feed.get('access')),
                      'subscriptionSaved': included,
                      'subscriptionState': 'active' if included and feed.get('access') else 'expired' if included else None})
    return {**data, 'feeds': feeds}


def update(who, data):
    user = s.require(who, human=True)
    if type(data.get('active', True)) is not bool:
        raise s.Problem('Invalid subscription state')
    ident = data.get('id');active = data.get('active', True)
    feed = s.one('SELECT * FROM feeds WHERE id=?', (ident,))
    import social, settlement
    if not feed or not social.visible(user, feed['owner']):
        raise s.Problem('Feed not found', 404)
    if active and not settlement.allowed(feed, user):
        raise s.Problem('Subscribe to use this feed', 403, 'subscription_required')
    initialize()
    with s.connection() as db:
        if ident != 'latest':
            db.execute('INSERT INTO feed_subscriptions VALUES(?,?,?,?) ON CONFLICT(owner,feed) DO UPDATE SET enabled=excluded.enabled,updated=excluded.updated', (user, ident, int(active), s.now()))
        if active:
            db.execute('INSERT INTO settings(user_id,feed) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET feed=excluded.feed', (user, ident))
        else:
            db.execute("UPDATE settings SET feed='latest' WHERE user_id=? AND feed=?", (user, ident))
    return {'ok': True, 'id': ident, 'subscribed': active and ident != 'latest'}
