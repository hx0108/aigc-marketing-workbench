import unittest,tempfile
import hashlib
from threading import Event
from pathlib import Path
from sqlalchemy import create_engine
from app import db,deletion,parsing,sources
from app.execution import Budget, ExternalCall, Task
from app.ledger import CallReservation
import pytest
from test_core import client
class DeletionTests(unittest.TestCase):
    def test_completed_job_does_not_starve_following_asset_cleanup(self):
        engine=create_engine('sqlite://');db.Base.metadata.create_all(engine)
        old=deletion.Session;old_root=deletion.ROOT
        from sqlalchemy.orm import sessionmaker
        sessions=sessionmaker(engine)
        with tempfile.TemporaryDirectory() as directory:
            deletion.Session=sessions;deletion.ROOT=Path(directory)
            (deletion.ROOT/'media').write_bytes(b'private')
            (deletion.ROOT/'repair-render.png').write_bytes(b'private render source')
            try:
                with sessions.begin() as s:
                    s.add_all([db.Record(id='done',workspace='w',kind='deletion',data={'sku_id':'old','physical_cleanup':'completed'}),db.Record(id='pending',workspace='w',kind='deletion',data={'sku_id':'sku','physical_cleanup':'pending'}),db.Record(id='work',workspace='w',kind='work',data={'sku_id':'sku'}),db.Record(id='asset',workspace='w',kind='asset',data={'work_id':'work','object_key':'media','repair_render_key':'repair-render.png'})])
                self.assertTrue(deletion.cleanup_once())
                self.assertFalse((deletion.ROOT/'media').exists())
                self.assertFalse((deletion.ROOT/'repair-render.png').exists())
                self.assertFalse(deletion.cleanup_once())
            finally:deletion.Session=old;deletion.ROOT=old_root


@pytest.mark.parametrize('parse_fails',[False,True])
def test_parse_cannot_restore_source_after_concurrent_sku_delete(client,tmp_path,monkeypatch,parse_fails):
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    (tmp_path/'source.txt').write_bytes(b'test')
    with db.Session.begin() as session:
        session.add_all([
            db.Record(id='sku',workspace='one',kind='sku',data={}),
            db.Record(id='source',workspace='one',kind='source',data={'sku_id':'sku','name':'source.txt',
                'object_key':'source.txt','sha256':hashlib.sha256(b'test').hexdigest()}),
        ])
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}

    def parse(*_):
        assert client.delete('/api/v1/skus/sku',headers=headers).status_code==202
        if parse_fails:
            raise ValueError('PARSE_FAILED')
        return [{'text':'late completion'}]

    monkeypatch.setattr(parsing,'parse_isolated',parse)
    assert client.post('/api/v1/sources/source/parse',headers=headers).status_code==404
    with db.Session.begin() as session:
        source=session.get(db.Record,'source')
        assert source.data['deleting'] and 'locators' not in source.data
        source.data={key:value for key,value in source.data.items() if key!='deleting'}
    assert client.get('/api/v1/sources/source/download').status_code==404
    assert (tmp_path/'source.txt').exists()


def test_sku_delete_fences_related_tasks_and_keeps_reservations(client):
    with db.Session.begin() as session:
        session.add_all([
            db.Record(id='sku',workspace='one',kind='sku',data={}),
            db.Record(id='work',workspace='one',kind='work',data={'sku_id':'sku'}),
            db.Record(id='request',workspace='one',kind='creation_request',data={'sku_id':'sku'}),
            db.Record(id='source',workspace='one',kind='source',data={'sku_id':'sku','object_key':'private-key','locators':[{'text':'private-text'}]}),
            db.Record(id='result',workspace='one',kind='result_revision',data={'work_id':'work'}),
            db.Record(id='asset',workspace='one',kind='asset',data={'work_id':'work'}),
            db.Record(id='export',workspace='one',kind='export',data={'work_id':'work'}),
            db.Record(id='foreign-sku',workspace='other',kind='sku',data={}),
            db.Record(id='foreign-asset',workspace='other',kind='asset',data={'work_id':'work'}),
            Budget(id='budget',workspace='one',cap=10,reserved=2,settled=0),
            Task(id='running',workspace='one',phase='creation_run',state='running',fencing_token=4,payload={'request_id':'request'}),
            Task(id='repair',workspace='one',phase='repair_asset',state='queued',fencing_token=0,payload={'work_id':'work'}),
            Task(id='edit',workspace='one',phase='edit_run',state='paused',fencing_token=2,payload={'work_id':'work'}),
            Task(id='foreign',workspace='other',phase='edit_run',state='queued',fencing_token=0,payload={'work_id':'work'}),
        ])
        session.flush()
        session.add_all([
            CallReservation(id='charge',budget_id='budget',workspace='one',request_hash='hash',upper_bound=2,remaining=2,finalized=False),
            ExternalCall(id='charge',intent_key='intent',task_id='running',state='external_unknown',request_hash='hash',workspace='one'),
        ])
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    preview=client.get('/api/v1/skus/sku/deletion-preview')
    assert preview.status_code==200 and preview.headers['cache-control']=='private, no-store'
    assert preview.json()=={
        'sku_id':'sku','counts':{'source':1,'work':1,'result':1,'asset':1,'export':1,'task':3},
        'active_tasks':3,'open_fee_reservations':1,'unknown_fee_reservations':1,
        'retention':{'access':'revoke_on_delete','registered_local_files':'async_cleanup','provider_files':'verification_required',
            'fees_and_audit':'retained','unsettled_fees':'reservation_retained'},
    }
    assert client.get('/api/v1/skus/foreign-sku/deletion-preview').status_code==404
    with db.Session() as session:
        assert session.get(Task,'running').state=='running'
        assert 'deleting' not in session.get(db.Record,'source').data
    assert client.delete('/api/v1/skus/sku',headers={'X-CSRF-Token':login.json()['csrf_token']}).status_code==202
    assert client.get('/api/v1/skus/sku/deletion-preview').status_code==404
    with db.Session() as session:
        for identifier,token in [('running',5),('repair',1),('edit',3)]:
            task=session.get(Task,identifier)
            assert (task.state,task.fencing_token)==('canceled',token)
        assert session.get(Task,'foreign').state=='queued'
        for identifier in ('source','work','result','asset','export'):
            assert session.get(db.Record,identifier).data['deleting'] is True
        assert 'deleting' not in session.get(db.Record,'foreign-asset').data
        assert session.get(Budget,'budget').reserved==2
        assert session.get(CallReservation,'charge').remaining==2
        assert session.get(ExternalCall,'charge').state=='external_unknown'


def test_worker_loop_reaches_pending_physical_cleanup(client,tmp_path,monkeypatch):
    from marketing_worker.runner import run
    monkeypatch.setattr(deletion,'ROOT',tmp_path)
    (tmp_path/'media').write_bytes(b'private')
    with db.Session.begin() as session:
        session.add_all([
            db.Record(id='pending',workspace='one',kind='deletion',data={'sku_id':'sku','physical_cleanup':'pending'}),
            db.Record(id='source',workspace='one',kind='source',data={'sku_id':'sku','object_key':'media'}),
        ])
    stop=Event()

    class IdleRepository:
        sessions=db.Session
        def recover_expired(self):
            pass
        def claim(self,owner):
            stop.set()
            return None

    run(IdleRepository(),'cleanup-test',stop)
    assert not (tmp_path/'media').exists()
    with db.Session() as session:
        assert session.get(db.Record,'pending').data['physical_cleanup']=='completed'


def test_cleanup_resumes_bounded_batches_and_keeps_other_workspace(client,tmp_path,monkeypatch):
    monkeypatch.setattr(deletion,'ROOT',tmp_path)
    for name in ('first','second','foreign'):
        (tmp_path/name).write_bytes(b'synthetic')
    with db.Session.begin() as session:
        session.add(db.Record(id='pending',workspace='one',kind='deletion',data={'sku_id':'sku','physical_cleanup':'pending'}))
        for name,workspace in [('first','one'),('second','one'),('foreign','other')]:
            session.add(db.Record(id=name,workspace=workspace,kind='source',data={'sku_id':'sku','object_key':name}))
    assert deletion.cleanup_once(batch_size=1)
    assert not (tmp_path/'first').exists() and (tmp_path/'second').exists()
    with db.Session() as session:
        assert session.get(db.Record,'pending').data['physical_cleanup']=='pending'
    assert deletion.cleanup_once(batch_size=1)
    assert not (tmp_path/'second').exists() and (tmp_path/'foreign').is_file()
    with db.Session() as session:
        assert session.get(db.Record,'pending').data['state']=='pending_external_verification'
    assert not deletion.cleanup_once(batch_size=1)
