"""Content-addressed public app assets; stale builds fall back to source modules."""
import hashlib
import json
import re
import threading

_cache={}
_lock=threading.Lock()


def current(root):
    manifest=root/'app-bundle.json'
    try:
        stat=manifest.stat()
        stamp=(stat.st_mtime_ns,stat.st_size)
        with _lock:
            entry=_cache.get(str(root))
            if not entry or entry['stamp']!=stamp:
                data=json.loads(manifest.read_text())
                files={**data['sources'],**data['outputs']}
                if len(files)>100 or not files:raise ValueError('Invalid asset manifest')
                if set(data['outputs'])!={data['js'],data['css']}:raise ValueError('Invalid outputs')
                for name,digest in files.items():
                    if not re.fullmatch(r'(?:assets/)?[A-Za-z0-9_.-]+',name) or not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid manifest path')
                for kind in ('js','css'):
                    if not re.fullmatch(r'assets/rally-app-[0-9a-f]{20}\.'+kind,data[kind]):raise ValueError('Invalid bundle')
                    if data['outputs'][data[kind]][:20] not in data[kind]:raise ValueError('Invalid content address')
                entry={'stamp':stamp,'data':data,'files':files,'signature':None}
                _cache[str(root)]=entry
            signature=tuple((name,(root/name).stat().st_mtime_ns,(root/name).stat().st_size) for name in entry['files'])
            if signature!=entry['signature']:
                entry['valid']=all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in entry['files'].items())
                entry['signature']=signature
            return {kind:entry['data'][kind] for kind in ('js','css')} if entry['valid'] else None
    except (OSError,ValueError,KeyError,TypeError):
        return None


def html(source,bundle):
    source=re.sub(r'\s*<link\b[^>]*rel="(?:modulepreload|stylesheet)"[^>]*>', '',source)
    source=source.replace('</head>','<link rel="stylesheet" href="/'+bundle['css']+'" /><link rel="modulepreload" href="/'+bundle['js']+'" /></head>')
    return source.replace('src="./live-app.js"','src="/'+bundle['js']+'"')
