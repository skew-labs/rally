"""Offline UI harness: real handlers, disposable state, no provider or wallet calls."""
import os
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
port=int(os.environ.get('RALLY_PREVIEW_PORT','4258'))
with tempfile.TemporaryDirectory(prefix='rally-ui-') as directory:
    os.environ.update(RALLY_STATE_DIR=directory,RALLY_PORT=str(port),RALLY_PUBLIC_ORIGIN=f'http://127.0.0.1:{port}',RALLY_CDN_BASE='',RALLY_COMMUNITY_FACTORY='',RALLY_COMMUNITY_DEPLOYER='',RALLY_PRIVY_APP_ID='',RALLY_AGENT_BRIDGE_CONFIG=str(Path(directory)/'unpaired.json'))
    import service as s
    def offline(*args,**kwargs):raise s.Problem('Provider unavailable in offline UI fixture',503)
    s.rpc=offline;s.http_json=offline
    import live_server as app
    import discovery
    s.initialize();discovery.initialize();app.agent_wallet.initialize()
    ThreadingHTTPServer(('127.0.0.1',port),app.Handler).serve_forever()
