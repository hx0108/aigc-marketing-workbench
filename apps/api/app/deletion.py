"""Resumable private-object cleanup; external completion is never assumed."""
from time import time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from .db import Session,Record
from .execution import ExternalCall,Task
from .ledger import CallReservation
from .sources import ROOT


ACTIVE_TASK_STATES = {'queued','paused','running'}


def sku_records(workspace, sku_id):
    work = aliased(Record)
    work_ids = select(work.id).where(work.workspace==workspace,work.kind=='work',
        work.data['sku_id'].as_string()==sku_id)
    return select(Record).where(Record.workspace==workspace,
        or_(Record.data['sku_id'].as_string()==sku_id,Record.data['work_id'].as_string().in_(work_ids)))


def sku_tasks(workspace, sku_id):
    related = aliased(Record)
    scope = select(related.id).where(related.workspace==workspace,related.data['sku_id'].as_string()==sku_id)
    requests = scope.where(related.kind=='creation_request')
    works = scope.where(related.kind=='work')
    return select(Task).where(Task.workspace==workspace,or_(
        Task.payload['sku_id'].as_string()==sku_id,
        Task.payload['request']['sku_id'].as_string()==sku_id,
        Task.payload['request_id'].as_string().in_(requests),
        Task.payload['request']['request_id'].as_string().in_(requests),
        Task.payload['work_id'].as_string().in_(works),
        Task.payload['request']['work_id'].as_string().in_(works),
    ))


def sku_deletion_impact(session, workspace, sku_id):
    counts = {kind:0 for kind in ('source','work','result_revision','asset','export','task')}
    records = sku_records(workspace,sku_id).with_only_columns(Record.kind)
    for kind,count in session.execute(records.add_columns(func.count()).where(
        Record.kind.in_(counts.keys()),
    ).group_by(Record.kind)):
        counts[kind]=count
    counts['result']=counts.pop('result_revision')
    tasks = sku_tasks(workspace,sku_id)
    task_states = dict(session.execute(tasks.with_only_columns(Task.state,func.count()).group_by(Task.state)).all())
    counts['task']=sum(task_states.values())
    reservations = select(ExternalCall.state,func.count()).join(CallReservation,CallReservation.id==ExternalCall.id).where(
        ExternalCall.task_id.in_(tasks.with_only_columns(Task.id)),
        CallReservation.finalized==False,CallReservation.remaining>0,
    ).group_by(ExternalCall.state)
    fee_states=dict(session.execute(reservations).all())
    return {'sku_id':sku_id,'counts':counts,'active_tasks':sum(task_states.get(state,0) for state in ACTIVE_TASK_STATES),
        'open_fee_reservations':sum(fee_states.values()),
        'unknown_fee_reservations':sum(fee_states.get(state,0) for state in ('unknown','external_unknown')),
        'retention':{'access':'revoke_on_delete','registered_local_files':'async_cleanup',
            'provider_files':'verification_required','fees_and_audit':'retained','unsettled_fees':'reservation_retained'}}


def cleanup_once(sessions=None, *, batch_size=16):
    if not 1<=batch_size<=64:
        raise ValueError('INVALID_CLEANUP_BATCH_SIZE')
    sessions = sessions or Session
    now = time()
    with sessions.begin() as session:
        job = session.scalar(select(Record).where(
            Record.kind=='deletion',
            func.coalesce(Record.data['physical_cleanup'].as_string(),'pending')=='pending',
            func.coalesce(Record.data['retry_after'].as_float(),0)<=now,
        ).order_by(Record.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return False
        pending = session.scalars(sku_records(job.workspace,job.data['sku_id']).where(
            Record.kind.in_({'source','asset','export'}),
            func.coalesce(Record.data['physical_deleted'].as_boolean(),False)==False,
        ).order_by(Record.id).limit(batch_size+1)).all()
        try:
            for record in pending[:batch_size]:
                keys = {record.data.get(field) for field in ('object_key','release_object_key','repair_render_key')} - {None}
                paths = [(ROOT/key).resolve() for key in keys]
                if any(not path.is_relative_to(ROOT) or path==ROOT for path in paths):
                    job.data={**job.data,'physical_cleanup':'blocked','cleanup_error':'INVALID_OBJECT_KEY'}
                    return True
                for path in paths:
                    path.unlink(missing_ok=True)
                record.data={**record.data,'physical_deleted':True,'deleting':True}
        except OSError:
            job.data={**job.data,'cleanup_error':'OBJECT_CLEANUP_RETRY','retry_after':now+30}
            return True
        progress={key:value for key,value in job.data.items() if key not in {'cleanup_error','retry_after'}}
        if len(pending)<=batch_size:
            progress.update(physical_cleanup='completed',state='pending_external_verification')
        job.data=progress
        return True
