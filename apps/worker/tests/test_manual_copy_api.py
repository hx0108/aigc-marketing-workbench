from decimal import Decimal

import pytest

from app import db
from app.db import Record
from app.execution import Budget, ExternalCall, Task
from app.ledger import prepare
from marketing_worker.pipeline import Pipeline
from test_core import client


def test_manual_copy_keeps_existing_unknown_reservation_and_skips_text_provider(client):
    request = {'platforms':['douyin'],'duration_seconds':10,
               'facts':[{'id':'name','validity':'active','value':'商品'}]}
    with db.Session.begin() as session:
        session.add_all([
            Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed'}),
            Record(id='task:copy',workspace='one',kind='task_step',data={'task_id':'task','state':'external_unknown'}),
            Task(id='task',workspace='one',phase='creation_run',state='external_unknown',
                 payload={'profile_id':'profile','request':request}),
            Budget(id='cap',workspace='one',cap=Decimal(10),reserved=0,settled=0),
            ExternalCall(id='task:copy',intent_key='task:copy',task_id='task',state='external_unknown',request_hash='copy'),
        ])
        session.flush()
        prepare(session,'cap','task:copy','copy','0.10')
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    detail=client.get('/api/v1/tasks/task').json()
    assert 'manual_copy' in detail['next_actions']
    draft={'title':'认识商品','body':'查看外观','poster_title':'商品展示',
           'selling_points':['查看细节'],'shots':['了解商品','看看外观','请核对规格']}
    action={'action':'manual_copy','authorized':True,'manual_copy':{'douyin':draft}}
    path='/api/v1/tasks/task/actions'
    assert client.post(path,json={**action,'authorized':False},headers=headers).status_code==409
    unsupported={**draft,'body':'续航100小时'}
    assert client.post(path,json={**action,'manual_copy':{'douyin':unsupported}},headers=headers).status_code==422
    result=client.post(path,json=action,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['execution_state']=='queued'
    assert Decimal(result.json()['reserved_cost'])==Decimal('0.10')
    assert result.json()['unknown_cost_flag'] is True
    assert client.post(path,json=action,headers=headers).status_code==409
    with db.Session() as session:
        payload=session.get(Task,'task').payload['request']
        assert session.get(ExternalCall,'task:copy').state=='external_unknown'

    class StopAfterCopy(Pipeline):
        def step(self, task_id, key, kind, payload):
            assert (key,kind)==('image/white','product_image')
            raise RuntimeError('copy bypass verified')

    with pytest.raises(RuntimeError,match='copy bypass verified'):
        StopAfterCopy(None,None).execute('task',payload)
