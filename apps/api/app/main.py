from fastapi import FastAPI, Header, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from sqlalchemy import select, func
from .db import Session, Record, initialize
import os
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app):
    config_path=os.environ.get('AIGC_PIPELINE_CONFIG')
    if config_path:
        from marketing_worker.configuration import load_configuration
        load_configuration(config_path,Session)
    yield
app = FastAPI(title='AIGC 营销工作台', version='0.4.0',lifespan=lifespan)
from .errors import install
install(app)

def identity(authorization: str = Header(default='')):
    token=os.environ.get('AIGC_DEV_TOKEN')
    if not token or authorization != 'Bearer '+token:
        raise HTTPException(401, detail={'code':'AUTH_REQUIRED','message':'请登录'})
    return 'development'
def db():
    with Session() as s:
        yield s

def get(s, id, workspace, kind=None):
    r=s.get(Record,id)
    if not r or r.workspace!=workspace or (kind and r.kind!=kind): raise HTTPException(404,'不存在')
    if r.data.get('deleting'):raise HTTPException(404,'不存在')
    return r

def output(r):
    from .pagination import timestamp
    data={**r.data,'id':r.id,'revision':r.revision,'created_at':timestamp(r.created_at),'created_at_known':r.created_at is not None}
    if r.kind=='asset':
        if data.get('repair_task_id'):
            data['repair_render_available']=bool(data.get('repair_render_key') and data.get('repair_render_sha256'))
        for field in ('label_verification','repair_render_key','repair_render_sha256'):
            data.pop(field,None)
    return data
def create(s,w,kind,data):
    r=Record(workspace=w,kind=kind,data=data);s.add(r);s.commit();return output(r)
class SKU(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=200)
    model:str=Field(default='',max_length=200)
    color:str=''
    merchant_sku:str=Field(default='',max_length=200)
    specification:str=Field(default='',max_length=500)
    product_model:str=Field(default='',max_length=200)
    single_spec_confirmed:bool=Field(default=False,strict=True)
class Profile(BaseModel):
    facts:dict
    source_ids:list[str]=[]
    candidate_ids:list[str]=[]
class Creation(BaseModel):
    profile_id:str
    platforms:list[str]=Field(min_length=1,max_length=2)
    duration_seconds:int=Field(gt=0,strict=True)
    brief:str=''
    budget_limit:Decimal|None=Field(default=None,gt=0,max_digits=12,decimal_places=8,allow_inf_nan=False)
@app.get('/health')
def health():
    try:
        from marketing_worker.business import readiness
        enabled=not readiness()
    except ImportError:
        enabled=False
    return {'status':'ok','real_generation_enabled':enabled}
@app.get('/ready')
def ready(request:Request,s=Depends(db)):
    from .readiness import is_ready
    from .sources import ROOT
    from .worker_heartbeat import fresh
    available=is_ready(s,ROOT,getattr(request.app.state,'readiness_static_root',None))
    instance=getattr(request.app.state,'readiness_worker_instance',None)
    worker='unknown'
    if instance:
        current=fresh(ROOT,instance)
        worker='heartbeat_fresh' if current else 'heartbeat_missing_or_stale'
        available=available and current
    return JSONResponse({'status':'ready' if available else 'unavailable','worker':worker},
        status_code=200 if available else 503,headers={'Cache-Control':'no-store'})

@app.get('/api/v1/{collection}')
def listing(collection:str, limit:int=20, offset:int=0,order:str='id_asc',cursor:str|None=None,w=Depends(identity),s=Depends(db)):
    kinds={'skus':'sku','works':'work','tasks':'task'}
    if collection not in kinds:raise HTTPException(404)
    if not 1<=limit<=100 or offset<0:raise HTTPException(422)
    from .pagination import page
    if collection=='tasks':
        from .execution import Task
        tasks,next_cursor=page(s,select(Task).where(Task.workspace==w),Task,w,collection,order,limit,offset,cursor)
        from .task_views import task_view
        return {'items':[task_view(s,t) for t in tasks],'limit':limit,'offset':offset,'order':order,'next_cursor':next_cursor}
    rows,next_cursor=page(s,select(Record).where(Record.workspace==w,Record.kind==kinds[collection],func.coalesce(Record.data['deleting'].as_boolean(),False)==False),Record,w,collection,order,limit,offset,cursor)
    return {'items':[output(r) for r in rows], 'limit':limit,'offset':offset,'order':order,'next_cursor':next_cursor}
@app.post('/api/v1/skus',status_code=201)
def sku(body:SKU,w=Depends(identity),s=Depends(db)):
    data=body.model_dump()
    if body.model and body.merchant_sku and body.model!=body.merchant_sku:raise HTTPException(422,'商品编号字段不一致')
    if body.color and body.specification and body.color!=body.specification:raise HTTPException(422,'规格字段不一致')
    data['merchant_sku']=(body.merchant_sku or body.model).strip()
    data['specification']=(body.specification or body.color).strip()
    data['model']=data['merchant_sku'];data['color']=data['specification']
    from sqlalchemy.exc import IntegrityError
    try:return create(s,w,'sku',data)
    except IntegrityError:
        s.rollback();raise HTTPException(409,detail={'code':'SKU_ALREADY_EXISTS','message':'商品编号已存在'}) from None
@app.post('/api/v1/skus/{id}/profiles',status_code=201)
def profile(id:str,body:Profile,w=Depends(identity),s=Depends(db)):
    sku=get(s,id,w,'sku')
    for source_id in body.source_ids:
        source=get(s,source_id,w,'source')
        if source.data['sku_id']!=id:raise HTTPException(422,'素材不属于当前商品')
    facts=dict(body.facts);locators={};source_ids=list(body.source_ids)
    for candidate_id in body.candidate_ids:
        candidate=get(s,candidate_id,w,'fact_candidate')
        if candidate.data['sku_id']!=id:raise HTTPException(422,'事实不属于当前商品')
        source=get(s,candidate.data['source_id'],w,'source')
        if source.data['sku_id']!=id:raise HTTPException(422,'来源不属于当前商品')
        if source.id not in source_ids:source_ids.append(source.id)
        key,value=candidate.data['key'],candidate.data['value']
        if key in facts and facts[key]!=value:raise HTTPException(422,detail={'code':'FACT_CONFLICT','field':key})
        facts[key]=value;locators[key]=candidate.data['locator']
    for key,value in {'name':sku.data.get('name'),'merchant_sku':sku.data.get('merchant_sku') or sku.data.get('model'),'specification':sku.data.get('specification') or sku.data.get('color'),'product_model':sku.data.get('product_model')}.items():
        if value and key not in facts:
            facts[key]=value;locators[key]={'origin':'catalog','sku_id':id,'sku_revision':sku.revision}
    for key in facts:
        if key not in locators:locators[key]={'origin':'manual','confirmed_by':w}
    selection={}
    if sku.data.get('source_selection_id'):
        selection=get(s,sku.data['source_selection_id'],w,'source_selection').data['sources']
        for item in selection.values():
            if item['source_id'] not in source_ids:source_ids.append(item['source_id'])
    return create(s,w,'profile',{'sku_id':id,**body.model_dump(),'source_ids':source_ids,'source_selection':selection,'facts':facts,'fact_sources':locators,'status':'draft'})
@app.post('/api/v1/profiles/{id}/confirm')
def confirm(id:str,w=Depends(identity),s=Depends(db)):
    r=get(s,id,w,'profile')
    if r.data['status']=='revoked':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    from .profile_validation import validate_profile
    from datetime import datetime,timezone
    sku=s.scalar(select(Record).where(Record.id==r.data['sku_id'],Record.workspace==w,Record.kind=='sku').with_for_update())
    if not sku or sku.data.get('deleting'):raise HTTPException(404)
    validate_profile(s,w,r)
    if r.data['status']!='confirmed':
        now=datetime.now(timezone.utc).isoformat()
        sources={key:{**locator,'confirmed_by':w,'confirmed_at':now} for key,locator in r.data['fact_sources'].items()}
        r.data={**r.data,'status':'confirmed','confirmed_by':w,'confirmed_at':now,'fact_sources':sources}
    if sku.data.get('current_profile_id')!=r.id:
        sku.data={**sku.data,'current_profile_id':r.id};sku.revision+=1
    s.commit();return {**output(r),'sku_revision':sku.revision}
@app.post('/api/v1/creation-requests',status_code=201)
def creation(body:Creation,w=Depends(identity),s=Depends(db)):
    p=get(s,body.profile_id,w,'profile')
    if p.data['status']!='confirmed':raise HTTPException(422,detail={'code':'PROFILE_NOT_CONFIRMED'})
    from .profile_validation import validate_profile
    validate_profile(s,w,p)
    if len(set(body.platforms))!=len(body.platforms) or not set(body.platforms)<={'douyin','xiaohongshu'}:raise HTTPException(422,detail={'code':'INVALID_PLATFORM'})
    import uuid
    request_id=str(uuid.uuid4())
    blockers=[{'code':'PROVIDER_NOT_CONFIGURED','message':'尚未配置生成服务和价格，无法授权执行'}]
    quote=None
    try:
        from marketing_worker.business import readiness,authorization_snapshot
        from .execution import Budget
        from .pricing import creation_reservation_floor
        pipeline_blockers=readiness()
        if not pipeline_blockers:
            configuration=authorization_snapshot(w,request_id)
            budget=s.get(Budget,configuration['budget_id'])
            if budget and budget.workspace==w:
                available=budget.cap-budget.reserved-budget.settled
                if body.budget_limit is not None:available=min(available,body.budget_limit)
                hold=s.get(Record,'budget-hold:'+budget.id)
                if hold and hold.workspace==w and hold.kind=='budget_hold' and hold.data.get('active'):
                    blockers=[{'code':'BUDGET_HELD_FOR_REVIEW','message':'供应商账单超过费用上界，需管理员复评后再执行'}]
                else:
                    minimum=creation_reservation_floor(configuration,body.duration_seconds,len(body.platforms))
                    if available<minimum:
                        blockers=[{'code':'BUDGET_INSUFFICIENT','message':f'可用预算低于完整创作的最低预留 ¥{minimum.normalize():f}'}]
                    else:
                        quote={**configuration,'cost_upper_bound':str(available),'minimum_reservation':str(minimum),'bound_basis':'available_authorized_budget','complete_output_guaranteed':False}
                        blockers=[]
            else:
                blockers=[{'code':'WORKSPACE_BUDGET_REQUIRED','message':'当前账号尚未分配创作预算，请联系管理员开通'}]
        elif any('PRICE' in code for code in pipeline_blockers):
            blockers=[{'code':'PRICE_CONFIGURATION_REQUIRED','message':'服务价格尚未核验，暂时无法报价，请联系管理员处理'}]
    except ValueError as exc:
        if str(exc)=='pipeline_not_authorized':
            blockers=[{'code':'WORKSPACE_AUTHORIZATION_REQUIRED','message':'当前账号尚未开通生成权限，请联系管理员开通'}]
        else:
            blockers=[{'code':'PRICE_CONFIGURATION_INVALID','message':'当前时长或价格配置无法报价，请联系管理员处理'}]
    except (ImportError,KeyError):
        blockers=[{'code':'PIPELINE_CONFIGURATION_INCOMPLETE','message':'生成配置不完整，请联系管理员处理'}]
    if set(p.data.get('source_selection',{}))!={'product','mask'}:
        blockers.append({'code':'SOURCE_SELECTION_REQUIRED','message':'请选择并复核商品原图与同尺寸遮罩，然后建立新的档案版本'})
    record=Record(id=request_id,workspace=w,kind='creation_request',data={**body.model_dump(mode='json'),'sku_id':p.data['sku_id'],'profile_snapshot':p.data,'status':'ready' if not blockers else 'blocked','blockers':blockers,'quote':quote})
    s.add(record);s.commit();return output(record)
class RunConsent(BaseModel):
    authorized:bool=False
@app.post('/api/v1/creation-requests/{id}/runs',status_code=202)
def run(id:str,body:RunConsent,idempotency_key:str=Header(default=''),w=Depends(identity),s=Depends(db)):
    from .admission import submit
    return submit(s,w,id,idempotency_key,body.authorized)
@app.get('/api/v1/{collection}/{id}')
def detail(collection:str,id:str,include_activity:bool=False,w=Depends(identity),s=Depends(db)):
    if collection=='tasks':
        from .execution import Task
        task=s.get(Task,id)
        if not task or task.workspace!=w:raise HTTPException(404)
        from .task_views import task_view
        return task_view(s,task)
    kind={'skus':'sku','profiles':'profile','creation-requests':'creation_request','tasks':'task','works':'work'}.get(collection)
    if not kind:raise HTTPException(404)
    if collection=='sessions' and id=='current':
        raise HTTPException(404)
    activity=None
    if kind=='work' and include_activity:
        from .execution import Task
        related=select(Task).where(
            Task.workspace==w,
            Task.payload['work_id'].as_string()==id,
        )
        active=s.scalar(related.where(Task.state.in_(['queued','running'])).limit(1)) is not None
        creation=s.scalar(related.where(Task.phase=='creation_run').order_by(Task.created_at.desc().nullslast(),Task.id).limit(1))
        activity={'has_active_tasks':active}
        if creation:
            from .task_views import creation_progress, task_view
            view=task_view(s,creation)
            activity['creation_task']={**view,'progress_stage':creation_progress(s,creation,view)}
    record=get(s,id,w,kind)
    result=output(record)
    if activity is not None:
        result.update(activity)
        repairs=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='asset',
            Record.data['work_id'].as_string()==id,Record.data['repair_task_id'].as_string().is_not(None),
            func.coalesce(Record.data['deleting'].as_boolean(),False)==False,
        ).order_by(Record.created_at.desc().nullslast(),Record.id).limit(20)).all()
        result['repair_candidates']=[output(asset) for asset in repairs]
    if kind=='work' and record.data.get('current_result'):
        revision=get(s,record.data['current_result'],w,'result_revision')
        result['result']=output(revision)
        result['assets']=[output(get(s,asset_id,w,'asset')) for asset_id in revision.data.get('assets',[])]
    return result

from .auth import authenticate, login, register, LoginSession
from fastapi import Response
import hashlib
app.dependency_overrides[identity]=authenticate
class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=200)
    password:str=Field(min_length=1,max_length=1024)
class Registration(Credentials):
    model_config=ConfigDict(extra='forbid')
    password:str=Field(min_length=12,max_length=1024)
@app.post('/api/v1/accounts',status_code=201)
def sign_up(body:Registration,request:Request,response:Response):
    return register(body.username,body.password,request,response)
@app.post('/api/v1/sessions')
def sign_in(body:Credentials,request:Request,response:Response):
    return login(body.username,body.password,request,response)
@app.delete('/api/v1/sessions/current',status_code=204)
def sign_out(request:Request,response:Response,w=Depends(identity),s=Depends(db)):
    r=s.get(LoginSession,hashlib.sha256(request.cookies['aigc_session'].encode()).hexdigest())
    if r:s.delete(r);s.commit()
    response.delete_cookie('aigc_session')

@app.get('/api/v1/skus/{id}/profiles')
def profiles(id:str,w=Depends(identity),s=Depends(db)):
    sku=get(s,id,w,'sku')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='profile',Record.data['sku_id'].as_string()==id).order_by(Record.created_at.asc().nullslast(),Record.id)).all()
    current=next((r.id for r in rows if r.id==sku.data.get('current_profile_id') and r.data.get('status')=='confirmed'),None)
    return {'items':[output(r) for r in rows],'current_profile_id':current,'selection_required':current is None and any(r.data.get('status')=='confirmed' for r in rows)}

@app.get('/api/v1/sessions/current')
def current_session(request:Request,w=Depends(identity),s=Depends(db)):
    r=s.get(LoginSession,hashlib.sha256(request.cookies['aigc_session'].encode()).hexdigest())
    return {'csrf_token':r.csrf}

@app.post('/api/v1/skus/{id}/sources',status_code=201)
async def upload_source(id:str,request:Request,w=Depends(identity),s=Depends(db)):
    from .sources import receive_upload,ROOT
    from urllib.parse import unquote
    get(s,id,w,'sku')
    if request.headers.get('X-Rights-Confirmed')!='true':raise HTTPException(422,'请确认素材权利')
    name=unquote(request.headers.get('X-Filename',''))
    if not name or len(name)>255:raise HTTPException(422,'文件名无效')
    from .uploads import SOURCE_COUNTS,reserve_upload,release_upload
    try:declared_size=int(request.headers.get('Content-Length','0'))
    except ValueError:raise HTTPException(422,'文件长度无效')
    reservation=reserve_upload(s,w,id,name,declared_size)
    try:
        key,digest,size,kind=await receive_upload(request,name,declared_size)
        if size!=declared_size:
            (ROOT/key).unlink(missing_ok=True)
            raise HTTPException(422,'上传长度不匹配')
    except BaseException:
        release_upload(s,reservation)
        raise
    # Lock the SKU before aggregate quota calculation and insertion.
    locked_sku=s.scalar(select(Record).where(Record.id==id).with_for_update().execution_options(populate_existing=True))
    import time
    if locked_sku.data.get('deleting') or reservation.data['expires']<=time.time():
        (ROOT/key).unlink(missing_ok=True)
        release_upload(s,reservation)
        raise HTTPException(409,'上传已过期或商品已删除')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='source')).all()
    same=[r for r in rows if r.data['sku_id']==id and not r.data.get('deleting')]
    if sum(r.data['size'] for r in same)+size>1024**3 or sum(r.data['type']==kind for r in same)>=SOURCE_COUNTS[kind]:
        (ROOT/key).unlink(missing_ok=True)
        release_upload(s,reservation)
        raise HTTPException(413,'商品素材配额不足')
    try:
        s.delete(reservation)
        return create(s,w,'source',{'sku_id':id,'name':name,'size':size,'type':kind,'object_key':key,'sha256':digest,'rights_confirmed':True,'parse_status':'pending'})
    except BaseException:
        s.rollback()
        (ROOT/key).unlink(missing_ok=True)
        raise
@app.get('/api/v1/skus/{id}/sources')
def sources(id:str,w=Depends(identity),s=Depends(db)):
    get(s,id,w,'sku')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='source')).all()
    return {'items':[output(r) for r in rows if r.data['sku_id']==id]}
@app.get('/api/v1/sources/{id}/download')
def source_download(id:str,inline:bool=False,w=Depends(identity),s=Depends(db)):
    from .sources import ROOT
    from fastapi.responses import FileResponse
    r=get(s,id,w,'source')
    get(s,r.data['sku_id'],w,'sku')
    path=(ROOT/r.data['object_key']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():raise HTTPException(404)
    is_image=inline and r.data.get('type')=='image'
    return FileResponse(path,filename=r.data['name'],content_disposition_type='inline' if is_image else 'attachment',
                        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


# Specific resource routes must precede the generic collection detail route.
app.router.routes.sort(key=lambda route: 1 if getattr(route,'path','')=='/api/v1/{collection}/{id}' else 0)

class DraftPatch(BaseModel):
    expected_revision:int
    changes:dict
    discard:bool=False
@app.patch('/api/v1/works/{id}/draft')
def edit_work(id:str,body:DraftPatch,w=Depends(identity),s=Depends(db)):
    work=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='work').with_for_update())
    if not work:raise HTTPException(404)
    if work.revision!=body.expected_revision:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    previous=work.data.get('draft',{})
    if body.discard:
        if body.changes:raise HTTPException(422,detail={'code':'DISCARD_WITH_CHANGES'})
        if previous:
            work.data={**work.data,'draft':{},'draft_history':work.data.get('draft_history',[])+[previous]}
            work.revision+=1;s.commit()
        return output(work)
    if previous.get('restore_revision_id'):
        raise HTTPException(409,detail={'code':'RESTORE_DRAFT_PENDING','message':'请先应用或撤销历史恢复草稿'})
    allowed={'platform','title','body','narration','voice','music','subtitle_style','poster_title','poster_points','poster_layout','asset_id','shots'}
    if not set(body.changes)<=allowed:raise HTTPException(422,'未知编辑字段')
    if 'poster_layout' in body.changes and body.changes['poster_layout'] not in ('classic','product_top'):
        raise HTTPException(422,detail={'code':'POSTER_LAYOUT_INVALID'})
    if 'poster_points' in body.changes:
        points=body.changes['poster_points']
        if not isinstance(points,list) or len(points)>8 or any(not isinstance(point,str) or not 0<len(point.strip())<=200 for point in points):
            raise HTTPException(422,detail={'code':'POSTER_POINTS_INVALID'})
    platform=body.changes.get('platform')
    if platform and platform not in work.data.get('platforms',[]):raise HTTPException(422,'未选择该平台')
    if len(work.data.get('platforms',[]))>1 and not platform:raise HTTPException(422,'请指定修改平台')
    if previous and previous.get('platform') and platform and previous['platform']!=platform:raise HTTPException(409,detail={'code':'PENDING_PLATFORM_DRAFT','message':'请先应用或恢复当前平台草稿'})
    history=work.data.get('draft_history',[])+[work.data.get('draft',{})]
    draft={**work.data.get('draft',{}),**body.changes}
    from .shot_edits import merge_shots,plan
    if 'shots' in body.changes:draft['shots']=merge_shots(previous.get('shots',[]),body.changes['shots'])
    plan(s,work,draft)
    work.data={**work.data,'draft':draft,'draft_history':history};work.revision+=1;s.commit()
    return output(work)
@app.post('/api/v1/works/{id}/change-quotes')
def changes(id:str,w=Depends(identity),s=Depends(db)):
    from .change_quotes import calculate_quote, quote_scope
    import uuid
    work = get(s,id,w,'work')
    quote, authorization = calculate_quote(s,w,work)
    if authorization is None:
        return quote
    quote_id = str(uuid.uuid4())
    s.add(Record(id=quote_id,workspace=w,kind='change_quote',data=quote_scope(work,quote,authorization)))
    s.commit()
    return {**quote,'quote_id':quote_id}

@app.post('/api/v1/sources/{id}/parse')
def parse_source(id:str,w=Depends(identity),s=Depends(db)):
    from .sources import ROOT
    source=get(s,id,w,'source')
    sku_id=source.data['sku_id']
    get(s,sku_id,w,'sku')
    snapshot={field:source.data.get(field) for field in ('sku_id','object_key','sha256','name')}
    path=(ROOT/snapshot['object_key']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():raise HTTPException(404)
    s.rollback()
    from .parsing import parse_isolated
    error_code=None
    try:
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=snapshot['sha256']:
                raise ValueError('SOURCE_DIGEST_MISMATCH')
        paragraphs=parse_isolated(path,snapshot['name'].lower())
    except ValueError as error:
        error_code=str(error)
    except OSError:
        error_code='SOURCE_UNAVAILABLE'
    sku=s.scalar(select(Record).where(Record.id==sku_id,Record.workspace==w,Record.kind=='sku').with_for_update())
    source=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='source').with_for_update())
    if not sku or sku.data.get('deleting') or not source or source.data.get('deleting'):raise HTTPException(404)
    if any(source.data.get(field)!=value for field,value in snapshot.items()):
        raise HTTPException(409,detail={'code':'SOURCE_CHANGED'})
    if error_code:
        source.data={**source.data,'parse_status':'failed','error_code':error_code};s.commit()
        raise HTTPException(422,detail={'code':error_code})
    unreadable=any(item.get('status') in {'ocr_failed','unreadable'} for item in paragraphs)
    needs_review=any(item.get('requires_review') for item in paragraphs)
    parse_status=('partial' if any(item.get('text','').strip() for item in paragraphs) else 'failed') if unreadable else ('awaiting_confirmation' if needs_review else 'completed')
    if not any(item.get('text','').strip() for item in paragraphs):parse_status='failed'
    source.data={**source.data,'parse_status':parse_status,'locators':paragraphs};s.commit()
    return {'source_id':id,'parse_status':parse_status,'locators':paragraphs}

from . import ledger
class Review(BaseModel):
    decision:str
    reason:str=''
    expected_review:str|None=None
@app.post('/api/v1/assets/{id}/reviews',status_code=201)
def review_asset(id:str,body:Review,w=Depends(identity),s=Depends(db)):
    if body.decision not in {'adopt','reject'}:raise HTTPException(422)
    asset=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='asset').with_for_update())
    if not asset or asset.data.get('deleting'):raise HTTPException(404)
    if body.expected_review is not None and asset.data.get('review','pending')!=body.expected_review:
        raise HTTPException(409,detail={'code':'ASSET_REVIEW_CHANGED'})
    work=get(s,asset.data['work_id'],w,'work')
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    review=Record(workspace=w,kind='review',data={'asset_id':id,'asset_revision':asset.revision,'decision':body.decision,'reason':body.reason})
    s.add(review)
    asset.data={**asset.data,'review':'approved' if body.decision=='adopt' else 'rejected'}
    if body.decision=='reject' and 'label_verification' in asset.data:
        asset.data={key:value for key,value in asset.data.items() if key!='label_verification'}
    s.commit()
    return output(review)
class ExportRequest(BaseModel):
    work_id:str
    mode:str
    selection:str
    asset_ids:list[str]|None=Field(default=None,min_length=1,max_length=32)
@app.post('/api/v1/export-packages')
def export_package(body:ExportRequest,w=Depends(identity),s=Depends(db)):
    work=get(s,body.work_id,w,'work')
    if body.mode not in {'sample','release'} or body.selection not in {'video_only','poster_only','full_suite'}:raise HTTPException(422)
    from .exporting import EXPORT_KINDS, build_sample, export_rights
    result_id=work.data.get('current_result')
    if not result_id:raise HTTPException(409,detail={'code':'MEDIA_NOT_AVAILABLE'})
    result=get(s,result_id,w,'result_revision')
    if result.data.get('work_id')!=body.work_id:raise HTTPException(409,detail={'code':'RESULT_WORK_MISMATCH'})
    current_ids=result.data.get('assets',[])
    partial=body.asset_ids is not None
    selected_ids=body.asset_ids if partial else current_ids
    if partial and (len(selected_ids)!=len(set(selected_ids)) or not set(selected_ids)<=set(current_ids)):
        raise HTTPException(409,detail={'code':'INVALID_ASSET_SELECTION'})
    assets=[get(s,asset_id,w,'asset') for asset_id in selected_ids]
    if any(a.data.get('work_id')!=body.work_id or a.data.get('deleting') for a in assets):
        raise HTTPException(409,detail={'code':'ASSET_NOT_AVAILABLE'})
    if partial and any(a.data.get('media_kind') not in EXPORT_KINDS[body.selection] for a in assets):
        raise HTTPException(409,detail={'code':'INVALID_ASSET_SELECTION'})
    rights=export_rights(s,w,work,result,body.selection,assets)
    from .release import require_repair_reviews
    try:
        require_repair_reviews(s,work,(asset for asset in assets if asset.data.get('media_kind') in EXPORT_KINDS[body.selection]))
        if body.mode=='release':
            from .release import package_release
            if get(s,work.data['profile_id'],w,'profile').data.get('status')!='confirmed':
                raise ValueError('FACT_REVOKED')
            package=package_release(work,assets,body.selection,rights=rights,partial=partial)
        else:package=build_sample(work,assets,body.selection,rights=rights,partial=partial)
    except ValueError as error:raise HTTPException(409,detail={'code':str(error)})
    return create(s,w,'export',{'work_id':body.work_id,'sku_id':work.data['sku_id'],**package})

class ManualCopyDraft(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    body:str=Field(min_length=1,max_length=1500)
    poster_title:str=Field(min_length=1,max_length=200)
    selling_points:list[str]=Field(min_length=1,max_length=8)
    shots:list[str]=Field(min_length=1,max_length=3)

class TaskAction(BaseModel):
    action:str
    authorized:bool=False
    shots:list[str]=[]
    manual_copy:dict[str,ManualCopyDraft]|None=None
@app.post('/api/v1/tasks/{id}/actions')
def task_action(id:str,body:TaskAction,w=Depends(identity),s=Depends(db)):
    from .execution import Task
    task=s.scalar(select(Task).where(Task.id==id,Task.workspace==w).with_for_update())
    if not task:raise HTTPException(404)
    if body.action=='cancel' and task.state in {'queued','running','paused','unknown','external_unknown','recovery_required'}:
        # Cancellation never settles or releases external reservations.
        task.state='canceled';task.fencing_token+=1
    elif body.action=='pause' and task.state=='queued':task.state='paused'
    elif body.action=='pause' and task.state=='running':task.payload={**task.payload,'_pause_requested':True}
    elif body.action=='resume' and task.state=='paused':
        task.state='queued';task.payload={**task.payload,'_pause_requested':False}
    elif body.action=='recover':
        from .recovery import recover
        recover(s,task)
    elif body.action=='static_fallback':
        from .recovery import select_static_fallback
        select_static_fallback(s,task,body.shots,body.authorized)
    elif body.action=='manual_copy':
        from .recovery import take_over_copy
        if not body.manual_copy:raise HTTPException(422,detail={'code':'MANUAL_COPY_REQUIRED'})
        take_over_copy(s,task,{platform:draft.model_dump() for platform,draft in body.manual_copy.items()},body.authorized)
    elif body.action=='query' and task.state in {'failed','partial','unknown','external_unknown','recovery_required','canceled'}:
        s.commit()
        try:
            from marketing_worker.business import query_task
            from marketing_worker.http_providers import ExternalUnknown, ProviderRejected
            query_task({'id':task.id,'workspace':w,'payload':task.payload})
        except ImportError:raise HTTPException(409,detail={'code':'QUERY_NOT_CONFIGURED'}) from None
        except ValueError:raise HTTPException(409,detail={'code':'QUERY_NOT_AUTHORIZED'}) from None
        except (ExternalUnknown,ProviderRejected):raise HTTPException(502,detail={'code':'VIDEO_QUERY_FAILED'}) from None
    else:raise HTTPException(409,'当前状态不允许此操作')
    s.commit()
    from .task_views import task_view
    return task_view(s,task)


@app.post('/api/v1/profiles/{id}/revoke')
def revoke_profile(id:str,w=Depends(identity),s=Depends(db)):
    profile=get(s,id,w,'profile')
    profile.data={**profile.data,'status':'revoked'};s.commit()
    return output(profile)


@app.get('/api/v1/skus/{id}/deletion-preview')
def sku_deletion_preview(id:str,w=Depends(identity),s=Depends(db)):
    from .deletion import sku_deletion_impact
    get(s,id,w,'sku')
    return JSONResponse(sku_deletion_impact(s,w,id),headers={'Cache-Control':'private, no-store'})


@app.delete('/api/v1/skus/{id}',status_code=202)
def delete_sku(id:str,w=Depends(identity),s=Depends(db)):
    from .execution import Task
    from .deletion import ACTIVE_TASK_STATES,sku_records,sku_tasks
    sku=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='sku').with_for_update())
    if not sku or sku.data.get('deleting'):raise HTTPException(404)
    related=sku_records(w,id)
    # Prevent an existing creation request from admitting another task during deletion.
    s.scalars(related.where(Record.kind=='creation_request').order_by(Record.id).with_for_update()).all()
    tasks=s.scalars(sku_tasks(w,id).where(Task.state.in_(ACTIVE_TASK_STATES)).order_by(Task.id).with_for_update()).all()
    # Workers persist with the task row locked before the work row.
    for task in tasks:
        task.state='canceled'
        task.fencing_token+=1
    sku.data={**sku.data,'deleting':True}
    for row in s.scalars(related.order_by(Record.id).with_for_update().execution_options(populate_existing=True)):
        row.data={**row.data,'deleting':True}
    result=create(s,w,'deletion',{'sku_id':id,'state':'access_revoked','physical_cleanup':'pending','external_cleanup':'unverified'})
    return result
@app.get('/api/v1/deletions/{id}')
def deletion_state(id:str,w=Depends(identity),s=Depends(db)):
    return output(get(s,id,w,'deletion'))
app.router.routes.sort(key=lambda route: 1 if getattr(route,'path','')=='/api/v1/{collection}/{id}' else 0)



@app.get('/api/v1/exports/{id}/download')
def download_export(id:str,w=Depends(identity),s=Depends(db)):
    from fastapi.responses import FileResponse
    package=get(s,id,w,'export');work=get(s,package.data['work_id'],w,'work')
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data['status']=='revoked':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    release=package.data['manifest']['mode']=='release'
    from .release import require_repair_reviews
    if release:
        if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
        from .release import require_label_verification, rules_fingerprint, ruleset
        try:rules=ruleset()
        except (ValueError,KeyError):raise HTTPException(409,detail={'code':'RULESET_UNVERIFIED'}) from None
        if rules['version']!=package.data['manifest']['rule_version'] or rules_fingerprint(rules)!=package.data['manifest'].get('rule_sha256'):
            raise HTTPException(409,detail={'code':'RULESET_CHANGED'})
    assets=[]
    for ref in package.data['manifest']['assets']:
        asset=get(s,ref['id'],w,'asset')
        assets.append(asset)
        if asset.revision!=ref['revision']:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
        if release and asset.data.get('review')!='approved':raise HTTPException(409,detail={'code':'REVIEW_REQUIRED'})
        if not release and asset.data.get('review')=='rejected':raise HTTPException(409,detail={'code':'ASSET_REJECTED'})
        if release:
            if asset.data.get('release_sha256')!=ref['sha256']:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
            try:require_label_verification(asset,rules)
            except ValueError as error:raise HTTPException(409,detail={'code':str(error)}) from None
    from .exporting import export_rights, require_release_rights, verified_package_path
    try:
        require_repair_reviews(s,work,assets)
        if release:
            manifest=package.data['manifest']
            revision=get(s,manifest['result_revision_id'],w,'result_revision')
            if revision.data.get('work_id')!=work.id:raise ValueError('RESULT_WORK_MISMATCH')
            rights=export_rights(s,w,work,revision,manifest['selection'],assets)
            require_release_rights(rights)
            if rights!=manifest.get('material_rights'):raise ValueError('MATERIAL_RIGHTS_CHANGED')
        path=verified_package_path(package.data)
    except ValueError as error:
        raise HTTPException(409,detail={'code':str(error)}) from None
    return FileResponse(path,filename='release.zip' if release else 'internal-sample.zip')





class RevisionAction(BaseModel):
    expected_revision:int
    authorized:bool=False
    platform:str|None=None
    quote_id:str|None=None
@app.post('/api/v1/works/{id}/apply')
def apply_work(id:str,body:RevisionAction,idempotency_key:str=Header(default=''),w=Depends(identity),s=Depends(db)):
    from .versions import apply_text,submit_edit,apply_restore,replay_edit
    work=get(s,id,w,'work')
    replay = replay_edit(s,w,id,body.expected_revision,idempotency_key,body.quote_id,body.authorized)
    if replay is not None:return replay
    if body.quote_id:
        return submit_edit(s,w,id,body.expected_revision,idempotency_key,body.authorized,body.quote_id)
    if work.data.get('draft',{}).get('restore_revision_id'):return apply_restore(s,w,id,body.expected_revision)
    try:return apply_text(s,w,id,body.expected_revision)
    except HTTPException as error:
        if not isinstance(error.detail,dict) or error.detail.get('code')!='MEDIA_UPDATE_AUTHORIZATION_REQUIRED':raise
        return submit_edit(s,w,id,body.expected_revision,idempotency_key,body.authorized,body.quote_id)
@app.get('/api/v1/works/{id}/history')
def work_history(id:str,w=Depends(identity),s=Depends(db)):
    get(s,id,w,'work')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='result_revision',
        Record.data['work_id'].as_string()==id).order_by(Record.created_at.desc().nullslast(),Record.id)).all()
    return {'items':[output(r) for r in rows]}

@app.get('/api/v1/works/{id}/fact-sources')
def work_fact_sources(id:str,platform:str,w=Depends(identity),s=Depends(db)):
    work=get(s,id,w,'work')
    if platform not in work.data.get('platforms',[]):raise HTTPException(422,detail={'code':'INVALID_PLATFORM'})
    result=get(s,work.data.get('current_result'),w,'result_revision')
    if result.data.get('work_id')!=id:raise HTTPException(404)
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    snapshot=profile.data
    if request_id:=work.data.get('creation_request_id'):
        request=get(s,request_id,w,'creation_request')
        snapshot=request.data['profile_snapshot']
    content=result.data.get('copy',{}).get(platform,{})
    refs=[*content.get('fact_refs',[]),*(ref for shot in content.get('shots',[]) for ref in shot.get('fact_refs',[]))]
    facts=snapshot.get('facts',{});locators=snapshot.get('fact_sources',{})
    entries=[]
    for ref in dict.fromkeys(refs):
        if ref not in facts:continue
        locator=locators.get(ref,{})
        source=s.get(Record,locator['source_id']) if locator.get('source_id') else None
        if source and (source.workspace!=w or source.kind!='source' or source.data.get('sku_id')!=work.data['sku_id'] or source.data.get('deleting')):
            source=None
        entries.append({'id':ref,'value':facts[ref],
            'source_name':source.data.get('name') if source else None,'origin':locator.get('origin'),
            'page':locator.get('page') if source else None,'paragraph':locator.get('paragraph') if source else None})
    return {'profile_id':profile.id,'result_revision_id':result.id,'platform':platform,'items':entries}

@app.post('/api/v1/works/{id}/history/{revision_id}/restore')
def restore_work(id:str,revision_id:str,body:RevisionAction,w=Depends(identity),s=Depends(db)):
    work=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    revision=get(s,revision_id,w,'result_revision')
    if revision.data.get('work_id')!=id:raise HTTPException(404)
    if work.revision!=body.expected_revision:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data['status']=='revoked':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    platforms=work.data.get('platforms',[])
    platform=body.platform or (platforms[0] if len(platforms)==1 else None)
    if platforms and platform not in platforms:raise HTTPException(422,'请指定恢复平台')
    old_copy=revision.data.get('copy',{})
    selected=old_copy.get(platform,{}) if platform else old_copy
    restored={k:v for k,v in selected.items() if k in {'title','body'}}
    if platform:restored['platform']=platform
    restored['restore_revision_id']=revision_id
    work.data={**work.data,'draft_history':work.data.get('draft_history',[])+[work.data.get('draft',{})],'draft':restored}
    work.revision+=1;s.commit();return output(work)


class RewriteRequest(BaseModel):
    expected_revision:int
    platform:str
    instruction:str=Field(min_length=1,max_length=2000)
    authorized:bool=False
@app.post('/api/v1/works/{id}/rewrite',status_code=202)
def rewrite_work(id:str,body:RewriteRequest,idempotency_key:str=Header(default=''),w=Depends(identity),s=Depends(db)):
    from .execution import Task
    import uuid
    work=s.scalar(select(Record).where(Record.id==id,Record.workspace==w,Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    if work.revision!=body.expected_revision:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    if body.platform not in work.data['platforms']:raise HTTPException(422,'未选择该平台')
    if not body.authorized:raise HTTPException(409,detail={'code':'CONSENT_REQUIRED'})
    if not idempotency_key:raise HTTPException(422,'缺少幂等键')
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    try:
        from marketing_worker.business import readiness,authorization_snapshot
        blockers=readiness()
    except ImportError:blockers=['PROVIDER_NOT_CONFIGURED']
    if blockers:raise HTTPException(409,detail={'code':'PROVIDER_NOT_CONFIGURED','blockers':blockers})
    task_id=str(uuid.uuid5(uuid.NAMESPACE_URL,w+':rewrite:'+idempotency_key))
    payload={'work_id':id,'base_draft_revision':body.expected_revision,'platform':body.platform,'instruction':body.instruction,'profile_id':work.data['profile_id']}
    old=s.get(Task,task_id)
    if old:
        if any(old.payload.get(k)!=v for k,v in payload.items()):raise HTTPException(409,detail={'code':'IDEMPOTENCY_CONFLICT'})
        return {'task_id':old.id}
    consent_id=str(uuid.uuid4())
    try:consent=authorization_snapshot(w,work.data['creation_request_id'])
    except ValueError:raise HTTPException(409,detail={'code':'CONSENT_SCOPE_MISMATCH'}) from None
    s.add(Record(id=consent_id,workspace=w,kind='processing_consent',data={**consent,'work_id':id,'profile_id':profile.id,'base_draft_revision':body.expected_revision,'platform':body.platform,'purpose':'copy_rewrite','instruction':body.instruction}))
    payload['consent_id']=consent_id
    s.add(Task(id=task_id,workspace=w,state='queued',phase='copy_rewrite',payload=payload));s.commit()
    return {'task_id':task_id}
@app.post('/api/v1/copy-versions/{id}/adopt')
def adopt_copy(id:str,body:RevisionAction,w=Depends(identity),s=Depends(db)):
    candidate=get(s,id,w,'copy_candidate')
    work=s.scalar(select(Record).where(Record.id==candidate.data['work_id'],Record.workspace==w,Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    if work.revision!=body.expected_revision or candidate.data['base_draft_revision']!=work.revision:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    platform=candidate.data['platform']
    if platform not in work.data.get('platforms',[]):raise HTTPException(422,detail={'code':'INVALID_PLATFORM'})
    draft=work.data.get('draft',{})
    if draft and draft.get('platform') not in (None,platform):
        raise HTTPException(409,detail={'code':'DRAFT_PLATFORM_CONFLICT'})
    proposed=candidate.data.get('changes')
    if not isinstance(proposed,dict) or not proposed or not set(proposed)<={'title','body','narration','poster_title','poster_points'}:
        raise HTTPException(422,detail={'code':'INVALID_COPY_CANDIDATE'})
    changes={**candidate.data['changes'],'platform':candidate.data['platform']}
    work.data={**work.data,'draft_history':work.data.get('draft_history',[])+[work.data.get('draft',{})],'draft':{**work.data.get('draft',{}),**changes}}
    work.revision+=1;s.commit();return output(work)


@app.get('/api/v1/works/{id}/copy-candidates')
def candidates(id:str,w=Depends(identity),s=Depends(db)):
    get(s,id,w,'work')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='copy_candidate')).all()
    return {'items':[output(row) for row in rows if row.data.get('work_id')==id]}
@app.get('/api/v1/assets/{id}/download')
def download_asset(id:str,w=Depends(identity),s=Depends(db)):
    from .sources import ROOT
    from fastapi.responses import FileResponse
    asset=get(s,id,w,'asset');work=get(s,asset.data['work_id'],w,'work')
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    path=(ROOT/asset.data['object_key']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():raise HTTPException(404)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=asset.data['sha256']:raise HTTPException(409,detail={'code':'MEDIA_HASH_MISMATCH'})
    if not asset.data.get('sample_marked'):raise HTTPException(409,detail={'code':'SAMPLE_MARK_REQUIRED'})
    return FileResponse(path,filename='internal-sample'+asset.data.get('extension','.bin'))

@app.post('/api/v1/sources/{id}/fact-candidates',status_code=201)
def extract_source_facts(id:str,w=Depends(identity),s=Depends(db)):
    from .facts import extract_candidates
    source=get(s,id,w,'source')
    if source.data.get('parse_status') not in {'completed','partial','awaiting_confirmation'}:raise HTTPException(409,detail={'code':'PARSE_REQUIRED'})
    candidates=extract_candidates(source.data.get('locators',[]),id)
    existing=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='fact_candidate')).all()
    outputs=[]
    for candidate in candidates:
        old=next((r for r in existing if r.data.get('source_id')==id and r.data.get('key')==candidate['key'] and r.data.get('value')==candidate['value'] and r.data.get('locator')==candidate['locator']),None)
        if old:outputs.append(output(old));continue
        outputs.append(create(s,w,'fact_candidate',{'sku_id':source.data['sku_id'],'source_id':id,**candidate}))
    return {'items':outputs,'extraction_method':'deterministic_key_value'}
@app.get('/api/v1/skus/{id}/fact-candidates')
def list_facts(id:str,w=Depends(identity),s=Depends(db)):
    get(s,id,w,'sku')
    rows=s.scalars(select(Record).where(Record.workspace==w,Record.kind=='fact_candidate')).all()
    items=[output(r) for r in rows if r.data.get('sku_id')==id]
    conflicts=sorted({item['key'] for item in items if len({other['value'] for other in items if other['key']==item['key']})>1})
    return {'items':items,'conflicting_keys':conflicts}

class RepairRequest(BaseModel):
    original_source_id:str
    mask_source_id:str

@app.post('/api/v1/assets/{id}/apply-repair')
def apply_repair(id:str,body:RevisionAction,w=Depends(identity),s=Depends(db)):
    from .versions import apply_repair_candidate
    return apply_repair_candidate(s,w,id,body.expected_revision)

@app.post('/api/v1/assets/{id}/repairs',status_code=202)
def repair_asset(id:str,body:RepairRequest,idempotency_key:str=Header(default=''),w=Depends(identity),s=Depends(db)):
    from .execution import Task
    import uuid
    candidate=get(s,id,w,'asset');work=get(s,candidate.data['work_id'],w,'work')
    profile=get(s,work.data['profile_id'],w,'profile')
    if profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    if candidate.data.get('media_kind') not in {'product_image','marketing_poster','cover'}:raise HTTPException(422,'仅支持图片局部修复')
    for source_id in (body.original_source_id,body.mask_source_id):
        source=get(s,source_id,w,'source')
        if source.data.get('sku_id')!=work.data['sku_id'] or source.data.get('type')!='image' or not source.data.get('rights_confirmed'):raise HTTPException(422,'修复素材不符合当前商品范围')
    if not idempotency_key:raise HTTPException(422,'缺少幂等键')
    task_id=str(uuid.uuid5(uuid.NAMESPACE_URL,w+':repair:'+idempotency_key))
    payload={'work_id':work.id,'candidate_asset_id':id,**body.model_dump()}
    old=s.get(Task,task_id)
    if old:
        if any(old.payload.get(k)!=v for k,v in payload.items()):raise HTTPException(409,detail={'code':'IDEMPOTENCY_CONFLICT'})
        return {'task_id':old.id}
    s.add(Task(id=task_id,workspace=w,state='queued',phase='repair_asset',payload=payload));s.commit()
    return {'task_id':task_id}

class SourceSelection(BaseModel):
    expected_revision:int
    product_source_id:str
    mask_source_id:str
    reviewed:bool=False
@app.post('/api/v1/skus/{id}/source-selection')
def source_selection(id:str,body:SourceSelection,w=Depends(identity),s=Depends(db)):
    from .source_selection import select_sources
    return select_sources(s,w,id,body.expected_revision,body.product_source_id,body.mask_source_id,body.reviewed)
@app.get('/api/v1/skus/{id}/source-selection')
def current_source_selection(id:str,w=Depends(identity),s=Depends(db)):
    sku=get(s,id,w,'sku')
    if not sku.data.get('source_selection_id'):return {'selection':None}
    return {'selection':output(get(s,sku.data['source_selection_id'],w,'source_selection'))}


@app.get('/api/v1/skus/{id}/subject-preview')
def preview_subject(id:str,product_id:str,mask_id:str,w=Depends(identity),s=Depends(db)):
    from .source_selection import subject_preview
    get(s,id,w,'sku')
    return Response(subject_preview(s,w,id,product_id,mask_id),media_type='image/png',
                    headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
