"""Isolated loading boundaries; no provider calls, auth changes or wallet actions."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING') == '1', 'Use scripts/test.py for isolated tests'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app_assets,service as s,discovery


class Bootstrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(s,'rpc',side_effect=AssertionError('RPC forbidden')),patch.object(s,'http_json',side_effect=AssertionError('HTTP forbidden')):
            s.initialize();discovery.initialize()
    def test_compact_keeps_account_entitlements_and_all_navigation(self):
        with patch.object(s.GATEWAY,'markets',return_value={'tokens':[{'id':'exact-address'}]}) as market:
            full=s.bootstrap(None);market.assert_called_once_with(False);market.reset_mock()
            compact=s.bootstrap(None,include_markets=False);market.assert_not_called()
        self.assertEqual({**full,'marketData':None},compact)
        self.assertIn('feeds',compact);self.assertIn('communityToken',compact);self.assertIn('loginMethods',compact)
    def test_compact_cannot_bypass_scoped_connection(self):
        with self.assertRaises(s.Problem) as out:s.bootstrap({'user':'buyer','grant':'read-only'},include_markets=False)
        self.assertEqual(out.exception.status,403)
    def test_prefetch_viewer_identity(self):
        self.assertIsNone(discovery.catalog(None,{})['viewer'])
        self.assertEqual(discovery.catalog({'user':'buyer','grant':None},{})['viewer'],'buyer')


class Assets(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'assets').mkdir()
        self.source='<head><link rel="stylesheet" href="./live.css" /><link rel="modulepreload" href="./live-app.js" /></head><script src="./theme.js"></script><script type="module" src="./live-app.js"></script>'
        (self.root/'index.html').write_text(self.source);(self.root/'live-app.js').write_text('original');(self.root/'live.css').write_text('body{}')
        self.outputs={}
        for kind,value in [('js','bundled'),('css','bundled styles')]:
            digest=hashlib.sha256(value.encode()).hexdigest();name=f'assets/rally-app-{digest[:20]}.{kind}';(self.root/name).write_text(value);self.outputs[name]=digest
        self.manifest={'js':next(x for x in self.outputs if x.endswith('.js')),'css':next(x for x in self.outputs if x.endswith('.css')),'sources':{x:hashlib.sha256((self.root/x).read_bytes()).hexdigest() for x in ['index.html','live-app.js','live.css']},'outputs':self.outputs}
        self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):(self.root/'app-bundle.json').write_text(json.dumps(self.manifest))
    def test_current_build_reduces_requests_and_preserves_theme(self):
        data=app_assets.current(self.root);self.assertTrue(data)
        html=app_assets.html(self.source,data)
        self.assertEqual(html.count('rel="stylesheet"'),1);self.assertEqual(html.count('rel="modulepreload"'),1)
        self.assertIn('src="./theme.js"',html);self.assertNotIn('src="./live-app.js"',html)
    def test_source_edit_invalidates_bundle_and_restoration_recovers(self):
        self.assertTrue(app_assets.current(self.root));(self.root/'live-app.js').write_text('updated')
        self.assertIsNone(app_assets.current(self.root));(self.root/'live-app.js').write_text('original')
        self.assertTrue(app_assets.current(self.root))
    def test_css_edit_invalidates_bundle(self):
        (self.root/'live.css').write_text('body{color:red}');self.assertIsNone(app_assets.current(self.root))
    def test_tampered_or_missing_output_falls_back(self):
        output=self.root/self.manifest['js'];output.write_text('unexpected')
        self.assertIsNone(app_assets.current(self.root));output.unlink();self.assertIsNone(app_assets.current(self.root))
    def test_manifest_cannot_escape_public_root(self):
        self.manifest['sources']['../private/keys']='a'*64;self.save();self.assertIsNone(app_assets.current(self.root))
    def test_missing_or_malformed_manifest_is_safe(self):
        (self.root/'app-bundle.json').write_text('{');self.assertIsNone(app_assets.current(self.root))
        (self.root/'app-bundle.json').unlink();self.assertIsNone(app_assets.current(self.root))

if __name__=='__main__':unittest.main()
