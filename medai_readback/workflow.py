"""Durable, single-tenant local workflow. No network calls in this module."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator
from medai_readback.confirmations import decide


def now():
    return datetime.now(timezone.utc).isoformat()


class Medication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=100)
    quantity: str = Field(min_length=1, max_length=100)
    schedule: list[str] = Field(min_length=1, max_length=20)

    @field_validator('schedule')
    @classmethod
    def meaningful_schedule(cls, values):
        if any(not v.strip() or len(v) > 200 for v in values):
            raise ValueError('Every timing must be nonblank and at most 200 characters')
        return [v.strip() for v in values]
    duration: str = Field(min_length=1, max_length=100)
    instructions: str = Field(max_length=500)

    @field_validator('name', 'dosage', 'quantity', 'duration')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value.strip()


class Patient(BaseModel):
    model_config = ConfigDict(extra='forbid')
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(pattern=r'^\+[1-9][0-9]{7,14}$')
    language: str = Field(min_length=2, max_length=20)
    region: str = Field(pattern=r'^[A-Z]{2}$')
    consent: bool
    consent_evidence: str = Field(min_length=1, max_length=1000)
    caregiver_name: str | None = None
    caregiver_phone: str | None = Field(default=None, pattern=r'^\+[1-9][0-9]{7,14}$')
    caregiver_language: str | None = None
    caregiver_region: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')


class Intake(BaseModel):
    ocr_reviewed: bool = False
    model_config = ConfigDict(extra='forbid')
    patient_id: str
    source_id: str = Field(min_length=1, max_length=200)
    medications: list[Medication] = Field(min_length=1, max_length=50)


    @field_validator('medications')
    @classmethod
    def distinct_medications(cls, meds):
        names = [' '.join(m.name.split()).casefold() for m in meds]
        if len(names) != len(set(names)):
            raise ValueError('Medication names must be distinct; include the formulation or strength in the name when necessary')
        return meds


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid')
    medications: list[Medication] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=1000)
    version: int = Field(ge=1)


    @field_validator('medications')
    @classmethod
    def distinct_medications(cls, meds):
        names = [' '.join(m.name.split()).casefold() for m in meds]
        if len(names) != len(set(names)):
            raise ValueError('Medication names must be distinct; include the formulation or strength in the name when necessary')
        return meds


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Explicit aware timestamps avoid guessing medication times or PRN dosing.
    due_at: list[datetime] = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    medication_names: list[str] = Field(min_length=1)

    @field_validator('due_at')
    @classmethod
    def aware(cls, values):
        if any(v.tzinfo is None or v.utcoffset() is None for v in values):
            raise ValueError('timestamps must include a timezone')
        return values


class WorkflowError(Exception):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


class Workflow:
    def __init__(self, path, tenant):
        if not tenant:
            raise ValueError('MEDAI_TENANT_ID must be configured')
        self.path, self.tenant = str(path), tenant
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id))')
            conn.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, call_id TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), used INTEGER NOT NULL)')
            conn.execute('INSERT OR IGNORE INTO budget VALUES (1,0)')
            conn.execute('CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, tenant TEXT NOT NULL, kind TEXT NOT NULL, record_id TEXT NOT NULL, digest TEXT NOT NULL)')

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get(self, conn, kind, key):
        row = conn.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
        doc = json.loads(row[0]) if row else None
        if doc and doc.get('tenant_id') != self.tenant:
            raise WorkflowError('Tenant mismatch', 403)
        return doc

    def _put(self, conn, kind, key, doc):
        from medai_readback.security import actor
        self._get(conn, kind, key)  # Reject overwriting a record owned by another tenant.
        conn.execute('INSERT INTO audit(at,actor,tenant,kind,record_id,digest) VALUES (?,?,?,?,?,?)',
                     (now(), actor.get(), self.tenant, kind, key, hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()))
        doc['tenant_id'] = self.tenant
        conn.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',
                     (kind, key, json.dumps(doc)))

    def get(self, kind, key):
        with self.transaction() as conn:
            doc = self._get(conn, kind, key)
            if doc is None:
                raise WorkflowError('Record not found', 404)
            return doc

    def list(self, kind):
        with self.transaction() as conn:
            return [doc for (body,) in conn.execute('SELECT body FROM records WHERE kind=?', (kind,))
                    if (doc := json.loads(body)).get('tenant_id') == self.tenant]

    def _consent(self, conn, patient_id):
        patient = self._get(conn, 'patient', patient_id)
        if not patient or not patient.get('consent') or patient.get('consent_withdrawn_at'):
            raise WorkflowError('Patient consent is absent or withdrawn', 403)
        return patient

    def patient(self, body, actor):
        doc = body.model_dump()
        doc.update(updated_at=now(), consent_withdrawn_at=None if body.consent else now(), actor=actor)
        with self.transaction() as conn:
            self._put(conn, 'patient', body.patient_id, doc)
            if not body.consent:
                for (key, raw) in conn.execute('SELECT id,body FROM records WHERE kind="job"').fetchall():
                    job = json.loads(raw)
                    if job.get('tenant_id') == self.tenant and job['patient_id'] == body.patient_id and job['status'] == 'pending':
                        job['status'] = 'cancelled_consent'
                        self._put(conn, 'job', key, job)
        return doc

    def intake(self, body, locales):
        data = body.model_dump()
        with self.transaction() as conn:
            patient = self._consent(conn, body.patient_id)
            contact = {k: patient[k] for k in ('phone', 'language', 'region', 'name')}
            key = hashlib.sha256(json.dumps([self.tenant, data, contact], sort_keys=True).encode()).hexdigest()[:32]
            existing = self._get(conn, 'confirmation', key)
            if existing:
                return existing
            reason = 'unsupported_language' if patient['language'] not in locales else None
            if len(data['medications']) > 6:
                reason = 'medication_limit'
            doc = dict(data, call_id=key, patient_name=patient['name'], phone_number=patient['phone'],
                       language=patient['language'], region=patient['region'], status='fallback' if reason else 'pending',
                       fallback_reason=reason, version=1, created_at=now(), dispatch_state='not_sent',
                       webhook_token=secrets.token_urlsafe(32))
            self._put(conn, 'confirmation', key, doc)
            return doc

    def reserve_call(self, call_id, limit, allowed_phones):
        with self.transaction() as conn:
            doc = self._get(conn, 'confirmation', call_id)
            if not doc:
                raise WorkflowError('Record not found', 404)
            patient = self._consent(conn, doc['patient_id'])
            if patient['phone'] != doc['phone_number'] or patient['language'] != doc['language'] or patient['region'] != doc['region'] or patient['name'] != doc['patient_name']:
                raise WorkflowError('Patient contact or language changed; create a new intake')
            if doc['status'] != 'pending' or doc['dispatch_state'] != 'not_sent':
                raise WorkflowError('Call already submitted or not eligible; no automatic redial')
            if patient['phone'] not in allowed_phones:
                raise WorkflowError('Phone is not on the explicit live-call allowlist', 403)
            used = conn.execute('SELECT used FROM budget WHERE id=1').fetchone()[0]
            if used >= limit:
                raise WorkflowError('Local call budget exhausted', 403)
            conn.execute('UPDATE budget SET used=used+1 WHERE id=1')
            doc.update(dispatch_state='submitting', dispatch_reserved_at=now())
            self._put(conn, 'confirmation', call_id, doc)
            return doc

    def record_dispatch(self, call_id, result=None):
        with self.transaction() as conn:
            doc = self._get(conn, 'confirmation', call_id)
            if result:
                doc.update(dispatch_state='submitted', provider_id=result['call_sid'])
            else:
                # Timeout may mean the provider accepted the call. Keep the reservation.
                doc.update(dispatch_state='unknown', dispatch_error='Reconcile with provider before retrying')
            self._put(conn, 'confirmation', call_id, doc)
            return doc

    def event(self, token, event_id, payload):
        if not isinstance(payload, dict) or not event_id:
            raise WorkflowError('Event ID and JSON object required', 422)
        data = payload.get('data')
        event = payload.get('type')
        if not isinstance(event, str):
            raise WorkflowError('Event type must be a string', 422)
        if not isinstance(data, dict) or not isinstance(data.get('metadata'), dict):
            raise WorkflowError('Expected CALL-E event envelope with data.metadata', 422)
        metadata = data['metadata']
        key = metadata.get('call_id')
        if not isinstance(key, str):
            raise WorkflowError('Missing correlation ID', 422)
        with self.transaction() as conn:
            doc = self._get(conn, 'confirmation', key)
            if not doc or not secrets.compare_digest(doc['webhook_token'], token):
                raise WorkflowError('Invalid webhook capability', 403)
            if metadata.get('tenant_id') != self.tenant or metadata.get('patient_id') != doc['patient_id']:
                raise WorkflowError('Metadata mismatch', 403)
            if doc['dispatch_state'] == 'not_sent':
                raise WorkflowError('No call submitted')
            if not isinstance(data.get('id'), str) or (doc.get('provider_id') and data['id'] != doc['provider_id']):
                raise WorkflowError('Provider call ID mismatch', 403)
            if event not in {'call.completed', 'call.failed', 'call.result_validation_failed'}:
                return {'status': 'ignored'}
            if conn.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
                return {'status': 'duplicate'}
            if doc['status'] == 'pending':
                structured = data.get('structured_result') if event == 'call.completed' and data.get('status') == 'completed' else {}
                disposition = decide(structured, doc['medications'])
                try:
                    self._consent(conn, doc['patient_id'])
                except WorkflowError:
                    disposition = 'fallback'
                    doc['fallback_reason'] = 'consent_withdrawn'
                doc['status'] = 'confirmed' if disposition == 'scheduled' else disposition
                doc['provider_failure'] = {k: data.get(k) for k in ('failure_code', 'failure_message')}
                doc['provider_attempts'] = [{'failure_code': a.get('failure_code'), 'failure_message': a.get('failure_message'), 'provider_call_id': a.get('provider_call_id')} for r in data.get('recipients', []) if isinstance(r, dict) for a in (r.get('attempts') if isinstance(r.get('attempts'), list) else []) if isinstance(a, dict)] if isinstance(data.get('recipients'), list) else []
                doc.update(structured_result=structured if isinstance(structured, dict) else {}, resolved_at=now())
                if doc['status'] == 'confirmed':
                    doc['approved_medications'] = doc['medications']
                    doc['approval'] = {'source': 'patient_call', 'at': now()}
                self._put(conn, 'confirmation', key, doc)
            conn.execute('INSERT INTO events VALUES (?,?)', (event_id, key))
            return {'status': 'processed', 'disposition': doc['status']}

    def review(self, key, body, actor):
        with self.transaction() as conn:
            doc = self._get(conn, 'confirmation', key)
            if not doc:
                raise WorkflowError('Record not found', 404)
            self._consent(conn, doc['patient_id'])
            if doc['status'] not in {'review', 'fallback'} or doc['version'] != body.version:
                raise WorkflowError('Record changed or is not awaiting staff review')
            doc.update(approved_medications=[m.model_dump() for m in body.medications], status='confirmed',
                       version=doc['version']+1, approval={'source': 'staff', 'actor': actor, 'reason': body.reason, 'at': now()})
            self._put(conn, 'confirmation', key, doc)
            return doc

    def schedule(self, key, body, actor):
        with self.transaction() as conn:
            doc = self._get(conn, 'confirmation', key)
            if not doc:
                raise WorkflowError('Record not found', 404)
            self._consent(conn, doc['patient_id'])
            if doc['status'] not in {'confirmed', 'scheduled'} or doc['version'] != body.version:
                raise WorkflowError('Human approval and current version required')
            if any(value <= datetime.now(timezone.utc) for value in body.due_at):
                raise WorkflowError('Schedule times must be in the future', 422)
            selected=set(body.medication_names)
            available={m['name'] for m in doc['approved_medications']}
            if not selected<=available:
                raise WorkflowError('Unknown medication selected',422)
            for due in body.due_at:
                due_str = due.astimezone(timezone.utc).isoformat()
                for index, med in enumerate(doc['approved_medications']):
                    if med['name'] not in selected:continue
                    job_id = hashlib.sha256(f'{key}:{body.version}:{due_str}:{index}'.encode()).hexdigest()[:32]
                    if not self._get(conn, 'job', job_id):
                        self._put(conn, 'job', job_id, dict(job_id=job_id, call_id=key, patient_id=doc['patient_id'],
                            due_at=due_str, medication=med, status='pending', actor=actor, kind='adherence',
                            webhook_token=secrets.token_urlsafe(32), dispatch_state='not_sent'))
            # The schedule exists durably, but no automatic calls are enabled.
            doc['status'] = 'scheduled'
            self._put(conn, 'confirmation', key, doc)
            return doc

    def budget(self):
        with self.transaction() as conn:
            return conn.execute('SELECT used FROM budget WHERE id=1').fetchone()[0]

    def due_jobs(self):
        return [j for j in self.list('job') if j['status']=='pending' and j['due_at']<=now()]

    def reserve_job(self, key, limit, phones):
        with self.transaction() as conn:
            job=self._get(conn,'job',key)
            if not job or job['status']!='pending' or job['dispatch_state']!='not_sent' or job['due_at']>now():
                raise WorkflowError('Job is not due or has already been submitted')
            patient=self._consent(conn,job['patient_id'])
            phone=patient.get('caregiver_phone') if job['kind']=='escalation' else patient['phone']
            if not phone or phone not in phones:
                raise WorkflowError('Recipient not explicitly allowlisted',403)
            used=conn.execute('SELECT used FROM budget WHERE id=1').fetchone()[0]
            if used>=limit:raise WorkflowError('Local call budget exhausted',403)
            conn.execute('UPDATE budget SET used=used+1 WHERE id=1')
            job.update(dispatch_state='submitting',status='in_progress',phone_number=phone)
            self._put(conn,'job',key,job)
            return job,patient

    def record_job_dispatch(self,key,result=None):
        with self.transaction() as conn:
            job=self._get(conn,'job',key)
            job['dispatch_state']='submitted' if result else 'unknown'
            if result:job['provider_id']=result['call_sid']
            self._put(conn,'job',key,job)
            return job

    def job_event(self,token,event_id,payload):
        if not isinstance(payload, dict) or not isinstance(event_id, str) or not event_id or not isinstance(payload.get('type'), str):
            raise WorkflowError('Valid event ID and type required', 422)
        data=payload.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('metadata'), dict):
            raise WorkflowError('Event data and metadata must be objects', 422)
        metadata=data['metadata']
        key=metadata.get('job_id')
        if not isinstance(key, str) or not isinstance(data.get('id'), str) or not data['id']:
            raise WorkflowError('Job and provider IDs must be nonempty strings', 422)
        with self.transaction() as conn:
            job=self._get(conn,'job',key)
            if not job or not secrets.compare_digest(job['webhook_token'],token):
                raise WorkflowError('Invalid job capability',403)
            if metadata.get('tenant_id')!=self.tenant or metadata.get('patient_id')!=job['patient_id'] or metadata.get('call_id')!=key:
                raise WorkflowError('Job correlation mismatch',403)
            if job['dispatch_state']=='not_sent' or not data.get('id') or (job.get('provider_id') and job['provider_id']!=data['id']):
                raise WorkflowError('Provider ID mismatch',403)
            if conn.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone():return {'status':'duplicate'}
            if payload.get('type') not in {'call.completed','call.failed','call.result_validation_failed'}:return {'status':'ignored'}
            if job['status'] in {'completed','review'}:
                conn.execute('INSERT INTO events VALUES (?,?)',(event_id,key))
                return {'status':'processed','disposition':job['status']}
            structured=data.get('structured_result') if payload['type']=='call.completed' and data.get('status')=='completed' else {}
            structured=structured if isinstance(structured,dict) else {}
            from medai_readback.adherence import ADHERENCE_OUTCOMES, needs_escalation
            outcome=structured.get('outcome') if job['kind']=='adherence' else structured.get('reached_caregiver')
            allowed=ADHERENCE_OUTCOMES if job['kind']=='adherence' else ('yes','no')
            job['provider_failure'] = {k: data.get(k) for k in ('failure_code', 'failure_message')}
            job.update(status='completed' if outcome in allowed else 'review',structured_result=structured,completed_at=now())
            self._put(conn,'job',key,job)
            try:patient=self._consent(conn,job['patient_id'])
            except WorkflowError:patient=None
            if patient and job['kind']=='adherence' and outcome in ADHERENCE_OUTCOMES and needs_escalation(outcome):
                if patient.get('caregiver_phone') and patient.get('caregiver_name'):
                    escalation_id='esc-'+key
                    if not self._get(conn,'job',escalation_id):
                        self._put(conn,'job',escalation_id,dict(job_id=escalation_id,call_id=job['call_id'],patient_id=job['patient_id'],
                            due_at=now(),medication=job['medication'],kind='escalation',status='pending',dispatch_state='not_sent',
                            patient_outcome=outcome,patient_reason=structured.get('reason') or '',webhook_token=secrets.token_urlsafe(32)))
            conn.execute('INSERT INTO events VALUES (?,?)',(event_id,key))
            return {'status':'processed','disposition':job['status']}
