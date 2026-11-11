import hashlib
import json
from sqlalchemy import func, select
from app.db import Record
from app.execution import Task, ExternalCall, Budget
from .http_providers import ExternalUnknown


class PauseRequested(RuntimeError):
    code='paused'
from app.ledger import CallReservation, money, prepare
from app.pricing import dynamic_bound


class StepStore:
    def __init__(self, sessions, workspace, token):
        self.sessions, self.workspace, self.token = sessions, workspace, token

    def read(self, task, key):
        with self.sessions() as session:
            row = session.get(Record, task + ':' + key)
            return row.data if row and row.workspace == self.workspace else None

    def canceled(self, task):
        with self.sessions() as session:
            row = session.get(Task, task)
            if row and row.payload.get('_pause_requested'):
                raise PauseRequested('Pause requested before next step')
            return not row or row.workspace != self.workspace or row.state != 'running' or row.fencing_token != self.token

    def write(self, task, key, state, result):
        with self.sessions.begin() as session:
            job = session.scalar(select(Task).where(Task.id == task).with_for_update())
            if not job or job.workspace != self.workspace or job.state != 'running' or job.fencing_token != self.token:
                raise ValueError('stale_task_lease')
            row = session.get(Record, task + ':' + key)
            data = {'state': state, 'result': result, 'task_id':task}
            if row:
                row.data = data
            else:
                session.add(Record(id=task + ':' + key, workspace=self.workspace, kind='task_step', data=data))


class AuthorizedServices:
    """Policy validates immutable consent; ledger reserves before outbound traffic."""
    def __init__(self, sessions, budget_id, policy, handlers, bounds, task_id, workspace, token):
        self.sessions, self.budget_id, self.policy = sessions, budget_id, policy
        self.handlers, self.bounds = handlers, bounds
        self.task_id, self.workspace, self.token = task_id, workspace, token

    def invoke(self, kind, payload, intent):
        self.policy(kind, payload, intent)
        handler = self.handlers[kind]
        external = kind in {'text', 'product_image', 'dynamic', 'tts'} and not (kind == 'product_image' and payload.get('slot') == 'white')
        if external:
            parameters=getattr(self,'provider_parameters',{})
            fingerprint = hashlib.sha256(json.dumps({'payload':payload,'provider_parameters':parameters}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            with self.sessions.begin() as session:
                budget = session.scalar(select(Budget).where(Budget.id == self.budget_id).with_for_update())
                task = session.scalar(select(Task).where(Task.id == self.task_id).with_for_update())
                if not task or task.workspace != self.workspace or task.state != 'running' or task.fencing_token != self.token or not budget or budget.workspace != self.workspace:
                    raise ValueError('submission_not_authorized')
                if task.phase == 'edit_run':
                    work = session.scalar(select(Record).where(
                        Record.id == task.payload['work_id'], Record.workspace == self.workspace,
                        Record.kind == 'work',
                    ).with_for_update())
                    if (not work or work.data.get('deleting') or
                        work.revision != task.payload['base_draft_revision'] or
                        work.data.get('current_result') != task.payload['base_result_id']):
                        raise ValueError('stale_edit_result')
                self.policy(kind, payload, intent)
                previous = session.get(ExternalCall, intent)
                if previous:
                    raise ExternalUnknown('Existing intent requires reconciliation, never resubmit')
                reservation = self.bounds[kind]
                consent_id = task.payload.get('consent_id') or task.payload.get('request', {}).get('consent_id')
                consent = session.get(Record, consent_id) if consent_id else None
                if consent and consent.workspace == self.workspace and consent.kind == 'processing_consent':
                    if kind == 'dynamic':
                        reservation = dynamic_bound(consent.data, payload.get('shot', {}).get('duration'))
                    if 'cost_upper_bound' in consent.data:
                        prior = session.scalar(select(func.coalesce(func.sum(CallReservation.upper_bound), 0))
                            .join(ExternalCall, ExternalCall.id == CallReservation.id)
                            .where(ExternalCall.task_id == task.id, ExternalCall.workspace == self.workspace))
                        if prior + money(reservation) > money(consent.data['cost_upper_bound']):
                            raise ValueError('consent_cost_upper_bound_exceeded')
                prepare(session, self.budget_id, intent, fingerprint, reservation)
                session.add(ExternalCall(id=intent, intent_key=intent, task_id=self.task_id, request_hash=fingerprint, state='submitting'))
        # Completion is not billing evidence: reservation stays until reconciled.
        try:
            result=handler(payload,intent)
        except Exception as error:
            from .pipeline import ContractError
            from .fact_validation import NumericFactError
            with self.sessions.begin() as session:
                call=session.get(ExternalCall,intent)
                remote=session.get(Record,'remote:'+intent)
                known_local_failure=(isinstance(error,(ContractError,NumericFactError)) and
                    remote is not None and remote.workspace==self.workspace and remote.kind=='provider_result' and
                    isinstance(remote.data.get('response'),dict))
                if call and call.task_id==self.task_id:
                    call.state='response_received' if known_local_failure else 'external_unknown'
            raise
        else:
            with self.sessions.begin() as session:
                call=session.get(ExternalCall,intent)
                if call:call.state='response_received'
            return result
