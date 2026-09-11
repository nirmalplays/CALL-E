"""Authenticated local API, explicit previews and budgeted outbound dispatch."""
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from medai_readback.calle import CalleService
from medai_readback.readback import build_readback_task, READBACK_RESULT_SCHEMA
from medai_readback.workflow import Workflow, WorkflowError, Patient, Intake, Review, ScheduleRequest

router = APIRouter(prefix='/local')


def workflow():
    path = os.getenv('MEDAI_DB_PATH') or str(Path(__file__).resolve().parents[1] / 'data' / 'medai.sqlite3')
    return Workflow(path, os.getenv('MEDAI_TENANT_ID', 'local'))


async def staff(authorization: str = Header(default='')):
    import json
    from medai_readback.security import actor
    configured = os.getenv('MEDAI_STAFF_KEYS')
    if configured:
        try:
            keys = json.loads(configured)
            if not isinstance(keys, dict) or not keys or any(not isinstance(v, str) or len(v) < 32 for v in keys.values()):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(503, 'Invalid staff key configuration') from None
        for name, key in keys.items():
            if secrets.compare_digest(authorization.encode(), ('Bearer ' + key).encode()):
                actor.set(name)
                return name
        raise HTTPException(401, 'Staff authentication required')
    token = os.getenv('MEDAI_STAFF_TOKEN', '')
    if len(token) < 32:
        raise HTTPException(503, 'Configure MEDAI_STAFF_TOKEN with at least 32 random characters')
    if not secrets.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, 'Staff authentication required', headers={'WWW-Authenticate': 'Bearer'})
    actor.set('local-staff')
    return 'local-staff'


def locales():
    return {s.strip() for s in os.getenv('CALLE_VERIFIED_LOCALES', '').split(',') if s.strip()}


def public(doc):
    return {k: v for k, v in doc.items() if k != 'webhook_token'}


def live_settings():
    errors = []
    if os.getenv('CALLE_ENABLE_LIVE_CALLS') != 'true':
        errors.append('Live calling disabled')
    try:
        limit = int(os.getenv('CALLE_CALL_BUDGET', '0'))
    except ValueError:
        limit = 0
    if limit < 1:
        errors.append('No call budget configured')
    phones = {p.strip() for p in os.getenv('CALLE_ALLOWED_PHONES', '').split(',') if p.strip()}
    if not phones:
        errors.append('No allowed phone numbers configured')
    url = os.getenv('MEDAI_PUBLIC_BASE_URL', '').rstrip('/')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        errors.append('Public HTTPS base URL missing or invalid')
    if not locales():
        errors.append('No conversationally verified locales configured')
    if not os.getenv('CALLE_API_KEY'):
        errors.append('API key missing')
    return errors, limit, phones, url


@router.get('/readiness', dependencies=[Depends(staff)])
def readiness():
    errors, limit, _, _ = live_settings()
    return {'configured_for_live': not errors, 'blockers': errors,
            'local_budget': limit, 'reserved_calls': workflow().budget(),
            'delivery_verified': False,
            'note': 'Configuration is not proof of phone delivery. No API request is made by this check.'}


@router.put('/patients', dependencies=[Depends(staff)])
def put_patient(body: Patient, actor: str = Depends(staff)):
    return workflow().patient(body, actor)


@router.post('/intakes', dependencies=[Depends(staff)])
def intake(body: Intake):
    if body.source_id.startswith("ocr-"):
        workflow().get("ocr", body.source_id)
        if not body.ocr_reviewed:
            raise HTTPException(422, "Verify medication fields against the original prescription before saving OCR intake.")
    # Accept validated extraction from any OCR pipeline without fixture substitution.
    return public(workflow().intake(body, locales()))


@router.get('/confirmations', dependencies=[Depends(staff)])
def confirmations():
    return [public(d) for d in workflow().list('confirmation') if not d.get('demo_seeded')]


@router.get('/patients', dependencies=[Depends(staff)])
def patients():
    service = workflow()
    sample_ids = {d['patient_id'] for d in service.list('confirmation') if d.get('demo_seeded')}
    return [d for d in service.list('patient') if d['patient_id'] not in sample_ids]


@router.get('/jobs', dependencies=[Depends(staff)])
def jobs():
    service = workflow()
    sample_ids = {d['call_id'] for d in service.list('confirmation') if d.get('demo_seeded')}
    return [public(j) for j in service.list('job') if j['call_id'] not in sample_ids]


@router.get('/confirmations/{key}/preview', dependencies=[Depends(staff)])
def preview(key: str):
    doc = workflow().get('confirmation', key)
    errors, _, _, _ = live_settings()
    task = build_readback_task(doc['patient_name'], doc['medications']) if len(doc['medications']) <= 6 else None
    return {'call_id': key, 'task': task, 'status': doc['status'],
            'result_schema': READBACK_RESULT_SCHEMA, 'language': doc['language'],
            'live_blockers': errors, 'calls_placed': 0}


@router.post('/confirmations/{key}/dispatch', dependencies=[Depends(staff)])
async def dispatch(key: str):
    errors, limit, phones, url = live_settings()
    if errors:
        raise HTTPException(409, errors)
    service = workflow()
    original = service.get('confirmation', key)
    if original['language'] not in locales():
        raise HTTPException(409, 'Language no longer verified')
    task = build_readback_task(original['patient_name'], original['medications'])
    doc = service.reserve_call(key, limit, phones)
    try:
        provider = await CalleService.get_instance()
        result = await provider.call(to_number=doc['phone_number'], task=task,
            result_schema=READBACK_RESULT_SCHEMA,
            metadata={'call_id': key, 'patient_id': doc['patient_id'], 'tenant_id': service.tenant},
            webhook_url=f'{url}/local/webhook/{doc["webhook_token"]}',
            locale=doc['language'], region=doc['region'])
        if not result.get('call_sid') or result['call_sid'] == 'unknown':
            raise RuntimeError('Missing provider ID')
    except Exception:
        service.record_dispatch(key)
        raise HTTPException(502, 'Dispatch outcome uncertain; budget retained. Do not redial before reconciliation.') from None
    return public(service.record_dispatch(key, result))


@router.post('/confirmations/{key}/reconcile', dependencies=[Depends(staff)])
async def reconcile(key: str):
    # Reads provider state for a call already submitted; places none, so this
    # works with live calling disabled and spends no budget.
    service = workflow()
    doc = service.get('confirmation', key)
    if doc['dispatch_state'] != 'submitted' or not doc.get('provider_id'):
        raise HTTPException(409, 'No submitted call with a known provider ID to reconcile')
    try:
        details = await (await CalleService.get_instance()).get_call_details(doc['provider_id'])
    except Exception:
        raise HTTPException(502, 'Could not read call state from the provider') from None
    return service.reconcile(key, details['call_details'])


@router.post('/webhook/{token}')
async def webhook(token: str, request: Request, event_id: str = Header(default='', alias='CALL-E-Event-Id')):
    # CALL-E public SDK documents unsigned hooks. A random per-call URL is an
    # application capability, NOT a provider signature. Redact this route in proxy logs.
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, 'Webhook too large')
    try:
        import json
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(422, 'Invalid JSON') from None
    if not isinstance(payload, dict):
        raise HTTPException(422, 'JSON object required')
    if payload.get('id') != event_id:
        raise HTTPException(422, 'Event header and envelope ID must match')
    data=payload.get('data')
    if isinstance(data,dict) and isinstance(data.get('metadata'),dict) and data['metadata'].get('job_id'):
        return workflow().job_event(token,event_id,payload)
    return workflow().event(token, event_id, payload)


@router.post('/confirmations/{key}/approve', dependencies=[Depends(staff)])
def approve(key: str, body: Review, actor: str = Depends(staff)):
    return public(workflow().review(key, body, actor))


@router.post('/confirmations/{key}/schedule', dependencies=[Depends(staff)])
def schedule(key: str, body: ScheduleRequest, actor: str = Depends(staff)):
    return public(workflow().schedule(key, body, actor))


@router.get('/dashboard', response_class=HTMLResponse)
def dashboard():
    # No PHI embedded before authentication. Token kept in memory only.
    return Path(__file__).with_name('local_dashboard.html').read_text(encoding='utf-8')


async def dispatch_job(key):
    from medai_readback.adherence import build_adherence_task, ADHERENCE_RESULT_SCHEMA
    from medai_readback.escalation import build_escalation_task, ESCALATION_RESULT_SCHEMA
    errors,limit,phones,url=live_settings()
    if errors:raise WorkflowError('; '.join(errors))
    service=workflow()
    job=service.get('job',key)
    patient=service.get('patient',job['patient_id'])
    language=patient['language'] if job['kind']=='adherence' else patient.get('caregiver_language')
    region=patient['region'] if job['kind']=='adherence' else patient.get('caregiver_region')
    if language not in locales() or not region:raise WorkflowError('Recipient language/region not verified')
    if job['kind']=='adherence':
        task=build_adherence_task(patient['name'],job['medication']['name'],job['medication']['dosage'],job['due_at'])
        schema=ADHERENCE_RESULT_SCHEMA
    else:
        task=build_escalation_task(patient.get('caregiver_name') or '',patient['name'],job['medication']['name'],job['patient_outcome'],job['patient_reason'])
        schema=ESCALATION_RESULT_SCHEMA
    snapshot = patient
    job,patient=service.reserve_job(key,limit,phones)
    try:
        if patient != snapshot:
            raise RuntimeError('Recipient changed during dispatch; reconcile before retry')
        provider=await CalleService.get_instance()
        result=await provider.call(to_number=job['phone_number'],task=task,result_schema=schema,
            metadata={'call_id':key,'job_id':key,'patient_id':job['patient_id'],'tenant_id':service.tenant},
            webhook_url=f'{url}/local/webhook/{job["webhook_token"]}',locale=language,region=region)
        if not result.get('call_sid') or result['call_sid']=='unknown':raise RuntimeError('Missing ID')
    except Exception:
        service.record_job_dispatch(key)
        raise WorkflowError('Job dispatch uncertain; budget retained, reconcile before retry',502) from None
    return public(service.record_job_dispatch(key,result))


@router.post('/jobs/{key}/dispatch',dependencies=[Depends(staff)])
async def dispatch_due_job(key:str):
    return await dispatch_job(key)


@router.get('/dashboard.js')
def dashboard_script():
    return Response(Path(__file__).with_name('local_dashboard.js').read_text(encoding='utf-8'), media_type='application/javascript')
