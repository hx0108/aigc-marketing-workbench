import logging
import threading
from time import monotonic
from app.operational_events import task_event
from .media import render_poster, compose_video, compose_product, repair_patch
from .providers import ProviderNotConfigured

HANDLERS = {'poster_render': render_poster, 'video_compose': compose_video,
            'product_compose': compose_product, 'repair_patch': repair_patch}


def run_once(repository, owner, services_factory=None):
    job = repository.claim(owner)
    if job is None:
        return False
    identity = (job['id'], job['fencing_token'])
    if repository.canceled(*identity):
        repository.fail(*identity, 'canceled')
        task_event(job['id'],'canceled',code='canceled')
        return True
    task_event(job['id'],'running')
    finished=threading.Event()
    def renew():
        while not finished.wait(30):
            if not repository.heartbeat(*identity,owner):
                return
    heartbeat=threading.Thread(target=renew,daemon=True)
    heartbeat.start()
    try:
        if job['kind']=='repair_asset':
            from .repair import repair_handler
            result=repair_handler(repository,job)
        elif job['kind'] in ('edit_run','copy_rewrite') and services_factory:
            from .edits import edit_handler,rewrite_handler
            result=({'edit_run':edit_handler,'copy_rewrite':rewrite_handler}[job['kind']])(repository,job,services_factory)
        elif job['kind'] == 'creation_run' and services_factory:
            from .bridge import creation_handler
            result = creation_handler(repository, job, services_factory)
        else:
            handler = HANDLERS.get(job['kind'])
            if handler is None:
                raise ProviderNotConfigured('No configured handler')
            result = handler(**job['payload'])
    except Exception as error:
        # Persist a safe error code, not secrets or source data from exception text.
        code = getattr(error,'code',type(error).__name__)
        if code in ('paused','external_unknown'):
            state = code
            recorded = repository._finish(*identity,state,{'code':code})
        else:
            state = 'failed'
            recorded = repository.fail(*identity,code)
        task_event(job['id'],'completion_fenced' if recorded is False else state,code=code,error=error)
    else:
        state = result.get('status')
        if state in ('external_unknown','partial','failed'):
            recorded = repository._finish(*identity,state,result)
        else:
            state = 'succeeded'
            recorded = repository.complete(*identity, result)
        task_event(job['id'],'completion_fenced' if recorded is False else state,
            code=state if state in ('external_unknown','failed') else None)
    finally:
        finished.set()
        heartbeat.join(timeout=1)
    return True


def run(repository, owner, stop, services_factory=None):
    from app.deletion import cleanup_once
    from sqlalchemy.exc import SQLAlchemyError

    next_cleanup = 0
    while not stop.is_set():
        repository.recover_expired()
        now = monotonic()
        if now >= next_cleanup:
            try:
                cleanup_once(repository.sessions)
            except SQLAlchemyError:
                logging.getLogger(__name__).warning('Worker object cleanup transaction failed')
            next_cleanup = now + 1
        if not run_once(repository, owner, services_factory):
            stop.wait(1)


def run_with_heartbeat(repository, owner, stop, storage_root, services_factory=None):
    """Record process-loop presence independently of the duration of a single task."""
    from app import worker_heartbeat
    from threading import Event, Thread

    finished = Event()
    logger = logging.getLogger(__name__)

    def pulse():
        try:
            while not finished.is_set() and not stop.is_set():
                try:
                    worker_heartbeat.publish(storage_root, owner)
                except OSError:
                    logger.warning('Worker heartbeat write failed')
                finished.wait(worker_heartbeat.INTERVAL_SECONDS)
        finally:
            try:
                worker_heartbeat.remove(storage_root, owner)
            except OSError:
                logger.warning('Worker heartbeat cleanup failed; it will expire')

    heartbeat = Thread(target=pulse, daemon=True)
    heartbeat.start()
    try:
        run(repository, owner, stop, services_factory)
    finally:
        finished.set()
        heartbeat.join(timeout=1)
