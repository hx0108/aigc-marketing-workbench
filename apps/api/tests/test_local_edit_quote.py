import pytest
from app import db
from app.db import Record
from marketing_worker import business
from test_core import client


@pytest.mark.parametrize('changes', [{'poster_title':'New poster'}, {'subtitle_style':'large'}, {'music':'music'}])
def test_local_media_quote_without_provider_configuration(client, monkeypatch, changes):
    monkeypatch.setattr(business, '_configuration', None)
    with db.Session.begin() as session:
        session.add_all([
            Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','facts':{}}),
            Record(id='music',workspace='one',kind='source',data={'sku_id':'sku','type':'audio','rights_confirmed':True}),
            Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','platforms':['douyin'],'current_result':'result'}),
            Record(id='result',workspace='one',kind='result_revision',data={'work_id':'work','copy':{'douyin':{'shots':[]}}}),
        ])
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    saved=client.patch('/api/v1/works/work/draft',json={'expected_revision':1,'changes':changes},headers=headers)
    assert saved.status_code==200,saved.text
    response=client.post('/api/v1/works/work/change-quotes',headers=headers)
    assert response.status_code==200,response.text
    quote=response.json()
    assert quote['executable'] is True,quote
    assert str(quote['cost_upper_bound'])=='0'
    assert quote['execution_mode']=='local_only'
    assert quote['quote_id']
    action={'expected_revision':saved.json()['revision'],'quote_id':quote['quote_id'],'authorized':True}
    stale=client.post('/api/v1/works/work/apply',json={**action,'expected_revision':1},headers={**headers,'Idempotency-Key':'local-stale'})
    assert stale.status_code==409
    applied=client.post('/api/v1/works/work/apply',json=action,headers={**headers,'Idempotency-Key':'local'})
    assert applied.status_code==200,applied.text
    from app.execution import Task
    with db.Session() as session:
        task=session.get(Task,applied.json()['task_id'])
        consent=session.get(Record,task.payload['consent_id'])
        assert task.payload['execution_mode']=='local_only'
        assert consent.data['cost_upper_bound']==0
        assert 'providers' not in consent.data and 'budget_id' not in consent.data


def test_paid_voice_edit_still_requires_price_configuration(client,monkeypatch):
    monkeypatch.setattr(business,'_configuration',None)
    with db.Session.begin() as session:
        session.add(Record(id='work',workspace='one',kind='work',data={'platforms':['douyin'],'draft':{'voice':'Cherry'}}))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    quote=client.post('/api/v1/works/work/change-quotes',headers={'X-CSRF-Token':login.json()['csrf_token']}).json()
    assert quote['executable'] is False
    assert quote['cost_upper_bound'] is None
    assert quote['blockers']==['PRICE_NOT_CONFIGURED']
