"""Offline smoke test first, then optional full regression suite.

python verify.py
python verify.py --full

Uses a dummy API key and blocks external sockets. No call credits are used.
"""
import ast
import contextlib
import io
import os
from pathlib import Path
import runpy
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
full='--full' in sys.argv
sys.dont_write_bytecode=True
os.chdir(ROOT)
os.environ.update(CALLE_API_KEY='offline-verification',CALLE_BASE_URL='https://offline.invalid',
    CALLE_ENABLE_LIVE_CALLS='false',MEDAI_STAFF_TOKEN='offline-test-token-'+'x'*32,
    MEDAI_TENANT_ID='offline',MEDAI_ENABLE_LEGACY_DEMO='false',CALLE_VERIFIED_LOCALES='en-IN')
def guard(event,args):
    if event=='socket.connect' and args[1][0] in ('127.0.0.1','::1'):return
    if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):
        raise RuntimeError('External network forbidden during offline verification')
sys.addaudithook(guard)
for folder in (ROOT,ROOT/'medai_readback',ROOT/'ocr',ROOT/'tests'):
    for source in folder.glob('*.py'):ast.parse(source.read_text(encoding='utf-8'))
print('PASS Python syntax')
with tempfile.TemporaryDirectory(prefix='medai-offline-') as temp:
    os.environ['MEDAI_DB_PATH']=str(Path(temp)/'test.sqlite3')
    from fastapi.testclient import TestClient
    import app
    with TestClient(app.app) as client:
        assert client.get('/health').status_code==200
        assert client.get('/local/dashboard').status_code==200
        assert client.get('/local/confirmations').status_code==401
        assert client.get('/demo/confirmations').status_code==404
        headers={'Authorization':'Bearer '+os.environ['MEDAI_STAFF_TOKEN']}
        assert client.get('/local/confirmations',headers=headers).json()==[]
        assert not client.get('/local/readiness',headers=headers).json()['configured_for_live']
    for scenario in ('demo-clean','demo-misread-dose'):
        sys.argv=['demo_call.py',scenario,'--dry-run']
        with contextlib.redirect_stdout(io.StringIO()) as output:
            runpy.run_path(str(ROOT/'demo_call.py'),run_name='__main__')
        assert 'result_schema' in output.getvalue()
    sys.argv=['worker.py','--once']
    with contextlib.redirect_stdout(io.StringIO()) as output:
        runpy.run_path(str(ROOT/'worker.py'),run_name='__main__')
    assert 'dry-run' in output.getvalue()
    print('PASS startup, authentication, preview scenarios, disabled live dispatch, worker dry run')
    if full:
        import pytest
        code=pytest.main(['tests/','skills/prescription-readback/scripts/','-q','-p','no:cacheprovider'])
        if code:raise SystemExit(code)
print('PASS verification; no external API requests or phone calls')
