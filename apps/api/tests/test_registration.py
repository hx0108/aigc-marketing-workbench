from concurrent.futures import ThreadPoolExecutor
import hashlib
from threading import Barrier

from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import auth, auth_limits, db, sources
from app.execution import Budget, ExternalCall, Task
from app.ledger import CallReservation
from test_core import client


def test_registration_issues_session_without_inheriting_configured_budget(client,tmp_path,monkeypatch):
    from marketing_worker import business

    with db.Session.begin() as session:
        session.add(Budget(id='global-owner-budget',workspace='one',cap=10,reserved=0,settled=0))
        session.add(db.Record(id='private-other-product',workspace='one',kind='sku',data={'name':'private'}))
    signup=client.post('/api/v1/accounts',json={'username':'商家二','password':'fixture-only-pass'})
    assert signup.status_code==201
    assert 'HttpOnly' in signup.headers['set-cookie'] and 'SameSite=strict' in signup.headers['set-cookie']
    assert client.get('/api/v1/sessions/current').json()==signup.json()
    assert client.get('/api/v1/skus/private-other-product').status_code==404
    assert client.get('/api/v1/skus').json()['items']==[]
    headers={'X-CSRF-Token':signup.json()['csrf_token']}
    assert client.post('/api/v1/skus',json={'name':'商品','merchant_sku':'SKU'}).status_code==403

    monkeypatch.setattr(sources,'ROOT',tmp_path)
    fixture=tmp_path/'fixture.png'
    fixture.write_bytes(b'synthetic profile image reference')
    digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
    with db.Session.begin() as session:
        account=session.get(auth.Account,'商家二')
        workspace=account.workspace
        assert workspace!='one' and account.password_hash!='fixture-only-pass'
        session.add_all([
            db.Record(id='own-sku',workspace=workspace,kind='sku',data={'name':'商品','merchant_sku':'SKU','specification':'单规格'}),
            db.Record(id='own-source',workspace=workspace,kind='source',data={'sku_id':'own-sku','type':'image',
                'object_key':fixture.name,'sha256':digest,'rights_confirmed':True}),
            db.Record(id='own-profile',workspace=workspace,kind='profile',data={'sku_id':'own-sku','status':'confirmed',
                'source_ids':['own-source'],'facts':{'name':'商品'},'fact_sources':{'name':{'source_id':'own-source'}},
                'source_selection':{'product':'own-source','mask':'own-source'}}),
        ])
    monkeypatch.setattr(business,'readiness',lambda:[])
    monkeypatch.setattr(business,'authorization_snapshot',lambda *_:{'budget_id':'global-owner-budget'})
    preflight=client.post('/api/v1/creation-requests',headers=headers,json={
        'profile_id':'own-profile','platforms':['douyin'],'duration_seconds':6,
    })
    assert preflight.status_code==201 and preflight.json()['status']=='blocked' and preflight.json()['quote'] is None
    run=client.post(f"/api/v1/creation-requests/{preflight.json()['id']}/runs",
        headers={**headers,'Idempotency-Key':'registration-no-spend'},json={'authorized':True})
    assert run.status_code==409 and run.json()['detail']['code']=='PREFLIGHT_BLOCKED'
    with db.Session() as session:
        assert session.get(Budget,'global-owner-budget').reserved==0
        for model in (Task,ExternalCall,CallReservation):
            assert session.scalar(select(func.count()).select_from(model))==0
    assert client.delete('/api/v1/sessions/current',headers=headers).status_code==204
    assert client.get('/api/v1/sessions/current').status_code==401
    assert client.post('/api/v1/sessions',json={'username':'商家二','password':'fixture-only-pass'}).status_code==200


def test_registration_failure_keeps_account_and_session_tables_unchanged(client):
    for payload,status in [
        ({'username':'tester','password':'fixture-only-pass'},409),
        ({'username':' short ','password':'fixture-only-pass'},422),
        ({'username':'new','password':'short'},422),
        ({'username':'new','password':'fixture-only-pass','workspace':'one'},422),
    ]:
        response=client.post('/api/v1/accounts',json=payload)
        assert response.status_code==status and 'set-cookie' not in response.headers
    with db.Session() as session:
        assert session.scalar(select(func.count()).select_from(auth.Account))==1
        assert session.scalar(select(func.count()).select_from(auth.LoginSession))==0


def test_registration_is_limited_before_password_hashing(client,monkeypatch):
    seen=[]

    def hash_password(password):
        seen.append(password)
        return 'fixture'

    monkeypatch.setattr(auth,'password_hash',hash_password)
    for index in range(5):
        assert client.post('/api/v1/accounts',json={'username':f'person-{index}','password':'fixture-only-pass'}).status_code==201
    limited=client.post('/api/v1/accounts',json={'username':'sixth','password':'fixture-only-pass'})
    assert limited.status_code==429 and int(limited.headers['retry-after'])>=1
    assert len(seen)==5


def test_concurrent_registration_has_only_one_account_and_session(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+(tmp_path/'registration.sqlite').as_posix())
    factory=sessionmaker(engine)
    db.Base.metadata.create_all(engine)
    monkeypatch.setattr(auth,'Session',factory)
    monkeypatch.setattr(auth,'consume',lambda scope,identity:auth_limits.consume(scope,identity,sessions=factory))
    barrier=Barrier(2)

    def register(index):
        request=Request({'type':'http','client':(f'127.0.0.{index}',1234),'scheme':'https',
            'server':('workbench.test',443),'path':'/api/v1/accounts','headers':[]})
        response=Response()
        barrier.wait(timeout=5)
        try:
            result=auth.register('one-username','fixture-only-pass',request,response)
            assert result['csrf_token'] and 'Secure' in response.headers['set-cookie']
            return 201
        except HTTPException as error:
            assert 'set-cookie' not in response.headers
            return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(register,(1,2)))==[201,409]
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(auth.Account))==1
            assert session.scalar(select(func.count()).select_from(auth.LoginSession))==1
    finally:
        engine.dispose()


def test_login_and_registration_reject_cross_origin_but_accept_same_origin_and_cli(client):
    for endpoint,username in (('/api/v1/accounts','new'),('/api/v1/sessions','tester')):
        payload={'username':username,'password':'test-password-123'}
        for origin in ('https://elsewhere.test','null','https://testserver','http://testserver:1234','http://testserver:0'):
            rejected=client.post(endpoint,json=payload,headers={'Origin':origin})
            assert rejected.status_code==403 and rejected.json()['detail']['code']=='ORIGIN_REJECTED'
            assert 'set-cookie' not in rejected.headers and payload['password'] not in rejected.text
        accepted=client.post(endpoint,json=payload,headers={'Origin':'http://testserver:80'})
        assert accepted.status_code in (200,201)
    cli=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    assert cli.status_code==200
