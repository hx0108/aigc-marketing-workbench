"""Send redacted operational events to stderr as one JSON object per line."""
from hashlib import sha256
import json
import sys
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.datastructures import MutableHeaders


_output_lock = Lock()
_export_routes = {'/api/v1/export-packages','/api/v1/exports/{id}/download'}
_worker_codes = {'canceled','paused','external_unknown','provider_rejected','voice_duration_mismatch'}


def emit(event, **fields):
    line = json.dumps({'event':event,**fields},ensure_ascii=True,separators=(',',':'))
    with _output_lock:
        sys.stderr.write(line+'\n')
        sys.stderr.flush()


def task_event(task_id, state, *, code=None, error=None):
    fields = {'task_ref':sha256(str(task_id).encode()).hexdigest(), 'state':state}
    if code is not None:
        fields['error_code'] = code if isinstance(code,str) and code in _worker_codes else 'task_failed'
    if error is not None:
        fields['error_type'] = type(error).__name__
    emit('worker_task_state',**fields)


class HttpEvents:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        request_id = str(uuid4())
        scope.setdefault('state',{})['request_id'] = request_id
        started = perf_counter()
        status = None
        error_type = None

        async def correlate(message):
            nonlocal status
            if message['type']=='http.response.start':
                status=message['status']
                MutableHeaders(scope=message)['X-Request-ID']=request_id
            await send(message)

        try:
            await self.app(scope,receive,correlate)
        except Exception as error:
            error_type=type(error).__name__
            if status is not None:
                # The response has started, so abort rather than logging the original exception.
                raise RuntimeError('http_response_interrupted') from None
            await JSONResponse({'code':'INTERNAL_ERROR','message':'请求处理失败','request_id':request_id,
                'retryable':False,'detail':'INTERNAL_ERROR'},status_code=500)(scope,receive,correlate)
        finally:
            route=scope.get('route')
            template=route.path if isinstance(route,APIRoute) else None
            category='request_completed'
            if status in (401,403):
                category='access_rejected'
            elif template in _export_routes and (error_type or (status is not None and status>=400)):
                category='export_failed'
            elif error_type or (status is not None and status>=500):
                category='request_failed'
            elif status==404:
                category='not_found'
            elif status is not None and status>=400:
                category='request_rejected'
            fields={'request_id':request_id,'route':template,'status':status,
                'duration_ms':round((perf_counter()-started)*1000,2)}
            if error_type:fields['error_type']=error_type
            if template in _export_routes:fields['operation']='export'
            emit(category,**fields)
