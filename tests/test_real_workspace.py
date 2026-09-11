"""Integration coverage for the user-entered workspace, in isolated storage."""
import pytest
from fastapi.testclient import TestClient
import app
from medai_readback.local_api import workflow

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MEDAI_DB_PATH', str(tmp_path/'workspace.sqlite3'))
    monkeypatch.setenv('MEDAI_STAFF_TOKEN', 'workspace-test-token-'+'x'*32)
    monkeypatch.setenv('MEDAI_TENANT_ID', 'workspace-test')
    monkeypatch.setenv('CALLE_ENABLE_LIVE_CALLS', 'false')
    monkeypatch.setenv('CALLE_VERIFIED_LOCALES', '')
    with TestClient(app.app, headers={'Authorization':'Bearer workspace-test-token-'+'x'*32}) as c:
        yield c

def add_record(client, identifier):
    patient = dict(patient_id=identifier, name='User entered patient', phone='+12025550123',
        language='en-IN', region='US', consent=True, consent_evidence='Isolated integration test consent')
    assert client.put('/local/patients', json=patient).status_code == 200
    prescription = dict(patient_id=identifier, source_id='entered-source', medications=[dict(
        name='Entered medicine', dosage='entered dose', quantity='1', schedule=['MORNING'],
        duration='2 days', instructions='Entered instructions')])
    response=client.post('/local/intakes', json=prescription)
    assert response.status_code == 200
    return response.json()

def test_user_input_appears_without_fixture_substitution_or_calls(client):
    record=add_record(client, 'actual-input')
    assert record['medications'][0]['name']=='Entered medicine'
    assert client.get('/local/patients').json()[0]['name']=='User entered patient'
    assert client.get('/local/confirmations').json()[0]['source_id']=='entered-source'
    assert record['status']=='fallback'
    assert workflow().budget()==0
    assert client.get('/local/patients',headers={'Authorization':''}).status_code==401

def test_seeded_sample_hidden_but_preserved(client):
    sample=add_record(client,'sample')
    service=workflow()
    with service.transaction() as conn:
        stored=service._get(conn,'confirmation',sample['call_id'])
        stored['demo_seeded']=True
        service._put(conn,'confirmation',sample['call_id'],stored)
    assert client.get('/local/patients').json()==[]
    assert client.get('/local/confirmations').json()==[]
    assert service.get('confirmation',sample['call_id'])['demo_seeded'] is True

def test_consent_cannot_be_skipped_on_new_input(client):
    response=client.put('/local/patients',json=dict(patient_id='no-consent',name='Test',phone='+12025550123',language='en-IN',region='US',consent=False,consent_evidence='Not granted'))
    assert response.status_code==200
    response=client.post('/local/intakes',json=dict(patient_id='no-consent',source_id='s',medications=[dict(name='M',dosage='D',quantity='1',schedule=['MORNING'],duration='1 day',instructions='')]))
    assert response.status_code==403
