"""Immutable result revisions and safe text-only application."""
from sqlalchemy import func, select
from fastapi import HTTPException
from .db import Record
import uuid


def next_result_number(session,work):
    """Allocate under the work row lock. Legacy result rows count as prior versions."""
    return 1+session.scalar(select(func.count()).select_from(Record).where(
        Record.workspace==work.workspace,Record.kind=='result_revision',
        Record.data['work_id'].as_string()==work.id,
    ))


def apply_repair_candidate(session,workspace,asset_id,expected_revision):
    from pathlib import Path
    from hashlib import sha256
    from .sources import ROOT
    from .execution import Task
    candidate=session.scalar(select(Record).where(Record.id==asset_id,Record.workspace==workspace,
        Record.kind=='asset').with_for_update())
    if not candidate or candidate.data.get('deleting') or not candidate.data.get('repair_task_id'):
        raise HTTPException(404)
    work=session.scalar(select(Record).where(Record.id==candidate.data['work_id'],Record.workspace==workspace,
        Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    if work.revision!=expected_revision:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    if candidate.data.get('review')!='approved':raise HTTPException(409,detail={'code':'REVIEW_REQUIRED'})
    if work.data.get('draft'):raise HTTPException(409,detail={'code':'PENDING_DRAFT'})
    profile=session.get(Record,work.data['profile_id'])
    if not profile or profile.workspace!=workspace or profile.data.get('status')!='confirmed' or profile.data.get('deleting'):
        raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    current=session.get(Record,work.data.get('current_result')) if work.data.get('current_result') else None
    if not current or current.workspace!=workspace or current.kind!='result_revision' or current.data.get('work_id')!=work.id:
        raise HTTPException(409,detail={'code':'RESULT_NOT_AVAILABLE'})
    parent=candidate.data['parent_asset_id']
    if parent not in current.data['assets']:raise HTTPException(409,detail={'code':'REPAIR_BASE_CHANGED'})
    original=session.get(Record,parent)
    if not original or original.workspace!=workspace or original.kind!='asset' or original.data.get('work_id')!=work.id or original.data.get('deleting') or any(
        original.data.get(field)!=candidate.data.get(field) for field in ('media_kind','slot')
    ):raise HTTPException(409,detail={'code':'REPAIR_BASE_CHANGED'})
    active=session.scalar(select(Task.id).where(
        Task.workspace==workspace,Task.payload['work_id'].as_string()==work.id,
        Task.phase.in_({'creation_run','edit_run'}),Task.state.in_({'queued','running','paused'}),
    ).limit(1))
    if active:raise HTTPException(409,detail={'code':'WORK_TASK_ACTIVE'})
    path=(ROOT/Path(candidate.data['object_key'])).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or sha256(path.read_bytes()).hexdigest()!=candidate.data['sha256']:
        raise HTTPException(409,detail={'code':'MEDIA_HASH_MISMATCH'})
    assets=[asset_id if asset_id!=parent else candidate.id for asset_id in current.data['assets']]
    revision=Record(id=str(uuid.uuid4()),workspace=workspace,kind='result_revision',data={**current.data,
        'parent_revision':current.id,'result_number':next_result_number(session,work),'assets':assets})
    session.add(revision)
    work.data={**work.data,'current_result':revision.id}
    work.revision+=1
    session.commit()
    return {'work_id':work.id,'current_result':revision.id,'result_number':revision.data['result_number'],'media_calls':0}

def apply_text(session,workspace,work_id,expected):
    work=session.scalar(select(Record).where(Record.id==work_id,Record.workspace==workspace,Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    if work.revision!=expected:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    if work.data.get('profile_id'):
        profile=session.get(Record,work.data['profile_id'])
        if not profile or profile.workspace!=workspace or profile.kind!='profile' or profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    current=session.get(Record,work.data.get('current_result')) if work.data.get('current_result') else None
    if current is None:raise HTTPException(409,detail={'code':'RESULT_NOT_AVAILABLE'})
    if current.workspace!=workspace or current.kind!='result_revision' or current.data.get('work_id')!=work_id:raise HTTPException(404)
    draft=work.data.get('draft',{})
    if not draft:raise HTTPException(409,detail={'code':'NO_CHANGES'})
    if not set(draft)<={'platform','title','body'}:raise HTTPException(409,detail={'code':'MEDIA_UPDATE_AUTHORIZATION_REQUIRED'})
    platforms=work.data.get('platforms',[])
    platform=draft.get('platform') or (platforms[0] if len(platforms)==1 else None)
    if len(platforms)>1 and not platform:raise HTTPException(422,'请指定修改平台')
    if platform and platform not in platforms:raise HTTPException(422,detail={'code':'INVALID_PLATFORM'})
    changes={k:v for k,v in draft.items() if k!='platform'}
    if not changes:raise HTTPException(409,detail={'code':'NO_CHANGES'})
    copy=dict(current.data.get('copy',{}))
    if platform:copy[platform]={**copy.get(platform,{}),**changes}
    else:copy.update(changes)
    assets=list(current.data.get('assets',[]))
    if platform:
        import json
        from .sources import store
        key,digest=store(json.dumps({'notice':'内部样片/未审核','platform':platform,'copy':copy[platform]},ensure_ascii=False).encode('utf-8'))
        release_key,release_digest=store(json.dumps({'platform':platform,'copy':copy[platform]},ensure_ascii=False).encode('utf-8'))
        asset_id=str(uuid.uuid4())
        session.add(Record(id=asset_id,workspace=workspace,kind='asset',data={'work_id':work_id,'media_kind':'copy','slot':platform,'object_key':key,'sha256':digest,'release_object_key':release_key,'release_sha256':release_digest,'sample_marked':True,'review':'pending','extension':'.json'}))
        assets=[aid for aid in assets if not ((a:=session.get(Record,aid)) and a.data.get('media_kind')=='copy' and a.data.get('slot')==platform)]+[asset_id]
    revision=Record(id=str(uuid.uuid4()),workspace=workspace,kind='result_revision',data={**current.data,'parent_revision':current.id,'result_number':next_result_number(session,work),'copy':copy,'assets':assets,'copy_review':'pending'})
    session.add(revision)
    work.data={**work.data,'current_result':revision.id,'draft':{},'draft_history':work.data.get('draft_history',[])+[draft]}
    work.revision+=1;session.commit()
    return {'id':work.id,'revision':work.revision,'current_result':revision.id,'media_calls':0}


def replay_edit(session, workspace, work_id, expected, key, quote_id, authorized):
    if not key:
        return None
    from .execution import Task
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace+':edit:'+key))
    task = session.get(Task, task_id)
    if task is None:
        return None
    if not authorized:
        raise HTTPException(409, detail={'code':'CONSENT_REQUIRED'})
    if (task.workspace != workspace or task.phase != 'edit_run' or
        task.payload.get('work_id') != work_id or
        task.payload.get('base_draft_revision') != expected or task.payload.get('quote_id') != quote_id):
        raise HTTPException(409, detail={'code':'IDEMPOTENCY_CONFLICT'})
    return {'task_id': task.id, 'work_id': work_id}


def require_no_active_edit(session, workspace, work_id, expected):
    from .execution import Task
    active_edit = session.scalar(select(Task.id).where(
        Task.workspace == workspace, Task.phase == 'edit_run',
        Task.state.in_({'queued', 'running', 'paused', 'unknown', 'external_unknown', 'recovery_required'}),
        Task.payload['work_id'].as_string() == work_id,
        Task.payload['base_draft_revision'].as_integer() == expected,
    ).limit(1))
    if active_edit is not None:
        raise HTTPException(409, detail={'code':'EDIT_ALREADY_ACTIVE','message':'当前草稿已有修改任务，请先处理该任务。'})


def submit_edit(session, workspace, work_id, expected, key, authorized, quote_id=None):
    from .execution import Task
    from .change_quotes import calculate_quote, quote_scope
    work = session.scalar(select(Record).where(Record.id==work_id, Record.workspace==workspace,
        Record.kind=='work').with_for_update().execution_options(populate_existing=True))
    if not work or work.data.get('deleting'):
        raise HTTPException(404)
    replay = replay_edit(session, workspace, work_id, expected, key, quote_id, authorized)
    if replay is not None:
        return replay
    if work.revision != expected:
        if quote_id:
            raise HTTPException(409, detail={'code':'CHANGE_QUOTE_STALE','message':'草稿版本已变化，请重新获取并确认报价。'})
        raise HTTPException(409, detail={'code':'VERSION_CONFLICT'})
    if not authorized:
        raise HTTPException(409, detail={'code':'CONSENT_REQUIRED'})
    if not key:
        raise HTTPException(422, detail={'code':'IDEMPOTENCY_KEY_REQUIRED'})
    if not quote_id:
        raise HTTPException(409, detail={'code':'CHANGE_QUOTE_REQUIRED','message':'请先获取并确认本次修改的报价。'})
    profile = session.get(Record, work.data.get('profile_id'))
    if not profile or profile.workspace != workspace or profile.kind != 'profile' or profile.data.get('status') != 'confirmed' or profile.data.get('deleting'):
        raise HTTPException(409, detail={'code':'FACT_REVOKED'})
    issued = session.get(Record, quote_id)
    quote, authorization = calculate_quote(session, workspace, work)
    if (not issued or issued.workspace != workspace or issued.kind != 'change_quote' or
        authorization is None or issued.data != quote_scope(work, quote, authorization)):
        raise HTTPException(409, detail={'code':'CHANGE_QUOTE_STALE','message':'修改内容或费用配置已变化，请重新获取并确认报价。'})
    require_no_active_edit(session, workspace, work_id, expected)
    current = session.get(Record, work.data.get('current_result'))
    if not current or current.kind != 'result_revision' or current.workspace != workspace or current.data.get('work_id') != work_id:
        raise HTTPException(404)
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace+':edit:'+key))
    draft = work.data.get('draft', {})
    platforms = work.data['platforms']
    if not draft.get('platform') and len(platforms) == 1:
        draft = {**draft, 'platform':platforms[0]}
    consent_id = str(uuid.uuid4())
    payload = {'work_id':work_id,'base_result_id':current.id,'base_result':current.data,
               'base_draft_revision':expected,'draft':draft,'profile_id':work.data['profile_id'],
               'platforms':platforms,'consent_id':consent_id,'quote_id':quote_id}
    if authorization.get('execution_mode')=='local_only':
        payload['execution_mode']='local_only'
    session.add(Record(id=consent_id,workspace=workspace,kind='processing_consent',data={
        **authorization,'work_id':work_id,'profile_id':payload['profile_id'],'base_result_id':current.id,
        'base_draft_revision':expected,'draft':draft,'quote_id':quote_id,
        'cost_upper_bound':quote['cost_upper_bound']}))
    issued.data = {**issued.data, 'task_id':task_id}
    session.add(Task(id=task_id,workspace=workspace,state='queued',phase='edit_run',payload=payload))
    session.commit()
    return {'task_id':task_id,'work_id':work_id}


def apply_restore(session,workspace,work_id,expected):
    from .execution import Task
    work=session.scalar(select(Record).where(Record.id==work_id,Record.workspace==workspace,Record.kind=='work').with_for_update())
    if not work or work.data.get('deleting'):raise HTTPException(404)
    if work.revision!=expected:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    active=session.scalar(select(Task.id).where(
        Task.workspace==workspace,Task.payload['work_id'].as_string()==work_id,
        Task.phase.in_({'creation_run','edit_run'}),Task.state.in_({'queued','running','paused'}),
    ).limit(1))
    if active:raise HTTPException(409,detail={'code':'WORK_TASK_ACTIVE'})
    target_id=work.data.get('draft',{}).get('restore_revision_id')
    if not target_id:raise HTTPException(409,detail={'code':'NO_RESTORE_DRAFT'})
    target=session.get(Record,target_id)
    if not target or target.workspace!=workspace or target.kind!='result_revision' or target.data.get('work_id')!=work_id:raise HTTPException(404)
    profile=session.get(Record,work.data['profile_id'])
    if not profile or profile.workspace!=workspace or profile.kind!='profile' or profile.data.get('status')!='confirmed':raise HTTPException(409,detail={'code':'FACT_REVOKED'})
    from .sources import ROOT
    from .release import require_repair_reviews
    import hashlib
    available=set()
    assets=[]
    for asset_id in target.data.get('assets',[]):
        asset=session.get(Record,asset_id)
        if not asset or asset.workspace!=workspace or asset.kind!='asset' or asset.data.get('work_id')!=work_id or asset.data.get('deleting') or asset.data.get('review')=='rejected':raise HTTPException(409,detail={'code':'RESTORE_ASSET_UNAVAILABLE'})
        path=(ROOT/asset.data['object_key']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=asset.data['sha256']:raise HTTPException(409,detail={'code':'RESTORE_ASSET_UNAVAILABLE'})
        available.add((asset.data.get('slot'),asset.data.get('media_kind')))
        assets.append(asset)
    try:require_repair_reviews(session,work,assets)
    except ValueError as error:raise HTTPException(409,detail={'code':str(error)}) from None
    required=[(platform,branch,kind) for platform in work.data['platforms']
              for branch,kind in [('video','video'),('poster','marketing_poster')]]
    missing=[f'{platform}/{branch}' for platform,branch,kind in required if (platform,kind) not in available]
    status='awaiting_review' if not missing else 'partial' if len(missing)<len(required) else 'failed'
    result=Record(id=str(uuid.uuid4()),workspace=workspace,kind='result_revision',data={**target.data,'restored_from':target.id,'parent_revision':work.data.get('current_result'),'result_number':next_result_number(session,work),'review_state':'pending'})
    session.add(result)
    work.data={**work.data,'current_result':result.id,'status':status,'missing_items':missing,
        'draft':{},'draft_history':work.data.get('draft_history',[])+[work.data['draft']]}
    work.revision+=1;session.commit()
    return {'id':work_id,'revision':work.revision,'current_result':result.id,'media_calls':0,'affected_platforms':work.data['platforms']}
