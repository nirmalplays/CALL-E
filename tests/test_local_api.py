import pytest
from fastapi.testclient import TestClient
import app
from medai_readback.local_api import workflow
from medai_readback.calle import CalleService

MED=dict(name='Medicine A',dosage='10mg',quantity='1',schedule=['MORNING'],duration='2 days',instructions='after food')

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDAI_DB_PATH',str(tmp_path/'http.sqlite3'))
    monkeypatch.setenv('MEDAI_STAFF_TOKEN','s'*40)
    monkeypatch.setenv('MEDAI_TENANT_ID','test')
    monkeypatch.setenv('CALLE_VERIFIED_LOCALES','en-IN')
    monkeypatch.setenv('CALLE_ENABLE_LIVE_CALLS','false')
    monkeypatch.setenv('CALLE_ALLOWED_PHONES','+12025550123')
    monkeypatch.setenv('CALLE_CALL_BUDGET','1')
    monkeypatch.setenv('MEDAI_PUBLIC_BASE_URL','https://example.test')
    with TestClient(app.app,headers={'Authorization':'Bearer '+'s'*40}) as c:yield c

def seed(client):
    assert client.put('/local/patients',json=dict(patient_id='p1',name='Test Patient',phone='+12025550123',language='en-IN',region='IN',consent=True,consent_evidence='Explicit test consent')).status_code==200
    r=client.post('/local/intakes',json=dict(patient_id='p1',source_id='source1',medications=[MED]))
    assert r.status_code==200,r.text
    return r.json()

def test_preview_never_dispatches_and_live_disabled(client,monkeypatch):
    async def forbidden(*a,**kw):raise AssertionError('must not call provider')
    monkeypatch.setattr(CalleService,'get_instance',forbidden)
    doc=seed(client)
    assert 'webhook_token' not in doc
    assert client.get('/local/confirmations/'+doc['call_id']+'/preview').json()['calls_placed']==0
    assert client.post('/local/confirmations/'+doc['call_id']+'/dispatch').status_code==409
    assert workflow().budget()==0

def test_http_confirmation_correction_review_and_schedule(client,monkeypatch):
    captured=[]
    class Fake:
        async def call(self,**kwargs):
            captured.append(kwargs)
            return {'call_sid':'call_test'}
    async def provider():return Fake()
    monkeypatch.setattr(CalleService,'get_instance',provider)
    monkeypatch.setenv('CALLE_ENABLE_LIVE_CALLS','true')
    doc=seed(client);key=doc['call_id']
    assert client.post(f'/local/confirmations/{key}/dispatch').status_code==200
    assert client.post(f'/local/confirmations/{key}/dispatch').status_code==409
    assert len(captured)==1
    payload={'id':'evt1','type':'call.completed','data':{'id':'call_test','status':'completed',
        'metadata':captured[0]['metadata'],'structured_result':{'reached_patient':'yes','overall':'corrected',
        'medications':[{'name_as_read':'Medicine A','status':'corrected','correction_text':'Please verify dose'}]}}}
    path='/local/webhook/'+workflow().get('confirmation',key)['webhook_token']
    assert client.post(path,json=payload).status_code==422
    assert client.post('/local/webhook/wrong',json=payload,headers={'CALL-E-Event-Id':'evt1'}).status_code==403
    r=client.post(path,json=payload,headers={'CALL-E-Event-Id':'evt1'})
    assert r.status_code==200 and r.json()['disposition']=='review'
    assert client.post(path,json=payload,headers={'CALL-E-Event-Id':'evt1'}).json()['status']=='duplicate'
    r=client.post(f'/local/confirmations/{key}/approve',json={'version':1,'reason':'Verified original with clinician','medications':[dict(MED,dosage='20mg')]})
    assert r.status_code==200 and r.json()['status']=='confirmed'
    from datetime import datetime,timedelta,timezone
    due=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    assert client.post(f'/local/confirmations/{key}/schedule',json={'due_at':[due],'version':2,'medication_names':['Medicine A']}).status_code==200
    assert len(client.get('/local/jobs').json())==1

def test_auth_and_missing_consent(client):
    assert client.get('/local/confirmations',headers={'Authorization':''}).status_code==401
    assert client.post('/local/intakes',json={'patient_id':'unknown','source_id':'s','medications':[MED]}).status_code==403

def test_reconcile_resolves_when_no_webhook_can_arrive(client,monkeypatch):
    class Fake:
        async def call(self,**kw):return {'call_sid':'call_test'}
        async def get_call_details(self,call_sid):
            assert call_sid=='call_test'
            return {'status':'completed','state':'terminal','call_details':{'id':'call_test','status':'completed',
                'structured_result':{'reached_patient':'yes','overall':'confirmed',
                    'medications':[{'name_as_read':'Medicine A','status':'confirmed','correction_text':''}]}}}
    async def provider():return Fake()
    monkeypatch.setattr(CalleService,'get_instance',provider)
    monkeypatch.setenv('CALLE_ENABLE_LIVE_CALLS','true')
    doc=seed(client);key=doc['call_id']
    assert client.post(f'/local/confirmations/{key}/reconcile').status_code==409
    assert client.post(f'/local/confirmations/{key}/dispatch').status_code==200
    assert client.post(f'/local/confirmations/{key}/reconcile').json()['disposition']=='confirmed'
    assert workflow().get('confirmation',key)['status']=='confirmed'
    assert workflow().budget()==1

def test_timeout_preserves_budget_no_redial(client,monkeypatch):
    class Fake:
        async def call(self,**kw):raise TimeoutError()
    async def provider():return Fake()
    monkeypatch.setattr(CalleService,'get_instance',provider)
    monkeypatch.setenv('CALLE_ENABLE_LIVE_CALLS','true')
    doc=seed(client);key=doc['call_id']
    assert client.post(f'/local/confirmations/{key}/dispatch').status_code==502
    assert client.post(f'/local/confirmations/{key}/dispatch').status_code==409
    assert workflow().budget()==1
