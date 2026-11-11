from collections import namedtuple
import os
from time import time
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from app import readiness, sources, worker_heartbeat
from app.main import app, db
from test_core import client


def test_readiness_only_reports_coarse_state_without_requiring_login(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json() == {'status':'ready','worker':'unknown'}
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/v1/skus').status_code == 401
    assert list(tmp_path.iterdir()) == []

    usage = namedtuple('DiskUsage', 'free')
    with patch.object(readiness, 'disk_usage', return_value=usage(free=0)):
        response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status':'unavailable','worker':'unknown'}
    assert client.get('/health').status_code == 200


def test_database_failure_is_unavailable_without_connection_details(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)

    class OfflineSession:
        def execute(self, statement):
            assert str(statement) == 'SELECT 1'
            raise OperationalError('SELECT 1', {}, OSError('private connection details'))

    monkeypatch.setitem(app.dependency_overrides, db, lambda: OfflineSession())
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status':'unavailable','worker':'unknown'}


def test_mounted_static_build_needs_current_referenced_files(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)
    build = tmp_path / 'dist'
    assets = build / 'assets'
    assets.mkdir(parents=True)
    monkeypatch.setattr(app.state, 'readiness_static_root', build, raising=False)
    (build / 'index.html').write_text(
        '<script type="module" src="/assets/current.js"></script>'
        '<script src="/vendor/react.js"></script>', encoding='utf-8',
    )
    (assets / 'stale.js').write_text('old', encoding='utf-8')
    assert client.get('/ready').status_code == 503
    (assets / 'current.js').write_text('current', encoding='utf-8')
    assert client.get('/ready').status_code == 503
    (build / 'vendor').mkdir()
    (build / 'vendor' / 'react.js').write_text('vendor', encoding='utf-8')
    assert client.get('/ready').status_code == 200


def test_trial_requires_its_own_recent_worker_heartbeat(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)
    instance = uuid4()
    monkeypatch.setattr(app.state, 'readiness_worker_instance', instance, raising=False)
    worker_heartbeat.publish(tmp_path, uuid4())
    assert client.get('/ready').status_code == 503

    worker_heartbeat.publish(tmp_path, instance)
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json() == {'status':'ready','worker':'heartbeat_fresh'}

    now = time()
    path = worker_heartbeat.heartbeat_path(tmp_path, instance)
    stale = now - worker_heartbeat.MAX_AGE_SECONDS - 1
    os.utime(path, (stale, stale))
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status':'unavailable','worker':'heartbeat_missing_or_stale'}
    future = now + 10
    os.utime(path, (future, future))
    assert not worker_heartbeat.fresh(tmp_path, instance, now=now)
