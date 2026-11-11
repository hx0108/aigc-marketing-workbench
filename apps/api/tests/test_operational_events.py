import json
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.errors import install
from marketing_worker import runner


def test_api_events_log_route_templates_and_redact_request_data(capsys):
    app=FastAPI()
    install(app)

    @app.post('/api/v1/assets/{asset_id}')
    def asset(asset_id:str,body:dict):
        if body.get('fail'):
            raise ValueError('secret exception text')
        return {'ok':True}

    @app.post('/api/v1/export-packages')
    def rejected_export():
        raise HTTPException(409,'private export path')

    @app.get('/restricted')
    def restricted():
        raise HTTPException(401,'private identity')

    with TestClient(app) as client:
        data={'name':'Synthetic PII','password':'Synthetic body password'}
        headers={'Authorization':'Bearer synthetic-token','Cookie':'session=synthetic-cookie','X-Request-ID':'caller-controlled'}
        first=client.post('/api/v1/assets/private-asset-id?query=private-query',json=data,headers=headers)
        failed=client.post('/api/v1/assets/private-asset-id?query=private-query',json={**data,'fail':True},headers=headers)
        exported=client.post('/api/v1/export-packages')
        missing=client.get('/missing/private-asset-id')
        rejected=client.get('/restricted')
    assert [reply.status_code for reply in (first,failed,exported,missing,rejected)]==[200,500,409,404,401]
    assert failed.json()['detail']=='INTERNAL_ERROR'
    raw=capsys.readouterr().err
    for secret in ('private-asset-id','private-query','Synthetic PII','Synthetic body password','synthetic-token',
                   'synthetic-cookie','caller-controlled','secret exception text','private export path','private identity'):
        assert secret not in raw
    completed,exception,export,not_found,access_rejected=map(json.loads,raw.splitlines())
    assert completed['route']=='/api/v1/assets/{asset_id}' and completed['event']=='request_completed'
    assert completed['request_id']==first.headers['X-Request-ID'] and UUID(completed['request_id'])
    assert completed['duration_ms']>=0
    assert exception['event']=='request_failed' and exception['error_type']=='ValueError'
    assert exception['request_id']==failed.json()['request_id']==failed.headers['X-Request-ID']
    assert export['event']=='export_failed' and export['operation']=='export'
    assert not_found['event']=='not_found' and not_found['route'] is None
    assert access_rejected['event']=='access_rejected'


def test_worker_events_expose_status_and_safe_code_without_job_input(capsys,monkeypatch):
    class SecretError(RuntimeError):
        code='potentially-sensitive-code'

    class Repository:
        task_id='private-job-id'

        def claim(self,owner):
            return {'id':self.task_id,'fencing_token':1,'kind':'fixture','payload':{'subject':'private-job-subject'}}

        def canceled(self,*args):return False
        def complete(self,*args):return True
        def fail(self,*args):return True

    def fail(subject):
        raise SecretError(subject)

    monkeypatch.setitem(runner.HANDLERS,'fixture',lambda **_:{'status':'completed'})
    runner.run_once(Repository(),'private-owner')
    monkeypatch.setitem(runner.HANDLERS,'fixture',fail)
    runner.run_once(Repository(),'private-owner')

    raw=capsys.readouterr().err
    assert all(value not in raw for value in ('private-job-id','private-job-subject','private-owner','potentially-sensitive-code'))
    events=list(map(json.loads,raw.splitlines()))
    assert [event['state'] for event in events]==['running','succeeded','running','failed']
    assert all(event['event']=='worker_task_state' and event['task_ref']==events[0]['task_ref'] for event in events)
    assert events[-1]['error_code']=='task_failed' and events[-1]['error_type']=='SecretError'
