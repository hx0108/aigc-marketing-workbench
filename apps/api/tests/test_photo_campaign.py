import io

import pytest
from PIL import Image
from sqlalchemy import func, select

from app import db, sources
from app.db import Record
from app.execution import ExternalCall, Task
from app.job_repository import JobRepository
from app.ledger import CallReservation
from test_core import client


@pytest.fixture
def campaign(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)
    sign_in = client.post('/api/v1/sessions', json={'username':'tester', 'password':'test-password-123'})
    headers = {'X-CSRF-Token':sign_in.json()['csrf_token']}
    sku = client.post('/api/v1/skus', json={'name':'概念耳机', 'model':'EP', 'color':'白色'}, headers=headers).json()
    pictures = []
    for color in ('white', 'red', 'blue'):
        image = io.BytesIO()
        Image.new('RGB', (32, 40), color).save(image, format='JPEG')
        upload = client.post(f"/api/v1/skus/{sku['id']}/sources", content=image.getvalue(),
            headers={**headers,'X-Filename':color+'.jpg','X-Rights-Confirmed':'true'})
        assert upload.status_code == 201
        pictures.append(upload.json())
    with db.Session.begin() as session:
        mask = session.get(Record, pictures[-1]['id'])
        mask.data = {**mask.data, 'is_subject_mask':True}
    profile = client.post(f"/api/v1/skus/{sku['id']}/profiles",
        json={'facts':{}, 'source_ids':[photo['id'] for photo in pictures]}, headers=headers).json()
    assert client.post(f"/api/v1/profiles/{profile['id']}/confirm", headers=headers).status_code == 200
    body = {'creative_mode':'photo_campaign', 'profile_id':profile['id'], 'platforms':['douyin','xiaohongshu'],
            'duration_seconds':15, 'wear_source_id':pictures[1]['id']}
    return headers, body, pictures


def test_photo_run_freezes_only_real_photos_without_a_mask_or_paid_service(client, campaign, monkeypatch):
    from marketing_worker import business
    headers, body, pictures = campaign
    monkeypatch.setattr(business, 'readiness', lambda: pytest.fail('A local run must not query paid providers'))
    creation = client.post('/api/v1/creation-requests', json=body, headers=headers)
    assert creation.status_code == 201
    data = creation.json()
    assert data['status'] == 'ready' and data['quote']['cost_upper_bound'] == 0
    assert [item['source_id'] for item in data['photo_sources']] == [p['id'] for p in pictures[:2]]
    assert all(set(item) == {'source_id','sha256','revision'} for item in data['photo_sources'])
    assert set(data['storyboards']) == {'douyin', 'xiaohongshu'}
    for shots in data['storyboards'].values():
        assert [shot['view'] for shot in shots] == ['scene', 'packshot', pictures[0]['id'], 'end']
        assert round(sum(shot['seconds'] for shot in shots), 2) == body['duration_seconds']
    assert data['storyboards']['douyin'][0]['seconds'] != data['storyboards']['xiaohongshu'][0]['seconds']
    with db.Session() as session:
        for model in (Task, ExternalCall, CallReservation):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    route = f"/api/v1/creation-requests/{data['id']}/runs"
    authorization = {**headers, 'Idempotency-Key':'same-click'}
    assert client.post(route, json={'authorized':False}, headers=authorization).status_code == 409
    first = client.post(route, json={'authorized':True}, headers=authorization)
    assert first.status_code == 202
    assert client.post(route, json={'authorized':True}, headers=authorization).json() == first.json()
    from app.photo_campaign import verify_campaign_job
    job = JobRepository(db.Session).claim('isolated-photo-worker')
    with db.Session() as session:
        paths = verify_campaign_job(session, job)
        assert [p.name for p in paths] == [p['object_key'] for p in pictures[:2]]
        consent = session.get(Record, job['payload']['request']['consent_id'])
        assert consent.data['contract_version'] == 'photo-campaign-v1'
        assert consent.data['cost_upper_bound'] == 0
        assert session.scalar(select(func.count()).select_from(Task)) == 1
        for model in (ExternalCall, CallReservation):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        revoked = session.get(Record, pictures[1]['id'])
        revoked.data = {**revoked.data, 'rights_confirmed':False}
        session.commit()
        with pytest.raises(ValueError, match='PHOTO_SOURCE_CHANGED'):
            verify_campaign_job(session, job)


def test_different_card_or_unverified_headline_cannot_enter_photo_run(client, campaign):
    headers, body, pictures = campaign
    for change, code in [
        ({'wear_source_id':pictures[-1]['id']}, 'WEAR_PHOTO_REQUIRED'),
        ({'wear_source_id':'unrelated-source'}, 'WEAR_PHOTO_REQUIRED'),
        ({'brief':'连续播放100小时'}, 'PHOTO_HEADLINE_INVALID'),
        ({'brief':'字'*33}, 'PHOTO_HEADLINE_INVALID'),
        ({'duration_seconds':31}, 'PHOTO_DURATION_INVALID'),
    ]:
        answer = client.post('/api/v1/creation-requests', json={**body, **change}, headers=headers)
        assert answer.status_code == 422, answer.text
        assert answer.json()['detail']['code'] == code
    assert client.post('/api/v1/creation-requests', json={**body,'creative_mode':'provider'},
        headers=headers).status_code == 422
    generic = client.post('/api/v1/creation-requests', json={**body,'wear_source_id':None}, headers=headers)
    assert generic.json()['status'] == 'ready'
    with db.Session.begin() as session:
        row = session.get(Record, pictures[0]['id'])
        row.revision += 1
    run = client.post(f"/api/v1/creation-requests/{generic.json()['id']}/runs", json={'authorized':True},
        headers={**headers,'Idempotency-Key':'expired-photos'})
    assert run.status_code == 409 and run.json()['detail']['code'] == 'PHOTO_SOURCE_CHANGED'
    assert client.get('/api/v1/tasks').json()['items'] == []


def test_photo_edits_recheck_originals_without_requiring_a_cutout(client, campaign):
    from marketing_worker.source_resolver import resolve_sources
    headers, body, pictures = campaign
    creation = client.post('/api/v1/creation-requests', json=body, headers=headers).json()
    response = client.post(f"/api/v1/creation-requests/{creation['id']}/runs", json={'authorized':True},
                           headers={**headers, 'Idempotency-Key':'photo-for-edit'})
    assert response.status_code == 202
    with db.Session() as session:
        work = session.get(Record, response.json()['work_id'])
        edit = {'workspace':work.workspace, 'kind':'edit_run', 'payload':{'work_id':work.id}}
    assert resolve_sources(db.Session, edit, sources.ROOT, {}) == {}
    with db.Session.begin() as session:
        photo = session.get(Record, pictures[0]['id'])
        photo.data = {**photo.data, 'rights_confirmed':False}
    with pytest.raises(ValueError, match='PHOTO_SOURCE_CHANGED'):
        resolve_sources(db.Session, edit, sources.ROOT, {})
