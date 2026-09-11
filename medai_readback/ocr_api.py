"""Authenticated, bounded local OCR uploads. No automatic clinical parsing."""
import base64
import asyncio
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from ocr.draft import medication_drafts
from medai_readback.workflow import now
from starlette.concurrency import run_in_threadpool
from medai_readback.local_api import staff, workflow
from ocr.extract import extract, MAX_BYTES

router = APIRouter(prefix='/local/ocr', dependencies=[Depends(staff)])
_busy = asyncio.Lock()


@router.post('/extract')
async def upload(request: Request):
    if _busy.locked():
        raise HTTPException(429, 'OCR is busy. Wait for the current extraction to finish.')
    async with _busy:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, 'Maximum upload size is 10 MB.')
            data.extend(chunk)
        try:
            result = await run_in_threadpool(extract, bytes(data))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        result['draft_medications'] = medication_drafts(result['pages'])
        result['created_at'] = now()
        result['scan_id'] = 'ocr-' + secrets.token_hex(12)
        result['sha256'] = hashlib.sha256(data).hexdigest()
        service = workflow()
        with service.transaction() as conn:
            service._put(conn, 'ocr', result['scan_id'], result)
            service._put(conn, 'ocr_source', result['scan_id'], {'data': base64.b64encode(data).decode('ascii')})
        return result


@router.get('')
def scans():
    return [{'scan_id': d['scan_id'], 'created_at': d.get('created_at'), 'pages': len(d['pages'])} for d in workflow().list('ocr')]


@router.get('/{scan_id}/source')
def source(scan_id: str):
    doc = workflow().get('ocr_source', scan_id)
    return Response(base64.b64decode(doc['data']), media_type='application/octet-stream',
                    headers={'Content-Disposition': 'attachment; filename=prescription-source'})


@router.get('/{scan_id}')
def saved(scan_id: str):
    return workflow().get('ocr', scan_id)
