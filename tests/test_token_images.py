"""Artwork scope, size and cache boundaries; synthetic images, no providers."""
import io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
import token_images as art,service as s,live_server


class Artwork(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'assets').mkdir();(self.root/'state').mkdir()
        self.a=patch.object(s,'ROOT',self.root);self.b=patch.object(s,'STATE',self.root/'state');self.a.start();self.b.start()
        art.CACHE.clear();art.RETRY.clear();self.url='https://storage.nadapp.net/coin/12345678-abcd'
    def tearDown(self):self.a.stop();self.b.stop();self.tmp.cleanup();art.CACHE.clear();art.RETRY.clear()
    def test_only_exact_public_registry_origin_and_path(self):
        self.assertTrue(art.safe(self.url))
        for value in [None,'https://[','http://storage.nadapp.net/coin/12345678','https://storage.nadapp.net.evil.test/coin/12345678','https://storage.nadapp.net@127.0.0.1/coin/12345678','https://storage.nadapp.net:443/coin/12345678','https://storage.nadapp.net/coin/12345678?target=http://localhost','https://storage.nadapp.net/../private','/media/private-upload']:
            self.assertFalse(art.safe(value),value)
    def test_redirects_never_leave_allowlisted_source(self):
        with self.assertRaises(ValueError):art.NoRedirect().redirect_request(None,None,None,None,'https://127.0.0.1/',None)
    def test_source_pixels_become_small_webp(self):
        buf=io.BytesIO();Image.new('RGBA',(900,600),(31,40,80,100)).save(buf,format='PNG')
        encoded=art.encode(buf.getvalue())
        with Image.open(io.BytesIO(encoded)) as out:
            self.assertEqual(out.format,'WEBP');self.assertEqual(out.size,(96,64));self.assertIn('A',out.getbands())
        self.assertLess(len(encoded),2000)
    def test_oversized_and_non_images_rejected(self):
        for body in [b'x'*(art.LIMIT+1),b'<svg></svg>',b'not an image']:
            with self.assertRaises(Exception):art.encode(body)
    def test_missing_cache_never_replaces_original(self):
        tokens=[{'id':'exact-address','logoURI':self.url,'price':1.25,'referenceAt':100}]
        self.assertIsNone(art.ready(self.url));self.assertEqual(art.decorate(tokens),tokens);self.assertNotIn('logoThumbURI',tokens[0])
    def test_ready_derivative_retains_identity_source_and_price(self):
        import hashlib
        name='token-art-'+'1'*20+'.webp';(self.root/'assets'/name).write_bytes(b'fixture')
        art.CACHE[hashlib.sha256(self.url.encode()).hexdigest()]=name
        original={'id':'exact-address','logoURI':self.url,'price':1.25,'referenceAt':100};token=dict(original)
        art.decorate([token]);self.assertEqual(token.pop('logoThumbURI'),'/assets/'+name);self.assertEqual(token,original)
    def test_restored_manifest_cannot_reveal_private_media(self):
        import hashlib
        key=hashlib.sha256(self.url.encode()).hexdigest()
        (self.root/'state/token-art-map.json').write_text(json.dumps({key:'../private/secret.webp'}))
        art.restore();self.assertIsNone(art.ready(self.url));self.assertEqual(art.CACHE,{})
    def test_invalid_url_does_not_open_network(self):
        with patch.object(art.urllib.request,'build_opener',side_effect=AssertionError('No provider call')):
            self.assertFalse(art.collect('https://localhost/'));self.assertFalse(art.collect('/media/private'))

    def test_derivative_works_with_read_only_app_assets(self):
        buf=io.BytesIO();Image.new('RGB',(200,100),(20,30,40)).save(buf,format='PNG');body=buf.getvalue()
        class Response:
            headers={'Content-Length':str(len(body))}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,limit):return body[:limit]
        class Opener:
            def open(self,*a,**kw):return Response()
        assets=self.root/'assets';assets.chmod(0o555)
        try:
            with patch.object(art.urllib.request,'build_opener',return_value=Opener()):self.assertTrue(art.collect(self.url))
            name=art.ready(self.url).rsplit('/',1)[-1];target=art.file(name)
            self.assertEqual(target.parent,self.root/'state/token-art');self.assertTrue(art.public(target));self.assertEqual(list(assets.iterdir()),[])
        finally:assets.chmod(0o755)
    def test_public_derivative_path_cannot_resolve_private_files_or_symlinks(self):
        store=self.root/'state/token-art';store.mkdir();secret=self.root/'state/secret';secret.write_text('private')
        name='token-art-'+'1'*20+'.webp';(store/name).symlink_to(secret)
        for value in ['../secret','token-art-../secret.webp','rally.sqlite3',name]:self.assertIsNone(art.file(value))
        self.assertFalse(art.public(secret))
    def test_http_derivative_cached_but_private_media_stays_uncached(self):
        store=self.root/'state/token-art';store.mkdir();name='token-art-'+'1'*20+'.webp';target=store/name;target.write_bytes(b'fixture')
        handler=object.__new__(live_server.Handler);handler.headers={};handler.command='GET';handler.wfile=io.BytesIO();headers={}
        handler.send_response=lambda status:headers.update(status=status);handler.send_header=lambda k,v:headers.update({k:v});handler.end_headers=lambda:None
        handler.file(target,'image/webp');self.assertEqual(headers['Cache-Control'],'public,max-age=31536000,immutable')
        private=self.root/'state/private.webp';private.write_bytes(b'private');handler.wfile=io.BytesIO();headers.clear();handler.file(private,'image/webp');self.assertEqual(headers['Cache-Control'],'no-store')

if __name__=='__main__':unittest.main()
