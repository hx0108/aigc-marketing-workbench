"""Creation admission: immutable request, idempotency and server-owned readiness."""
import hashlib,uuid
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from .db import Record
from .execution import Budget,Task

def submit(session,workspace,request_id,key,authorized):
    if not key or len(key)>200:raise HTTPException(422,detail={'code':'IDEMPOTENCY_KEY_REQUIRED'})
    request=session.scalar(select(Record).where(Record.id==request_id,Record.workspace==workspace,Record.kind=='creation_request').with_for_update())
    if not request or request.data.get('deleting'):raise HTTPException(404)
    identity=str(uuid.uuid5(uuid.NAMESPACE_URL,workspace+':'+key))
    existing=session.get(Task,identity)
    if existing:
        if existing.payload.get('request_id')!=request_id:raise HTTPException(409,detail={'code':'IDEMPOTENCY_CONFLICT'})
        return {'task_id':identity,'work_id':existing.payload['work_id'],'execution_state':existing.state}
    profile=session.get(Record,request.data['profile_id'])
    if not profile or profile.workspace!=workspace or profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    if not authorized:raise HTTPException(409,detail={'code':'CONSENT_REQUIRED'})
    if request.data.get('status')!='ready' or request.data.get('blockers'):
        raise HTTPException(409,detail={'code':'PREFLIGHT_BLOCKED','blockers':request.data.get('blockers',[])})
    try:
        from marketing_worker.business import readiness
        blockers=readiness()
    except (ImportError,AttributeError):blockers=['PROVIDER_NOT_CONFIGURED']
    if blockers:raise HTTPException(409,detail={'code':'PROVIDER_NOT_CONFIGURED','blockers':blockers})
    snapshot=request.data['profile_snapshot']
    if set(snapshot.get('source_selection',{}))!={'product','mask'}:raise HTTPException(422,detail={'code':'SOURCE_SELECTION_REQUIRED'})
    sources=[session.get(Record,id) for id in snapshot.get('source_ids',[])]
    if not any(s and s.workspace==workspace and s.data.get('type')=='image' and not s.data.get('deleting') for s in sources):raise HTTPException(422,detail={'code':'PRODUCT_IMAGE_REQUIRED'})
    work_id=str(uuid.uuid4())
    data={**request.data,'facts':[{'id':str(k),'value':v,'validity':'active'} for k,v in snapshot['facts'].items()],'source_ids':snapshot.get('source_ids',[])}
    from marketing_worker.business import authorization_snapshot
    try:consent=authorization_snapshot(workspace,request_id)
    except ValueError:raise HTTPException(409,detail={'code':'CONSENT_SCOPE_MISMATCH'}) from None
    quote=request.data.get('quote')
    if not quote or any(quote.get(key)!=consent.get(key) for key in ('providers','provider_parameters','price_version','budget_id','consent_version','bounds')):
        raise HTTPException(409,detail={'code':'AUTHORIZATION_SCOPE_CHANGED'})
    budget=session.scalar(select(Budget).where(Budget.id==consent['budget_id'],Budget.workspace==workspace).with_for_update())
    hold=session.get(Record,'budget-hold:'+consent['budget_id'])
    if hold and hold.workspace==workspace and hold.kind=='budget_hold' and hold.data.get('active'):
        raise HTTPException(409,detail={'code':'BUDGET_HELD_FOR_REVIEW'})
    if not budget or budget.cap-budget.reserved-budget.settled<Decimal(quote['cost_upper_bound']):
        raise HTTPException(409,detail={'code':'CREATION_QUOTE_CHANGED'})
    consent['cost_upper_bound']=quote['cost_upper_bound']
    consent_id=str(uuid.uuid4())
    session.add(Record(id=consent_id,workspace=workspace,kind='processing_consent',data={'request_id':request_id,'request_revision':request.revision,'profile_id':data['profile_id'],'source_ids':data['source_ids'],'platforms':data['platforms'],'duration_seconds':data['duration_seconds'],**consent}))
    data['consent_id']=consent_id
    session.add(Record(id=work_id,workspace=workspace,kind='work',data={'sku_id':data['sku_id'],'profile_id':data['profile_id'],'creation_request_id':request_id,'platforms':data['platforms'],'duration_seconds':data['duration_seconds'],'status':'queued','current_result':None}))
    session.add(Task(id=identity,workspace=workspace,state='queued',phase='creation_run',payload={'work_id':work_id,'profile_id':data['profile_id'],'request_id':request_id,'request':data}))
    session.commit()
    return {'task_id':identity,'work_id':work_id,'execution_state':'queued'}
