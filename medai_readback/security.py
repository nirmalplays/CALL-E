"""Request limits and browser protections shared by local and deployed apps."""
import asyncio
from contextvars import ContextVar
from starlette.responses import JSONResponse

actor = ContextVar('audit_actor', default='system')


class RequestProtection:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = 10 * 1024 * 1024 if scope['path'] == '/local/ocr/extract' else 1_000_000
        chunks, size = [], 0
        try:
            async with asyncio.timeout(30):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    size += len(message.get('body', b''))
                    if size > limit:
                        return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
                    chunks.append(message.get('body', b''))
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            return await JSONResponse({'detail': 'Request upload timed out'}, status_code=408)(scope, receive, send)
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers += [(b'x-content-type-options', b'nosniff'),
                            (b'x-frame-options', b'DENY'),
                            (b'referrer-policy', b'no-referrer'),
                            (b'cache-control', b'no-store'),
                            (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
                message = dict(message, headers=headers)
            await send(message)
        await self.app(scope, bounded_receive, protected_send)
