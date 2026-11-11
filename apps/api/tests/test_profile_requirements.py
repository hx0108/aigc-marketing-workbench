from test_api_boundaries import client,source_directory,sign_in,upload_synthetic_product

def test_missing_specification_and_image_keeps_profile_draft(client):
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'SKU-1'},headers=headers).json()
    profile=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{}},headers=headers).json()
    response=client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=headers)
    assert response.status_code==422
    assert set(response.json()['detail']['missing_fields'])=={'specification_or_single_spec_confirmation','current_product_image'}
    assert client.get('/api/v1/profiles/'+profile['id']).json()['status']=='draft'

def test_explicit_single_spec_and_image_can_confirm_with_provenance(client,source_directory,monkeypatch):
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'SKU-1','single_spec_confirmed':True},headers=headers).json()
    image_id=upload_synthetic_product(client,headers,sku['id'])
    profile=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{},'source_ids':[image_id]},headers=headers).json()
    response=client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=headers)
    assert response.status_code==200
    assert response.json()['facts']['name']=='耳机'
    assert response.json()['fact_sources']['name']['origin']=='catalog'
    assert response.json()['fact_sources']['name']['confirmed_at']

def test_conflicting_identity_is_not_confirmed(client,source_directory,monkeypatch):
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'SKU-1','specification':'白色'},headers=headers).json()
    image_id=upload_synthetic_product(client,headers,sku['id'])
    profile=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{'name':'吹风机'},'source_ids':[image_id]},headers=headers).json()
    response=client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=headers)
    assert response.status_code==422
    assert response.json()['detail']['code']=='FACT_CONFLICT'
