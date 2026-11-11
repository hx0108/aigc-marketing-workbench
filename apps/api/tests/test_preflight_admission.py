from sqlalchemy import select
from app import db
from app.db import Record
from app.execution import Task
from test_core import client


def test_direct_run_cannot_bypass_failed_material_preflight(client):
    with db.Session.begin() as session:
        session.add(Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed'}))
        session.add(Record(id='request',workspace='one',kind='creation_request',data={
            'profile_id':'profile','status':'blocked','blockers':[{'code':'SOURCE_SELECTION_REQUIRED'}]}))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    result=client.post('/api/v1/creation-requests/request/runs',json={'authorized':True},headers={
        'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'blocked-run'})
    assert result.status_code==409
    assert result.json()['detail']['code']=='PREFLIGHT_BLOCKED'
    assert result.json()['detail']['blockers']==[{'code':'SOURCE_SELECTION_REQUIRED'}]
    with db.Session() as session:
        assert session.scalar(select(Task)) is None
        assert session.scalar(select(Record).where(Record.kind=='processing_consent')) is None


def test_changed_provider_parameters_require_new_quote(client,monkeypatch):
    from marketing_worker import business
    approved={'providers':{'video':'same-model'},'provider_parameters':{'video':{'resolution':'480p'}},'price_version':'v1','budget_id':'b','consent_version':'v1','bounds':{'dynamic':'6'}}
    monkeypatch.setattr(business,'readiness',lambda:[])
    monkeypatch.setattr(business,'authorization_snapshot',lambda *args:{**approved,'provider_parameters':{'video':{'resolution':'1080p'}}})
    with db.Session.begin() as session:
        session.add(Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed'}))
        session.add(Record(id='image',workspace='one',kind='source',data={'type':'image'}))
        session.add(Record(id='mask',workspace='one',kind='source',data={'type':'image'}))
        session.add(Record(id='request',workspace='one',kind='creation_request',data={
            'profile_id':'profile','status':'ready','blockers':[],'quote':{**approved,'cost_upper_bound':'10'},
            'profile_snapshot':{'facts':{'name':'synthetic'},'source_ids':['image','mask'],'source_selection':{'product':{'source_id':'image'},'mask':{'source_id':'mask'}}}}))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    result=client.post('/api/v1/creation-requests/request/runs',json={'authorized':True},headers={
        'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'changed-parameters'})
    assert result.status_code==409
    assert result.json()['detail']['code']=='AUTHORIZATION_SCOPE_CHANGED'
    with db.Session() as session:
        assert session.scalar(select(Task)) is None
import pytest
from decimal import Decimal

@pytest.mark.parametrize('limit,expected', [('4','4'),('20','7')])
def test_creation_budget_cannot_exceed_user_or_ledger(client,monkeypatch,limit,expected):
    from marketing_worker import business
    from app import profile_validation, pricing
    from app.execution import Budget
    monkeypatch.setattr(profile_validation,'validate_profile',lambda *args:None)
    monkeypatch.setattr(business,'readiness',lambda:[])
    monkeypatch.setattr(business,'authorization_snapshot',lambda *args:{'budget_id':'private-budget'})
    monkeypatch.setattr(pricing,'creation_reservation_floor',lambda *args:Decimal('2'))
    with db.Session.begin() as s:
        s.add(Record(id='p',workspace='one',kind='profile',data={'status':'confirmed','sku_id':'s','source_selection':{'product':{},'mask':{}}}))
        s.add(Budget(id='private-budget',workspace='one',cap=Decimal('10'),reserved=Decimal('2'),settled=Decimal('1')))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    r=client.post('/api/v1/creation-requests',json={'profile_id':'p','platforms':['douyin'],'duration_seconds':5,'budget_limit':limit},headers={'X-CSRF-Token':login.json()['csrf_token']})
    assert r.status_code==201
    assert Decimal(r.json()['quote']['cost_upper_bound'])==Decimal(expected)

@pytest.mark.parametrize('reason,expected', [('unauthorized','WORKSPACE_AUTHORIZATION_REQUIRED'),('missing','WORKSPACE_BUDGET_REQUIRED'),('price','PRICE_CONFIGURATION_REQUIRED')])
def test_creation_blockers_do_not_disclose_configuration(client,monkeypatch,reason,expected):
    from marketing_worker import business
    from app import profile_validation
    monkeypatch.setattr(profile_validation,'validate_profile',lambda *args:None)
    monkeypatch.setattr(business,'readiness',lambda:['VIDEO_PRICE_VERIFICATION_REQUIRED'] if reason=='price' else [])
    def snapshot(*args):
        if reason=='unauthorized':raise ValueError('pipeline_not_authorized')
        return {'budget_id':'private-budget'}
    monkeypatch.setattr(business,'authorization_snapshot',snapshot)
    with db.Session.begin() as s:
        s.add(Record(id='p',workspace='one',kind='profile',data={'status':'confirmed','sku_id':'s','source_selection':{'product':{},'mask':{}}}))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    r=client.post('/api/v1/creation-requests',json={'profile_id':'p','platforms':['douyin'],'duration_seconds':5},headers={'X-CSRF-Token':login.json()['csrf_token']})
    assert r.status_code==201
    assert r.json()['blockers'][0]['code']==expected
    assert r.json()['quote'] is None
    assert 'private-budget' not in r.text

@pytest.mark.parametrize('blockers,enabled', [([],True),(['SERVER_PIPELINE_CONFIGURATION_REQUIRED'],False)])
def test_health_reports_generation_configuration_without_details(client,monkeypatch,blockers,enabled):
    from marketing_worker import business
    monkeypatch.setattr(business,'readiness',lambda:blockers)
    assert client.get('/health').json()=={'status':'ok','real_generation_enabled':enabled}
