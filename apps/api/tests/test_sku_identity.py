from test_api_boundaries import client,sign_in
from app import db
from app.auth import Account,password_hash

def test_merchant_sku_unique_only_within_workspace(client):
    headers=sign_in(client)
    first=client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'SKU-A'},headers=headers)
    assert first.status_code==201
    duplicate=client.post('/api/v1/skus',json={'name':'另一个商品','model':'SKU-A'},headers=headers)
    assert duplicate.status_code==409
    assert duplicate.json()['detail']['code']=='SKU_ALREADY_EXISTS'
    with db.Session() as session:
        session.add(Account(username='other',workspace='two',password_hash=password_hash('test-password-123')));session.commit()
    client.delete('/api/v1/sessions/current',headers=headers)
    other=sign_in(client,'other')
    assert client.post('/api/v1/skus',json={'name':'耳机','merchant_sku':'SKU-A'},headers=other).status_code==201
