"""Resume only known local failed steps; external ambiguity never resubmits."""
from sqlalchemy import select
from fastapi import HTTPException
from .db import Record
from .execution import Task,ExternalCall


def can_take_over_copy(session, task):
    if task.phase!='creation_run' or task.state not in {'failed','external_unknown','recovery_required'}:
        return False
    request=task.payload.get('request',{})
    if not request.get('facts') or request.get('manual_copy'):
        return False
    step=session.get(Record,task.id+':copy')
    if not step or step.workspace!=task.workspace or step.kind!='task_step':
        return False
    if step.data.get('state') in {'failed','external_unknown','submitting'}:
        return True
    if step.data.get('state')=='succeeded':
        from marketing_worker.pipeline import validate_copy
        try:validate_copy(step.data['result'],request)
        except ValueError:return True
    return False


def take_over_copy(session, task, drafts, authorized):
    if not authorized:raise HTTPException(409,detail={'code':'CONSENT_REQUIRED'})
    if not can_take_over_copy(session,task):raise HTTPException(409,detail={'code':'MANUAL_COPY_NOT_AVAILABLE'})
    profile=session.get(Record,task.payload.get('profile_id'))
    if not profile or profile.workspace!=task.workspace or profile.data.get('status')!='confirmed':
        raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    request=task.payload['request']
    refs=[fact['id'] for fact in request['facts'] if fact.get('validity')=='active']
    if set(drafts)!=set(request['platforms']):raise HTTPException(422,detail={'code':'PLATFORM_MISMATCH'})
    copy={}
    for platform,draft in drafts.items():
        narrations=draft['shots']
        narration=' '.join(narrations)
        if len(narration)>600:raise HTTPException(422,detail={'code':'MANUAL_COPY_NARRATION_TOO_LONG'})
        total=request['duration_seconds']*1000
        base,extra=divmod(total,len(narrations))
        copy[platform]={'title':draft['title'],'body':draft['body'],'poster_title':draft['poster_title'],
            'selling_points':draft['selling_points'],'fact_refs':refs,'narration':narration,
            'shots':[{'narration':line,'duration':(base+(index<extra))/1000,'fact_refs':refs,
                      'asset_slot':('white','scene_1','scene_2')[index]} for index,line in enumerate(narrations)]}
    from marketing_worker.pipeline import validate_copy
    try:validate_copy(copy,request)
    except ValueError:raise HTTPException(422,detail={'code':'MANUAL_COPY_INVALID'}) from None
    task.payload={**task.payload,'request':{**request,'manual_copy':copy},'_pause_requested':False}
    task.state='queued'

def recovery_blockers(session,task):
    steps=session.scalars(select(Record).where(Record.workspace==task.workspace,Record.kind=='task_step')).all()
    failed=[step for step in steps if step.data.get('task_id')==task.id and step.data.get('state')!='succeeded']
    blockers=[]
    replaced={task.id+':'+shot.rsplit('/',1)[0]+'/dynamic/'+shot.rsplit('/',1)[1] for shot in task.payload.get('request',{}).get('static_fallback_shots',[])} if task.phase=='creation_run' else set()
    if task.payload.get('request',{}).get('manual_copy'):replaced.add(task.id+':copy')
    for step in failed:
        if step.id in replaced:continue
        if step.data.get('state') in {'submitting','external_unknown'} or session.get(ExternalCall,step.id):blockers.append(step.id)
    return blockers

def recover(session,task):
    if task.state not in {'failed','partial'}:raise HTTPException(409,'当前任务不允许恢复')
    if recovery_blockers(session,task):raise HTTPException(409,detail={'code':'EXTERNAL_STATE_UNKNOWN','message':'需核查既有调用，不能重新提交'})
    profile_id=task.payload.get('profile_id')
    if profile_id:
        profile=session.get(Record,profile_id)
        if not profile or profile.workspace!=task.workspace or profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    if task.phase == 'edit_run':
        from .versions import require_no_active_edit
        work = session.scalar(select(Record).where(
            Record.id == task.payload['work_id'], Record.workspace == task.workspace,
            Record.kind == 'work',
        ).with_for_update())
        expected = task.payload['base_draft_revision']
        if (not work or work.data.get('deleting') or work.revision != expected or
            work.data.get('current_result') != task.payload['base_result_id']):
            raise HTTPException(409, detail={'code':'VERSION_CONFLICT','message':'草稿版本已变化，无法恢复该修改任务。'})
        require_no_active_edit(session, task.workspace, work.id, expected)
    task.state='queued';task.payload={**task.payload,'_pause_requested':False}
    session.commit()


def select_static_fallback(session,task,shots,authorized):
    if not authorized:raise HTTPException(409,detail={'code':'CONSENT_REQUIRED'})
    if task.phase!='creation_run' or task.state not in {'failed','partial','external_unknown','recovery_required'}:raise HTTPException(409,'当前任务不可改为静图')
    profile=session.get(Record,task.payload.get('profile_id'))
    if not profile or profile.workspace!=task.workspace or profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    content=task.payload['request'].get('manual_copy')
    if not content:
        copy=session.get(Record,task.id+':copy')
        if not copy or copy.workspace!=task.workspace or copy.data.get('state')!='succeeded':raise HTTPException(409,'缺少已验证分镜')
        content=copy.data['result']
    selected=task.payload['request']['platforms']
    allowed={platform+'/'+str(i) for platform,draft in content.items() if platform in selected for i in range(len(draft['shots']))}
    if not shots or len(shots)!=len(set(shots)) or not set(shots)<=allowed:raise HTTPException(422,'静图替代镜头无效')
    for shot in shots:
        platform,index=shot.split('/')
        step=session.get(Record,task.id+':'+platform+'/dynamic/'+index)
        if not step or step.workspace!=task.workspace or step.kind!='task_step' or step.data.get('state') not in {'failed','external_unknown','submitting'}:raise HTTPException(409,'仅失败或未知动态镜头可选择静图替代')
    request={**task.payload['request'],'static_fallback_shots':sorted(set(task.payload['request'].get('static_fallback_shots',[]))|set(shots))}
    session.add(Record(workspace=task.workspace,kind='processing_consent',data={'task_id':task.id,'purpose':'explicit_static_fallback','shots':shots,'existing_reservations_retained':True}))
    task.payload={**task.payload,'request':request,'_pause_requested':False};task.state='queued';session.commit()
