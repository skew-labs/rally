"""Token conversations reuse posts, moderation, identities and feed ranking."""
import re
import service as s

MENTION = re.compile(r'(?<![\w@])@([a-zA-Z0-9_]{3,24})(?![\w])')


def selection(params, viewer):
    if params.get('discussion') != '1':
        return 'parent IS NULL', []
    import social
    root, root_args = social.visibility_sql(viewer, 'root')
    child, child_args = social.visibility_sql(viewer, 'child')
    asset = params.get('asset')
    # The recursive join excludes a whole branch when any ancestor is deleted or blocked.
    # UNION (rather than UNION ALL) also bounds malformed cycles in old data.
    sql = """posts.id IN (WITH RECURSIVE conversation(id,asset) AS (
      SELECT root.id,root.asset FROM posts root WHERE root.parent IS NULL
      AND root.deleted=0 AND root.asset IS NOT NULL AND root.asset!=''""" + root
    args = list(root_args)
    if asset:
        sql += ' AND lower(root.asset)=lower(?)';args.append(str(asset))
    sql += """ UNION SELECT child.id,conversation.asset FROM posts child
      JOIN conversation ON child.parent=conversation.id WHERE child.deleted=0 AND (child.asset IS NULL OR child.asset='' OR lower(child.asset)=lower(conversation.asset))""" + child
    sql += ') SELECT id FROM conversation)'
    return sql, args + list(child_args)


def prepare(who, data):
    if not data.get('parent'):
        return data
    import social
    parent = social.post(data['parent'], who['user'])
    root = parent;seen = set()
    while root.get('parent'):
        if root['id'] in seen or len(seen) >= 100:
            raise s.Problem('Conversation unavailable', 409)
        seen.add(root['id']);root = social.post(root['parent'], who['user'])
    asset = root.get('asset')
    if data.get('asset') and asset and str(data['asset']).lower() != str(asset).lower():
        raise s.Problem('Reply in the same token conversation')
    # A reply inherits token context, not community membership or financial access.
    return {**data, 'asset': asset or data.get('asset')}


def decorate(post, viewer):
    import social
    if post.get('parent'):
        row = s.one('SELECT * FROM posts WHERE id=? AND deleted=0', (post['parent'],))
        if row and social.visible(viewer, row['author']):
            p = s.profile(row['author'], viewer)
            post['replyTo'] = {'id': row['id'], 'author': p, 'text': row['text'][:180]}
            if not post.get('asset'):
                seen = set()
                while row and not row.get('asset') and row.get('parent') and row['id'] not in seen and len(seen)<100:
                    seen.add(row['id']);row = s.one('SELECT * FROM posts WHERE id=? AND deleted=0', (row['parent'],))
                    if row and not social.visible(viewer,row['author']):row=None
                if row:post['asset'] = row.get('asset')
    asset = s.GATEWAY.token_map.get(post.get('asset'))
    if asset and not post.get('assetInfo'):
        post['assetInfo'] = {'id':post['asset'],**{k: asset[k] for k in ('id','name','symbol','logoURI','logoThumbURI','logoCandidates','image','kind','venue','nadfun','graduated') if k in asset}}
    handles = list(dict.fromkeys(h.lower() for h in MENTION.findall(post.get('text',''))))[:20]
    if handles:
        rows = s.rows('SELECT id,handle FROM accounts WHERE handle IN ('+','.join('?' for _ in handles)+')',handles)
        post['mentions'] = [r for r in rows if social.visible(viewer,r['id'])]
    return post


def notify(who, post):
    import social
    # Only existing, visible accounts receive notifications; never generate identities.
    for mention in decorate(dict(post),who['user']).get('mentions',[]):
        social.notify(who['actor'],mention['id'],'mention',post['id'])
