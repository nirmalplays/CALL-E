import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from medai_readback.workflow import Workflow, WorkflowError, Patient, Intake, Review, ScheduleRequest

MED = dict(name='Medicine A', dosage='10mg', quantity='1', schedule=['MORNING'], duration='2 days', instructions='after food')

@pytest.fixture
def flow(tmp_path):
    f = Workflow(tmp_path/'state.sqlite3', 'test')
    f.patient(Patient(patient_id='p1', name='Test Patient', phone='+12025550123', language='en-IN', region='IN', consent=True, consent_evidence='Test consent'), 'tester')
    return f

def intake(flow, locales={'en-IN'}):
    return flow.intake(Intake(patient_id='p1', source_id='scan1', medications=[MED]), locales)

def payload(doc, overall='confirmed', event='call.completed'):
    return {'id':'evt1','type':event,'data':{'id':'call_test','status':'completed',
        'metadata':{'call_id':doc['call_id'],'patient_id':'p1','tenant_id':'test'},
        'structured_result':{'reached_patient':'yes','overall':overall,'medications':[{'name_as_read':'Medicine A','status':overall,'correction_text':'check dose' if overall=='corrected' else ''}]}}}

def sent(flow):
    d=intake(flow)
    flow.reserve_call(d['call_id'],1,{'+12025550123'})
    flow.record_dispatch(d['call_id'],{'call_sid':'call_test'})
    return d

def details(status='completed', overall='confirmed'):
    return {'id':'call_test','status':status,
        'structured_result':{'reached_patient':'yes','overall':overall,'medications':[{'name_as_read':'Medicine A','status':overall,'correction_text':'check dose' if overall=='corrected' else ''}]}}

def test_reconcile_resolves_a_call_with_no_webhook(flow):
    d=sent(flow)
    assert flow.reconcile(d['call_id'],details())['disposition']=='confirmed'
    assert flow.get('confirmation',d['call_id'])['approved_medications']==[MED]

def test_reconcile_is_idempotent_and_a_late_webhook_cannot_re_resolve(flow):
    d=sent(flow)
    flow.reconcile(d['call_id'],details())
    assert flow.reconcile(d['call_id'],details(overall='corrected'))['disposition']=='confirmed'
    assert flow.event(d['webhook_token'],'evt1',payload(d,'corrected'))['disposition']=='confirmed'

@pytest.mark.parametrize('status',['failed','canceled'])
def test_reconcile_of_a_failed_call_cannot_approve(flow,status):
    d=sent(flow)
    assert flow.reconcile(d['call_id'],details(status=status))['disposition']=='fallback'
    assert 'approved_medications' not in flow.get('confirmation',d['call_id'])

def test_reconcile_leaves_an_active_call_pending(flow):
    d=sent(flow)
    assert flow.reconcile(d['call_id'],details(status='queued'))=={'status':'active','call_status':'queued'}
    assert flow.get('confirmation',d['call_id'])['status']=='pending'

def test_reconcile_rejects_another_calls_result(flow):
    d=sent(flow)
    with pytest.raises(WorkflowError):flow.reconcile(d['call_id'],dict(details(),id='call_other'))
    assert flow.get('confirmation',d['call_id'])['status']=='pending'

def test_reconcile_requires_a_submitted_call_with_a_provider_id(flow):
    d=intake(flow)
    with pytest.raises(WorkflowError):flow.reconcile(d['call_id'],details())
    flow.reserve_call(d['call_id'],1,{'+12025550123'});flow.record_dispatch(d['call_id'])
    with pytest.raises(WorkflowError):flow.reconcile(d['call_id'],details())

def test_restart_preserves_records_and_budget(flow):
    d=sent(flow)
    other=Workflow(flow.path,'test')
    assert other.get('confirmation',d['call_id'])['provider_id']=='call_test'
    assert other.budget()==1

def test_intake_idempotent_but_changed_regimen_has_new_id(flow):
    a=intake(flow)
    assert intake(flow)['call_id']==a['call_id']
    b=flow.intake(Intake(patient_id='p1',source_id='scan1',medications=[dict(MED,dosage='20mg')]),{'en-IN'})
    assert b['call_id']!=a['call_id']

def test_concurrent_dispatch_reserves_one_credit(flow):
    d=intake(flow)
    def attempt(_):
        try: flow.reserve_call(d['call_id'],1,{'+12025550123'}); return True
        except WorkflowError: return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8)))==1
    assert flow.budget()==1

def test_budget_and_allowlist_fail_closed(flow):
    d=intake(flow)
    for budget,phones in [(0,{'+12025550123'}),(1,set())]:
        with pytest.raises(WorkflowError):flow.reserve_call(d['call_id'],budget,phones)
    assert flow.budget()==0

def test_uncertain_response_cannot_redial(flow):
    d=sent(flow);flow.record_dispatch(d['call_id'])
    with pytest.raises(WorkflowError):flow.reserve_call(d['call_id'],10,{'+12025550123'})
    assert flow.budget()==1

def test_locale_fallback_is_persisted(flow):
    d=intake(flow,set())
    assert d['status']=='fallback' and d['fallback_reason']=='unsupported_language'
    assert len(flow.list('confirmation'))==1

def test_webhook_capability_and_correlation(flow):
    d=sent(flow)
    with pytest.raises(WorkflowError):flow.event('bad','evt1',payload(d))
    p=payload(d);p['data']['metadata']['tenant_id']='other'
    with pytest.raises(WorkflowError):flow.event(d['webhook_token'],'evt1',p)
    assert flow.get('confirmation',d['call_id'])['status']=='pending'

def test_confirmation_is_not_false_scheduling_and_event_is_idempotent(flow):
    d=sent(flow)
    assert flow.event(d['webhook_token'],'evt1',payload(d))['disposition']=='confirmed'
    assert flow.list('job')==[]
    assert flow.event(d['webhook_token'],'evt1',payload(d))['status']=='duplicate'

@pytest.mark.parametrize('event',['call.failed','call.result_validation_failed'])
def test_failure_event_cannot_approve(flow,event):
    d=sent(flow)
    assert flow.event(d['webhook_token'],'evt1',payload(d,event=event))['disposition']=='fallback'

def test_staff_review_does_not_overwrite_extraction_and_jobs_survive_restart(flow):
    d=sent(flow)
    flow.event(d['webhook_token'],'evt1',payload(d,'corrected'))
    approved=flow.review(d['call_id'],Review(medications=[dict(MED,dosage='20mg')],reason='Verified source',version=1),'reviewer')
    assert approved['medications'][0]['dosage']=='10mg'
    assert approved['approved_medications'][0]['dosage']=='20mg'
    request=ScheduleRequest(medication_names=['Medicine A'],due_at=[datetime.now(timezone.utc)+timedelta(days=1)],version=2)
    flow.schedule(d['call_id'],request,'reviewer');flow.schedule(d['call_id'],request,'reviewer')
    assert len(Workflow(flow.path,'test').list('job'))==1
    with pytest.raises(WorkflowError):flow.review(d['call_id'],Review(medications=[MED],reason='stale',version=1),'reviewer')

def test_revocation_blocks_intake_dispatch_and_scheduling(flow):
    d=sent(flow)
    flow.patient(Patient(patient_id='p1',name='Test',phone='+12025550123',language='en-IN',region='IN',consent=False,consent_evidence='Withdrawn'),'tester')
    with pytest.raises(WorkflowError):intake(flow)
    assert flow.event(d['webhook_token'],'evt1',payload(d))['disposition']=='fallback'
    with pytest.raises(WorkflowError):flow.schedule(d['call_id'],ScheduleRequest(medication_names=['Medicine A'],due_at=[datetime.now(timezone.utc)+timedelta(days=1)],version=1),'tester')

def test_revocation_cancels_existing_jobs(flow):
    d=sent(flow);flow.event(d['webhook_token'],'evt1',payload(d))
    flow.schedule(d['call_id'],ScheduleRequest(medication_names=['Medicine A'],due_at=[datetime.now(timezone.utc)+timedelta(days=1)],version=1),'tester')
    flow.patient(Patient(patient_id='p1',name='Test',phone='+12025550123',language='en-IN',region='IN',consent=False,consent_evidence='Withdrawn'),'tester')
    assert flow.list('job')[0]['status']=='cancelled_consent'


def test_due_job_reservation_and_escalation_share_budget(flow):
    flow.patient(Patient(patient_id='p1',name='Test',phone='+12025550123',language='en-IN',region='IN',
        consent=True,consent_evidence='Consented test',caregiver_name='Caregiver',caregiver_phone='+12025550124',
        caregiver_language='en-IN',caregiver_region='IN'),'tester')
    d=sent(flow);flow.event(d['webhook_token'],'evt1',payload(d))
    flow.schedule(d['call_id'],ScheduleRequest(medication_names=['Medicine A'],due_at=[datetime.now(timezone.utc)+timedelta(days=1)],version=1),'tester')
    job=flow.list('job')[0]
    with flow.transaction() as c:
        job['due_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        flow._put(c,'job',job['job_id'],job)
    assert len(flow.due_jobs())==1
    with pytest.raises(WorkflowError):flow.reserve_job(job['job_id'],1,{'+12025550123'})
    reserved,_=flow.reserve_job(job['job_id'],2,{'+12025550123'})
    flow.record_job_dispatch(job['job_id'],{'call_sid':'call_adherence'})
    event={'id':'evt2','type':'call.completed','data':{'id':'call_adherence','status':'completed',
        'metadata':{'call_id':job['job_id'],'job_id':job['job_id'],'tenant_id':'test','patient_id':'p1'},
        'structured_result':{'outcome':'refusing','reason':'Needs care team'}}}
    assert flow.job_event(job['webhook_token'],'evt2',event)['disposition']=='completed'
    assert flow.job_event(job['webhook_token'],'evt2',event)['status']=='duplicate'
    escalation=flow.due_jobs()[0]
    assert escalation['kind']=='escalation'
    with pytest.raises(WorkflowError):flow.reserve_job(escalation['job_id'],2,{'+12025550124'})
    assert flow.budget()==2
