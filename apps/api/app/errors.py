"""Consistent safe API errors with request correlation, retaining detail compatibility."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .operational_events import HttpEvents

def install(app):
    app.add_middleware(HttpEvents)
    @app.exception_handler(HTTPException)
    async def http_error(request,error):
        details=error.detail if isinstance(error.detail,dict) else {'message':str(error.detail)}
        code=details.get('code','HTTP_'+str(error.status_code))
        return JSONResponse(status_code=error.status_code,headers=error.headers,content={'code':code,'message':details.get('message',code),'request_id':getattr(request.state,'request_id',None),'retryable':error.status_code in {429,503},'detail':error.detail})
    @app.exception_handler(RequestValidationError)
    async def validation(request,error):
        fields=[{'loc':item['loc'],'type':item['type'],'message':item['msg']} for item in error.errors()]
        return JSONResponse(status_code=422,content={'code':'VALIDATION_ERROR','message':'请求字段无效','request_id':getattr(request.state,'request_id',None),'retryable':False,'detail':fields})
