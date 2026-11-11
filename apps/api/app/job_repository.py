"""Transactional local-media queue. External submission is deliberately excluded."""
from sqlalchemy import select, update
from .db import Session
from .execution import Task, ExternalCall
import time


class JobRepository:
    def __init__(self, sessions=Session):
        self.sessions = sessions

    def claim(self, owner):
        with self.sessions.begin() as session:
            task = session.scalar(select(Task).where(Task.state == 'queued').with_for_update(skip_locked=True).limit(1))
            if task is None:
                return None
            token = task.fencing_token + 1
            result = session.execute(update(Task).where(Task.id == task.id, Task.state == 'queued', Task.fencing_token == task.fencing_token).values(state='running', fencing_token=token))
            if result.rowcount != 1:
                return None
            task.payload = {**task.payload, '_lease': {'owner': owner, 'expires': time.time() + 900}}
            return {'id': task.id, 'workspace': task.workspace, 'fencing_token': token, 'kind': task.phase, 'payload': {k:v for k,v in task.payload.items() if not k.startswith('_')}}

    def recover_expired(self, now=None):
        """Never replay an expired operation: reconcile output/external outcome first."""
        now = time.time() if now is None else now
        count = 0
        with self.sessions.begin() as session:
            tasks = session.scalars(select(Task).where(Task.state == 'running').with_for_update(skip_locked=True))
            for task in tasks:
                lease = task.payload.get('_lease')
                if lease and lease['expires'] < now:
                    pending=session.scalar(select(ExternalCall.id).where(ExternalCall.task_id==task.id,ExternalCall.state.in_(['submitting','external_unknown','processing'])).limit(1))
                    task.state = 'external_unknown' if pending or task.phase in {'text', 'image', 'video', 'tts'} else 'recovery_required'
                    task.fencing_token += 1
                    count += 1
        return count

    def heartbeat(self, task_id, token, owner, now=None):
        now=time.time() if now is None else now
        with self.sessions.begin() as session:
            task=session.scalar(select(Task).where(Task.id==task_id).with_for_update())
            if task is None or task.state!='running' or task.fencing_token!=token:
                return False
            lease=task.payload.get('_lease',{})
            if lease.get('owner')!=owner or lease.get('expires',0)<=now:
                return False
            task.payload={**task.payload,'_lease':{**lease,'expires':now+900}}
            return True

    def canceled(self, task_id, token):
        with self.sessions() as session:
            task = session.get(Task, task_id)
            return task is None or task.fencing_token != token or task.state != 'running'

    def _finish(self, task_id, token, state, value):
        with self.sessions.begin() as session:
            task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
            if task is None or task.fencing_token != token or task.state != 'running':
                return False
            task.payload = {**task.payload, '_outcome': value}
            task.state = state
            return True

    def complete(self, task_id, token, result):
        return self._finish(task_id, token, 'succeeded', result)

    def fail(self, task_id, token, code):
        return self._finish(task_id, token, 'failed', {'error_code': code})
