"""Small, first-party derivatives of public nad.fun artwork, outside HTTP workers."""
import hashlib,io,json,os,re,threading,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from PIL import Image
import service as s

LIMIT=3*1024*1024
LOCK=threading.Lock();CACHE={};RETRY={}


def safe(url):
    if not isinstance(url,str):return False
    try:u=urlsplit(url)
    except ValueError:return False
    return u.scheme=='https' and u.netloc=='storage.nadapp.net' and not u.query and not u.fragment and bool(re.fullmatch(r'/coin/[A-Za-z0-9_-]{8,128}',u.path))


def restore():
    try:
        data=json.loads((s.STATE/'token-art-map.json').read_text())
        with LOCK:
            CACHE.update({key:value for key,value in data.items() if re.fullmatch(r'[a-f0-9]{64}',key) and isinstance(value,str) and re.fullmatch(r'token-art-[a-f0-9]{20}\.webp',value)})
    except (OSError,ValueError,AttributeError):pass


def ready(url):
    if not safe(url):return None
    with LOCK:name=CACHE.get(hashlib.sha256(url.encode()).hexdigest())
    return '/assets/'+name if name and (s.ROOT/'assets'/name).is_file() else None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Artwork redirects are not supported')


def encode(body):
    if len(body)>LIMIT:raise ValueError('Artwork exceeds size limit')
    with Image.open(io.BytesIO(body)) as image:
        if image.format not in {'JPEG','PNG','WEBP','GIF'} or image.width*image.height>16_777_216:raise ValueError('Unsupported artwork')
        image.seek(0);image.thumbnail((96,96));image=image.convert('RGBA')
        output=io.BytesIO();image.save(output,format='WEBP',quality=82,method=4);return output.getvalue()


def collect(url):
    if not safe(url):return False
    key=hashlib.sha256(url.encode()).hexdigest()
    if ready(url):return True
    with LOCK:
        if RETRY.get(key,0)>time.time():return False
        RETRY[key]=time.time()+600
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'Rally-Token-Art/1.0','Accept':'image/*'})
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=5) as response:
            if int(response.headers.get('Content-Length','0'))>LIMIT:raise ValueError('Artwork exceeds size limit')
            body=response.read(LIMIT+1)
        webp=encode(body);name='token-art-'+hashlib.sha256(webp).hexdigest()[:20]+'.webp';target=s.ROOT/'assets'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        # A unique temporary name also handles identical artwork across tokens.
        temporary=target.with_name(name+'.'+key[:12]+'.tmp');temporary.write_bytes(webp);os.replace(temporary,target)
        with LOCK:CACHE[key]=name;RETRY.pop(key,None)
        return True
    except Exception:return False


def once(maximum=12,workers=2):
    import nadfun
    # Registry metadata only: no chain reads, authentication or financial execution.
    tokens=nadfun.catalog(sort='cap')['tokens']+nadfun.catalog()['tokens']
    urls=list(dict.fromkeys(t.get('logoURI') for t in tokens if safe(t.get('logoURI'))))
    pending=[url for url in urls if not ready(url) and RETRY.get(hashlib.sha256(url.encode()).hexdigest(),0)<=time.time()][:maximum]
    with ThreadPoolExecutor(max_workers=workers) as pool:results=list(pool.map(collect,pending))
    with LOCK:
        while len(CACHE)>2048:CACHE.pop(next(iter(CACHE)))
        data=dict(CACHE)
    if len(data)==2048:
        keep=set(data.values())
        for path in (s.ROOT/'assets').glob('token-art-*.webp'):
            if path.name not in keep and re.fullmatch(r'token-art-[a-f0-9]{20}\.webp',path.name):path.unlink(missing_ok=True)
    temporary=s.STATE/'token-art-map.json.tmp';temporary.write_text(json.dumps(data));os.replace(temporary,s.STATE/'token-art-map.json')
    return {'attempted':len(pending),'collected':sum(results),'ready':sum(bool(ready(url)) for url in urls),'sources':len(urls)}


def decorate(tokens):
    for token in tokens:
        thumbnail=ready(token.get('logoURI'))
        if thumbnail:token['logoThumbURI']=thumbnail
    return tokens


def background():
    restore()
    while True:
        try:once()
        except Exception:pass
        time.sleep(45)
