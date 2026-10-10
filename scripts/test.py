"""Run fixture tests in disposable state. No production state or provider access."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
tests=['test_social_loop.py','test_algorithms.py','test_auth.py','test_discovery.py','test_launch_activity.py','test_loading.py','test_token_images.py','test_launch_ingestion.py','test_execution.py','test_privy.py','test_native_auth.py','test_wallet_assets.py','test_preflight.py']
for name in tests:
    with tempfile.TemporaryDirectory(prefix='rally-tests-') as directory:
        env={**os.environ,'RALLY_TESTING':'1','RALLY_STATE_DIR':directory,
             'PYTHONPATH':os.pathsep.join(filter(None,[str(root),os.environ.get('PYTHONPATH','')])),
             'RALLY_RPC_URL':'https://rpc.invalid','RALLY_COMMUNITY_FACTORY':'',
             'RALLY_COMMUNITY_DEPLOYER':'','RALLY_PRIVY_APP_ID':'',
             'RALLY_AGENT_BRIDGE_CONFIG':str(Path(directory)/'unpaired.json')}
        subprocess.run([sys.executable,str(root/'tests'/name)],cwd=root,env=env,check=True)
print('All isolated Python suites passed; no mainnet transactions or signatures.')
