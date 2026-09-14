# Runs the dashboard call-placement regression under Node, and pins the
# staff-facing blocker guidance to the strings live_settings() actually emits.
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from medai_readback.local_api import live_settings

ROOT = Path(__file__).resolve().parents[1]
LIVE_VARS = ('CALLE_ENABLE_LIVE_CALLS', 'CALLE_CALL_BUDGET', 'CALLE_ALLOWED_PHONES',
             'MEDAI_PUBLIC_BASE_URL', 'CALLE_VERIFIED_LOCALES', 'CALLE_API_KEY')


@pytest.mark.skipif(not shutil.which('node'), reason='Node is not installed')
def test_dashboard_call_placement(monkeypatch):
    for name in LIVE_VARS:
        monkeypatch.delenv(name, raising=False)
    blockers, *_ = live_settings()
    assert blockers, 'every live-call blocker should be raised with no configuration present'
    result = subprocess.run(
        ['node', str(ROOT / 'tests' / 'test_dashboard_calls.cjs'),
         str(ROOT / 'medai_readback' / 'local_dashboard.js'), json.dumps(blockers)],
        capture_output=True, text=True, cwd=ROOT, env={**os.environ, 'NODE_OPTIONS': ''})
    assert result.returncode == 0, result.stdout + result.stderr
