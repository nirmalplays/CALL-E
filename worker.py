"""Process due local jobs. Default is preview-only, never dialing.

python worker.py --once          # list due jobs, zero API calls
python worker.py --once --live   # explicitly dispatch due jobs within budget
python worker.py --live          # run worker; live settings still required
"""
import argparse
import asyncio
import json
import os
import env_config
from medai_readback.local_api import workflow, dispatch_job
from medai_readback.calle import CalleService
from medai_readback.workflow import WorkflowError

def heartbeat(live):
    # The dashboard has no other way to know this process exists.
    from datetime import datetime, timezone
    workflow().set_state('worker_heartbeat', json.dumps({
        'at': datetime.now(timezone.utc).isoformat(),
        'mode': 'live' if live else 'dry-run', 'pid': os.getpid()}))


async def run(once=False,live=False):
    try:
        while True:
            jobs=workflow().due_jobs()
            heartbeat(live)
            print(json.dumps({'due_jobs':[j['job_id'] for j in jobs],'mode':'live' if live else 'dry-run'}),flush=True)
            if live:
                for job in jobs:
                    try:await dispatch_job(job['job_id'])
                    except WorkflowError as exc:
                        print(f'Job blocked: {exc}',flush=True)
                        # Do not hammer a failed provider or exhausted budget.
                        break
            if once or not live:return
            await asyncio.sleep(30)
    finally:
        await CalleService.shutdown()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    asyncio.run(run(args.once,args.live))
