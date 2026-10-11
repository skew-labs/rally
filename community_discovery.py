"""Community discovery from stored social activity and cached token references.

No provider reads, order submission or inferred returns in the directory.
"""
import service as s


def catalog(viewer=None):
    import social
    import community_tokens
    guard,args=social.visibility_sql(viewer)
    stamp=s.now()
    activity={r['community']:r for r in s.rows('''SELECT community,
        count(*) AS posts, sum(created>=?) AS posts24h,
        max(created) AS lastPostAt FROM posts
        WHERE deleted=0 AND parent IS NULL AND community IS NOT NULL'''+guard+
        ' GROUP BY community',[stamp-86400,*args])}
    members={r['community']:r['n'] for r in s.rows('SELECT community,count(*) n FROM members GROUP BY community')}
    joined={r['community'] for r in s.rows('SELECT community FROM members WHERE user_id=?',(viewer,))} if viewer else set()
    owners={r['community']:r['owner'] for r in s.rows("SELECT community,owner FROM creator_tokens WHERE state='live' AND community IS NOT NULL")}
    result=[]
    for community in s.rows('SELECT * FROM communities ORDER BY rowid'):
        ident=community['id'];owner=owners.get(ident)
        if owner and not social.visible(viewer,owner):owner=None
        counts=activity.get(ident,{})
        token=community_tokens.public(owner) if owner else None
        if token:token={**token,'quoteAsset':s.GATEWAY.token_map.get(s.USDC)}
        result.append({**community,'members':members.get(ident,0),'joined':ident in joined,
            'posts':counts.get('posts',0),'posts24h':counts.get('posts24h',0),
            'lastPostAt':counts.get('lastPostAt'),'activityAsOf':stamp,
            'tokenOwner':owner,'token':token})
    return result
