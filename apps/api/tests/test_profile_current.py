from test_api_boundaries import client,source_directory,sign_in,upload_synthetic_product
from app import db,sources
from app.db import Record

def test_current_profile_is_explicit_confirmation_not_uuid_order(client,source_directory,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'P1','specification':'白色'},headers=headers).json()
    image=upload_synthetic_product(client,headers,sku['id'])
    profiles=[]
    for note in ('first','second'):
        profile=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{'note':note},'source_ids':[image]},headers=headers).json()
        assert client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=headers).status_code==200
        profiles.append(profile)
    result=client.get('/api/v1/skus/'+sku['id']+'/profiles').json()
    assert result['current_profile_id']==profiles[-1]['id']
    assert result['selection_required'] is False
    assert all(item['created_at_known'] for item in result['items'])

def test_legacy_confirmed_profile_has_no_invented_current_selection(client):
    headers=sign_in(client)
    with db.Session() as session:
        session.add_all([Record(id='legacy-sku',workspace='one',kind='sku',data={'name':'legacy'}),Record(id='legacy-profile',workspace='one',kind='profile',data={'sku_id':'legacy-sku','status':'confirmed'})]);session.commit()
        profile=session.get(Record,'legacy-profile');profile.created_at=None;session.commit()
    result=client.get('/api/v1/skus/legacy-sku/profiles').json()
    assert result['current_profile_id'] is None
    assert result['selection_required'] is True
    assert result['items'][0]['created_at'] is None
    assert result['items'][0]['created_at_known'] is False
