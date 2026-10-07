"""Durable video queue and permission-neutral delivery metadata.

This module never decides who may read an upload. HTTP handlers must authorize
the parent media id before resolving a derivative with ``delivery``.
"""
import json
import re
import shutil

import service as s

MAX_UPLOAD = 25 * 1024 * 1024
OWNER_QUOTA = 250 * 1024 * 1024
MAX_PENDING = 4
MAX_DURATION = 180
MAX_PIXELS = 16_777_216
MAX_OUTPUT = 48 * 1024 * 1024
VERSION = 1


def initialize():
    with s.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS media_jobs(
          media_id TEXT PRIMARY KEY, state TEXT NOT NULL, input_path TEXT NOT NULL,
          input_mime TEXT NOT NULL, attempts INTEGER DEFAULT 0, created INTEGER,
          updated INTEGER, error TEXT, metadata TEXT);
        CREATE INDEX IF NOT EXISTS media_jobs_queue ON media_jobs(state,created);
        ''')


def enqueue(ident, owner, actor, body, mime):
    """Store a bounded input and enqueue it atomically; no encoder in HTTP workers."""
    initialize()
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise s.Problem('Invalid upload request')
    if mime not in {'video/mp4', 'video/webm'} or not body or len(body) > MAX_UPLOAD:
        raise s.Problem('Choose an MP4 or WebM video under 25 MB', 413)
    valid = ((mime == 'video/mp4' and len(body) > 12 and body[4:8] == b'ftyp') or
             (mime == 'video/webm' and body[:4] == b'\x1aE\xdf\xa3'))
    if not valid:
        raise s.Problem('This video could not be opened')
    ext = '.source.mp4' if mime == 'video/mp4' else '.source.webm'
    path = s.STATE / 'media' / (ident + ext)
    created = False
    # Row checks and write are serialized across upload workers, not just threads.
    try:
        with s.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT coalesce(sum(size),0) FROM media WHERE owner=?', (owner,)).fetchone()[0] + len(body) > OWNER_QUOTA:
                raise s.Problem('Media storage limit reached', 413)
            pending = db.execute("SELECT count(*) FROM media_jobs j JOIN media m ON m.id=j.media_id WHERE m.owner=? AND j.state IN ('pending','running')", (owner,)).fetchone()[0]
            if pending >= MAX_PENDING:
                raise s.Problem('Your videos are still processing. Try again shortly.', 429)
            with path.open('xb') as handle:
                created = True
                handle.write(body)
            path.chmod(0o600)
            db.execute('INSERT INTO media(id,owner,actor,path,mime,size,created) VALUES(?,?,?,?,?,?,?)', (ident, owner, actor, path.name, mime, len(body), s.now()))
            db.execute('INSERT INTO media_jobs(media_id,state,input_path,input_mime,created,updated) VALUES(?,?,?,?,?,?)', (ident, 'pending', path.name, mime, s.now(), s.now()))
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return describe(ident)


def describe(ident):
    """Stable API shape for image, pending video, and optimized video uploads."""
    row = s.one('SELECT id,mime,size FROM media WHERE id=?', (ident,))
    if not row:
        raise s.Problem('Media not found', 404)
    job = s.one('SELECT state,error,metadata FROM media_jobs WHERE media_id=?', (ident,))
    result = {**row, 'url': '/media/' + ident, 'state': job['state'] if job else 'ready'}
    if job and job['state'] == 'ready':
        meta = json.loads(job['metadata'])
        result.update({'mime': 'video/mp4', 'poster': '/media/' + ident + '/poster',
                       'width': meta['width'], 'height': meta['height'],
                       'duration': meta['duration'], 'size': meta['videoBytes'],
                       'hls': '/media/' + ident + '/hls/index.m3u8' if meta.get('hls') else None})
    elif job and job['state'] == 'failed':
        result['message'] = 'This video could not be processed. Upload a different file.'
    return result


def delivery(ident, suffix=''):
    """Return an allowlisted local file after the caller has checked the media ACL.

    Never accept user paths here, and never turn the private media directory into
    an unauthenticated static directory/CDN export.
    """
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise s.Problem('Media not found', 404)
    row = s.one('SELECT path,mime FROM media WHERE id=?', (ident,))
    if not row:
        raise s.Problem('Media not found', 404)
    job = s.one('SELECT state,metadata FROM media_jobs WHERE media_id=?', (ident,))
    if job and job['state'] != 'ready':
        raise s.Problem('Video is processing' if job['state'] != 'failed' else 'Video unavailable', 425 if job['state'] != 'failed' else 404, 'media_processing' if job['state'] != 'failed' else 'media_failed')
    if not suffix:
        target, mime = s.STATE / 'media' / row['path'], row['mime']
    elif suffix == 'poster' and job:
        target, mime = s.STATE / 'media' / ident / 'poster.webp', 'image/webp'
    elif job and json.loads(job['metadata']).get('hls') and re.fullmatch(r'hls/(?:index\.m3u8|segment[0-9]{5}\.ts)', suffix):
        target = s.STATE / 'media' / ident / suffix
        mime = 'application/vnd.apple.mpegurl' if target.suffix == '.m3u8' else 'video/mp2t'
    else:
        raise s.Problem('Media not found', 404)
    if not target.resolve().is_relative_to((s.STATE / 'media').resolve()) or not target.is_file() or target.is_symlink():
        raise s.Problem('Media not found', 404)
    return target, mime


def claim():
    expired = []
    result = None
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        # A killed encoder has a bounded deadline; its durable input may be retried.
        expired = [dict(x) for x in db.execute("SELECT * FROM media_jobs WHERE state='running' AND updated<? AND attempts>=2", (s.now() - 300,))]
        db.execute("UPDATE media_jobs SET state=CASE WHEN attempts<2 THEN 'pending' ELSE 'failed' END,error='worker_interrupted',updated=? WHERE state='running' AND updated<?", (s.now(), s.now() - 300))
        row = db.execute("SELECT * FROM media_jobs WHERE state='pending' ORDER BY created,media_id LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE media_jobs SET state='running',attempts=attempts+1,updated=? WHERE media_id=? AND state='pending'", (s.now(), row['media_id']))
            result = dict(row)
    for old in expired:
        fail(old, 'worker_interrupted')
    return result


def fail(job, reason='encode_failed'):
    """Discard unusable inputs and staged derivatives, retaining an honest status."""
    ident = job['media_id']
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        return
    source = s.STATE / 'media' / job['input_path']
    if source.parent == s.STATE / 'media' and source.name.startswith(ident + '.source.'):
        source.unlink(missing_ok=True)
    shutil.rmtree(s.STATE / 'media' / ('.work-' + ident), ignore_errors=True)
    shutil.rmtree(s.STATE / 'media' / ident, ignore_errors=True)
    with s.connection() as db:
        db.execute("UPDATE media_jobs SET state='failed',error=?,updated=? WHERE media_id=?", (reason, s.now(), ident))
        db.execute('UPDATE media SET size=0 WHERE id=?', (ident,))
