"""Server-owned task actions and fee projections from immutable cost events."""
from decimal import Decimal
from sqlalchemy import select
from .execution import ExternalCall
from .ledger import CallReservation,CostEvent
from .db import Record


def creation_progress(session, task, view):
    if task.state=='succeeded':return 4
    request=task.payload.get('request',{})
    platforms=request.get('platforms',[])
    if not platforms or 'manual_copy' in view['next_actions']:return 0
    stages=[
        [] if request.get('manual_copy') else ['copy'],
        ['image/white','image/scene_1','image/scene_2'],
        [platform+'/voice' for platform in platforms],
        [platform+'/'+branch for platform in platforms for branch in ('video','poster')],
    ]
    ids={task.id+':'+step for stage in stages for step in stage}
    records=session.scalars(select(Record).where(
        Record.id.in_(ids),Record.workspace==task.workspace,Record.kind=='task_step',
    )).all()
    completed={row.id for row in records if row.data.get('state')=='succeeded'}
    for index,stage in enumerate(stages):
        if any(task.id+':'+step not in completed for step in stage):return index
    return 4

def task_view(session,task):
    from .recovery import can_take_over_copy
    fallback_candidates=[]
    actions={'queued':['pause','cancel'],'paused':['resume','cancel'],'running':['pause','cancel'],'unknown':['query','cancel'],'external_unknown':['query','cancel'],'recovery_required':['query','cancel']}.get(task.state,[])
    if task.state in {'failed','partial'}:
        from .recovery import recovery_blockers
        actions=['recover'] if not recovery_blockers(session,task) else ['query']
    if task.phase=='creation_run' and task.state in {'failed','partial','external_unknown','recovery_required'}:
        content=task.payload.get('request',{}).get('manual_copy')
        copy=session.get(Record,task.id+':copy')
        if not content and copy and copy.data.get('state')=='succeeded' and isinstance(copy.data.get('result'),dict):
            content=copy.data['result']
        if content:
            for platform,draft in content.items():
                if not isinstance(draft,dict) or not isinstance(draft.get('shots'),list):continue
                for index in range(len(draft['shots'])):
                    step=session.get(Record,task.id+':'+platform+'/dynamic/'+str(index))
                    if step and step.data.get('state') in {'failed','external_unknown','submitting'}:fallback_candidates.append(platform+'/'+str(index))
            if fallback_candidates:actions.append('static_fallback')
    manual_copy_platforms=[]
    if can_take_over_copy(session,task):
        actions.append('manual_copy')
        manual_copy_platforms=task.payload['request']['platforms']
    if task.payload.get('_pause_requested') and 'pause' in actions:actions.remove('pause')
    calls=session.scalars(select(ExternalCall).where(ExternalCall.task_id==task.id)).all()
    remote_ids={'remote:'+call.intent_key:call.id for call in calls if '/dynamic/' in call.intent_key}
    remote_rows=session.scalars(select(Record).where(
        Record.id.in_(remote_ids), Record.workspace==task.workspace, Record.kind=='provider_result',
    ).order_by(Record.id)).all() if remote_ids else []
    video_checks=[]
    for row in remote_rows:
        response=row.data.get('response',{})
        if not response.get('id') or not response.get('model'):
            continue
        status=response.get('status')
        if status not in ('submitted','queued','pending','processing','running','succeeded','failed','canceled'):
            status='unknown'
        video_checks.append({'call_id':remote_ids[row.id],'status':status})
    if not video_checks and 'query' in actions:
        actions.remove('query')
    if video_checks and task.state=='canceled':
        actions.append('query')
    ids=[call.id for call in calls]
    reservations=session.scalars(select(CallReservation).where(CallReservation.id.in_(ids))).all() if ids else []
    events=session.scalars(select(CostEvent).where(CostEvent.call_id.in_(ids))).all() if ids else []
    unsettled={reservation.id for reservation in reservations if not reservation.finalized}
    from .pagination import timestamp
    return {'error':task_error(session,task),'created_at':timestamp(task.created_at),'created_at_known':task.created_at is not None,'static_fallback_candidates':fallback_candidates,'manual_copy_platforms':manual_copy_platforms,'id':task.id,'work_id':task.payload.get('work_id'),'execution_state':task.state,'phase':task.phase,'video_checks':video_checks,'next_actions':actions,'pause_requested':bool(task.payload.get('_pause_requested')),'estimate_basis':'submitted_calls','estimated_cost':str(sum((r.upper_bound for r in reservations),Decimal(0))),'reserved_cost':str(sum((r.remaining for r in reservations),Decimal(0))),'settled_cost':str(sum((e.amount for e in events),Decimal(0))),'unknown_cost_flag':any(call.id in unsettled and call.state in {'external_unknown','unknown'} for call in calls) or (task.state in {'unknown','external_unknown'} and any(not r.finalized for r in reservations)),'cost_state':'pending' if any(not r.finalized for r in reservations) else 'settled'}








ERROR_MESSAGES={
 'NUMERIC_CLAIM_REVIEW_REQUIRED':('生成文案包含尚未确认的数字或参数，已停止生成。','请核对商品事实与文案中的数字，再处理失败阶段。','copy'),
 'text_input_too_large':('商品资料超过文案服务输入上限，已停止生成。','请缩减商品事实或创意要求后重新创作。','copy'),
 'voice_duration_mismatch':('配音时长超过视频时长，已停止合成。','请缩短口播或调整视频时长。','voice'),
 'TimeoutExpired':('处理超时，当前生成已停止。','请核查任务状态后再恢复，避免重复提交未知调用。','processing'),
 'provider_rejected':('服务商拒绝本次生成请求。','请联系管理员核查服务配置和账号权限。','provider'),
 'external_unknown':('服务商结果尚未确认，本地流程已停止推进。','费用预留保留，请查询既有请求或联系管理员核查；不要重复生成。','provider'),
 'consent_cost_upper_bound_exceeded':('本次授权费用上限不足，已停止后续生成。','请核查已发生费用并重新授权，勿直接重复请求。','authorization'),
}

for code in ('BUDGET_INSUFFICIENT','budget_insufficient'):
    ERROR_MESSAGES[code]=('可用预算不足，已停止后续生成。','请先核对已预留及已结算费用，再决定是否补充预算。','authorization')
for code in ('source_scope_invalid','source_snapshot_hash_mismatch','source_hash_mismatch','reviewed_product_and_mask_required','asset_hash_mismatch','fact_revoked','SOURCE_SCOPE_INVALID'):
    ERROR_MESSAGES[code]=('商品素材或事实已失效，已停止生成。','请重新核对商品资料和原图遮罩；不要重复提交旧任务。','material')
for code in ('NUMERIC_FACT_MISMATCH','INVALID_FACT_REFERENCE'):
    ERROR_MESSAGES[code]=('文案与已确认商品事实不一致，已停止生成。','请核对事实来源和文案内容后再处理。','copy')
STAGE_LABELS={'copy':'创作文案','image':'生成画面','voice':'配音','video':'视频合成','poster':'海报排版','material':'商品资料','authorization':'预算与授权','provider':'外部生成服务','processing':'任务处理'}

def task_error(session,task):
    if task.state not in {'failed','partial','unknown','external_unknown','recovery_required'}:return None
    outcome=task.payload.get('_outcome',{})
    code=outcome.get('error_code') or outcome.get('code') if isinstance(outcome,dict) else None
    stage='processing'
    rows=session.scalars(select(Record).where(Record.workspace==task.workspace,Record.kind=='task_step',Record.id.startswith(task.id+':'))).all()
    for row in rows:
        if row.data.get('state') not in {'failed','external_unknown'}:continue
        result=row.data.get('result',{})
        candidate=result.get('code') if isinstance(result,dict) else None
        suffix=row.id[len(task.id)+1:]
        stage='copy' if suffix=='copy' else 'image' if suffix.startswith('image/') or '/dynamic/' in suffix else 'voice' if suffix.endswith('/voice') else 'video' if suffix.endswith('/video') else 'poster' if suffix.endswith('/poster') else 'processing'
        if candidate in ERROR_MESSAGES:
            code=candidate;break
    if task.state in {'unknown','external_unknown','recovery_required'}:code='external_unknown'
    if code not in ERROR_MESSAGES:
        return {'code':'GENERATION_FAILED','message':'生成已停止，失败原因需要进一步核查。','stage':STAGE_LABELS[stage],'hint':'请联系管理员核查任务；已完成内容和费用记录保留。'}
    message,hint,default_stage=ERROR_MESSAGES[code]
    if stage=='processing':stage=default_stage
    return {'code':code,'message':message,'stage':STAGE_LABELS[stage],'hint':hint}
