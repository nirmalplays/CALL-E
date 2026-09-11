import subprocess
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from medai_readback.workflow import Intake, Review, WorkflowError, Medication
from medai_readback.readback import format_medication_line, build_readback_task
from tests.test_workflow import flow, sent, payload, MED


def test_liquid_quantity_is_not_changed_to_tablets():
    line = format_medication_line(1, dict(MED, quantity='5 ml'))
    assert '5 ml' in line and 'tablet' not in line
    assert 'reminders now' not in build_readback_task('Test', [MED])


@pytest.mark.parametrize('kind',[Intake,Review])
def test_duplicate_names_rejected_before_name_based_scheduling(kind):
    values = {'patient_id':'p','source_id':'s'} if kind is Intake else {'reason':'verified','version':1}
    with pytest.raises(ValidationError):
        kind(medications=[MED,dict(MED,name='  medicine   a ',dosage='20mg')],**values)


def test_blank_timing_rejected():
    with pytest.raises(ValidationError):
        Medication(**dict(MED,schedule=[' ']))


def test_malformed_callback_types_fail_with_validation(flow):
    d=sent(flow)
    p=payload(d);p['type']=[]
    with pytest.raises(WorkflowError) as exc: flow.event(d['webhook_token'],'evt-bad',p)
    assert exc.value.status==422
    for data in [None,{'metadata':[]},{'metadata':{'job_id':{}},'id':'call_x'}]:
        with pytest.raises(WorkflowError) as exc: flow.job_event('token','evt',{'type':'call.failed','data':data})
        assert exc.value.status==422


@pytest.mark.parametrize('script',['test_readback_api.py','test_readback_call.py'])
def test_legacy_examples_default_to_offline(script):
    root=Path(__file__).resolve().parents[1]
    # Fail immediately if any code path attempts network access, even with a key.
    code="import sys,runpy; sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError('network forbidden')) if e.startswith('socket.') else None); runpy.run_path(sys.argv[1],run_name='__main__')"
    # run_path script sees no application arguments.
    code=code.replace("runpy.run_path(sys.argv[1],run_name='__main__')", "p=sys.argv.pop(); runpy.run_path(p,run_name='__main__')")
    result=subprocess.run([sys.executable,'-B','-c',code,str(root/script)],capture_output=True,text=True,timeout=20,cwd=root)
    assert result.returncode==0,result.stderr
    assert 'OFFLINE FIXTURE PREVIEW' in result.stdout
