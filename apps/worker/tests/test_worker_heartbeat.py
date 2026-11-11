from threading import Event
from uuid import uuid4

import pytest

from app import worker_heartbeat
from marketing_worker import runner


@pytest.mark.parametrize('loop_fails', [False, True])
def test_worker_heartbeat_removed_on_normal_or_exception_exit(tmp_path, monkeypatch, loop_fails):
    published = Event()
    instance = uuid4()
    publish = worker_heartbeat.publish

    def tracked_publish(root, owner):
        publish(root, owner)
        published.set()

    def loop(repository, owner, stop, services_factory):
        assert published.wait(timeout=3)
        assert worker_heartbeat.fresh(tmp_path, instance)
        if loop_fails:
            raise RuntimeError('loop stopped')
        stop.set()

    monkeypatch.setattr(worker_heartbeat, 'publish', tracked_publish)
    monkeypatch.setattr(runner, 'run', loop)
    if loop_fails:
        with pytest.raises(RuntimeError, match='loop stopped'):
            runner.run_with_heartbeat(object(), instance, Event(), tmp_path)
    else:
        runner.run_with_heartbeat(object(), instance, Event(), tmp_path)
    assert not worker_heartbeat.fresh(tmp_path, instance)
