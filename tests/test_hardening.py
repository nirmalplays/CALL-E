import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from tests.test_local_api import client
from tests.test_workflow import flow, intake
from medai_readback.workflow import Workflow, WorkflowError, Patient
from medai_readback.local_api import workflow
from operations import backup


def test_named_staff_audit_and_revoked_key(client, monkeypatch):
    monkeypatch.setenv('MEDAI_STAFF_KEYS', json.dumps({'reviewer-one': 'k'*40}))
    assert client.get('/local/patients').status_code == 401
    headers = {'Authorization': 'Bearer ' + 'k'*40}
    r = client.put('/local/patients', headers=headers, json=dict(patient_id='audit-p', name='Test', phone='+12025550123', language='en-IN', region='IN', consent=True, consent_evidence='test'))
    assert r.status_code == 200
    with sqlite3.connect(workflow().path) as conn:
        assert conn.execute('SELECT actor FROM audit ORDER BY seq DESC LIMIT 1').fetchone()[0] == 'reviewer-one'


def test_large_json_rejected_before_validation(client):
    r = client.post('/local/patients', content=b'x'*1_000_001)
    assert r.status_code == 413


def test_dashboard_csp_and_external_script(client):
    r = client.get('/local/dashboard')
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert '<script>' not in r.text
    assert client.get('/local/dashboard.js').status_code == 200


def test_cannot_overwrite_other_tenant_patient(flow):
    other = Workflow(flow.path, 'other')
    with pytest.raises(WorkflowError):
        other.patient(Patient(patient_id='p1',name='Intruder',phone='+12025550123',language='en-IN',region='IN',consent=True,consent_evidence='test'),'other')
    assert flow.get('patient','p1')['name'] != 'Intruder'


def test_region_change_blocks_old_prescription(flow):
    d = intake(flow)
    p = flow.get('patient','p1')
    fields = {k:v for k,v in p.items() if k in Patient.model_fields}
    fields['region'] = 'US'
    flow.patient(Patient(**fields), 'staff')
    with pytest.raises(WorkflowError):
        flow.reserve_call(d['call_id'],1,{'+12025550123'})
    assert flow.budget() == 0


def test_backup_restores_records_and_never_overwrites(flow,tmp_path):
    d = intake(flow)
    target = backup(flow.path,tmp_path/'backup.sqlite3')
    assert Workflow(target,'test').get('confirmation',d['call_id'])['patient_id'] == 'p1'
    with pytest.raises(FileExistsError):
        backup(flow.path,target)


def test_production_app_requires_config_and_excludes_demo(monkeypatch,tmp_path):
    import production
    monkeypatch.delenv('MEDAI_STAFF_KEYS',raising=False)
    assert production.configuration_errors()
    monkeypatch.setenv('MEDAI_STAFF_KEYS',json.dumps({'staff':'p'*40}))
    monkeypatch.setenv('MEDAI_TENANT_ID','clinic')
    monkeypatch.setenv('MEDAI_DB_PATH',str(tmp_path/'production.sqlite3'))
    monkeypatch.setenv('MEDAI_ALLOWED_HOSTS','testserver')
    monkeypatch.setenv('MEDAI_ENABLE_LEGACY_DEMO','false')
    with TestClient(production.create_app()) as c:
        assert c.get('/health').status_code == 200
        assert c.get('/demo/scans').status_code == 404
        assert c.get('/openapi.json').status_code == 404
        assert c.get('/health',headers={'Host':'unexpected.example'}).status_code == 400
