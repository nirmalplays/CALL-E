import json
from datetime import datetime, timedelta, timezone

from tests.test_local_api import client, seed  # noqa: F401 - pytest fixtures
from medai_readback.local_api import workflow


def test_config_never_leaks_secrets(client, monkeypatch):
    monkeypatch.setenv('CALLE_API_KEY', 'super-secret-key-value')
    body = client.get('/local/config').text
    assert client.get('/local/config').status_code == 200
    for secret in ('super-secret-key-value', 's' * 40, '+12025550123'):
        assert secret not in body, 'configuration endpoint leaked a secret'
    data = json.loads(body)
    assert data['calling']['allowed_phone_count'] == 1, 'count only, never the numbers'
    assert data['calling']['provider_host'] and '/' not in data['calling']['provider_host']


def test_config_requires_staff_auth(client):
    assert client.get('/local/config', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.post('/local/config/budget', json={'limit': 1},
                       headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_working_limit_cannot_exceed_the_env_ceiling(client, monkeypatch):
    monkeypatch.setenv('CALLE_CALL_BUDGET', '3')
    assert client.post('/local/config/budget', json={'limit': 2}).json()['working_limit'] == 2
    assert client.get('/local/readiness').json()['local_budget'] == 2

    over = client.post('/local/config/budget', json={'limit': 99})
    assert over.status_code == 409
    assert '3' in over.json()['detail']
    assert client.get('/local/readiness').json()['local_budget'] == 2, 'a refused raise changes nothing'


def test_lowering_the_ceiling_in_env_also_lowers_a_stored_limit(client, monkeypatch):
    monkeypatch.setenv('CALLE_CALL_BUDGET', '5')
    client.post('/local/config/budget', json={'limit': 5})
    monkeypatch.setenv('CALLE_CALL_BUDGET', '2')
    assert client.get('/local/readiness').json()['local_budget'] == 2, 'env stays the hard cap'


def test_zero_working_limit_blocks_dispatch(client, monkeypatch):
    monkeypatch.setenv('CALLE_CALL_BUDGET', '4')
    doc = seed(client)
    client.post('/local/config/budget', json={'limit': 0})
    assert 'No call budget configured' in client.get('/local/readiness').json()['blockers']
    assert client.post('/local/confirmations/' + doc['call_id'] + '/dispatch').status_code == 409
    assert workflow().budget() == 0, 'a blocked dispatch reserves nothing'


def test_negative_limit_is_rejected(client):
    assert client.post('/local/config/budget', json={'limit': -1}).status_code == 422


def test_worker_state_reports_stopped_until_a_heartbeat_arrives(client):
    assert client.get('/local/config').json()['automation'] == {
        'running': False, 'seen_at': None, 'age_seconds': None, 'mode': None}

    fresh = datetime.now(timezone.utc).isoformat()
    workflow().set_state('worker_heartbeat', json.dumps({'at': fresh, 'mode': 'live', 'pid': 1}))
    state = client.get('/local/config').json()['automation']
    assert state['running'] is True and state['mode'] == 'live'

    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    workflow().set_state('worker_heartbeat', json.dumps({'at': stale, 'mode': 'live', 'pid': 1}))
    state = client.get('/local/config').json()['automation']
    assert state['running'] is False, 'a worker silent for 5 minutes is not running'
    assert state['age_seconds'] >= 300

    workflow().set_state('worker_heartbeat', 'not json')
    assert client.get('/local/config').json()['automation']['running'] is False


def test_readiness_carries_worker_state(client):
    assert 'worker' in client.get('/local/readiness').json()
