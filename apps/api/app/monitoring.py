"""Read-only operational measurements; never infer success or billing from liveness."""
from datetime import datetime, timezone
from sqlalchemy import func, select
from .execution import Budget, ExternalCall, Task


def snapshot(session, workspace, queue_age_limit=None, now=None):
    if not workspace or queue_age_limit is not None and (type(queue_age_limit) is not int or queue_age_limit <= 0):
        raise ValueError('INVALID_MONITOR_SCOPE_OR_THRESHOLD')
    now = now or datetime.now(timezone.utc)
    counts = dict(session.execute(select(Task.state, func.count()).where(Task.workspace == workspace).group_by(Task.state)).all())
    calls = dict(session.execute(select(ExternalCall.state, func.count()).where(ExternalCall.workspace == workspace).group_by(ExternalCall.state)).all())
    queued = session.execute(select(func.min(Task.created_at), func.count()).where(Task.workspace == workspace, Task.state == 'queued')).one()
    unknown_times = session.scalar(select(func.count()).select_from(Task).where(Task.workspace == workspace, Task.state == 'queued', Task.created_at.is_(None)))
    oldest = queued[0]
    if oldest and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    age = max(0, (now - oldest).total_seconds()) if oldest else None
    exceeded = session.scalar(select(func.count()).select_from(Budget).where(Budget.workspace == workspace, Budget.reserved + Budget.settled > Budget.cap))
    alerts = []
    if exceeded:
        alerts.append({'code':'BUDGET_OVER_CAP', 'severity':'critical', 'count':exceeded})
    if calls.get('external_unknown', 0):
        alerts.append({'code':'EXTERNAL_OUTCOME_UNKNOWN', 'severity':'warning', 'count':calls['external_unknown']})
    if counts.get('failed', 0):
        alerts.append({'code':'FAILED_TASKS', 'severity':'warning', 'count':counts['failed']})
    if unknown_times:
        alerts.append({'code':'QUEUE_TIME_UNKNOWN', 'severity':'warning', 'count':unknown_times})
    if queue_age_limit is not None and age is not None and age > queue_age_limit:
        alerts.append({'code':'QUEUE_AGE_EXCEEDED', 'severity':'warning', 'oldest_seconds':age})
    return {'observed_at':now.isoformat(), 'task_states':counts, 'external_call_states':calls,
            'queued_count':queued[1], 'oldest_queue_seconds':age, 'queue_age_limit_seconds':queue_age_limit,
            'queue_threshold_configured':queue_age_limit is not None, 'alerts':alerts,
            'alert_delivery':'not_configured', 'unmeasured':['render_resource_peak','export_failures','cross_account_denials','duplicate_callbacks']}
