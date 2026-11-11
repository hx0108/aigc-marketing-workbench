from test_api_boundaries import client,source_directory,sign_in
from app import sources,parsing

def test_blank_document_is_not_reported_as_parse_success(client,source_directory,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'test','merchant_sku':'blank'},headers=headers).json()
    source=client.post('/api/v1/skus/'+sku['id']+'/sources',content=b' \n ',headers={**headers,'X-Filename':'blank.txt','X-Rights-Confirmed':'true'}).json()
    result=client.post('/api/v1/sources/'+source['id']+'/parse',headers=headers)
    assert result.status_code==200
    assert result.json()['parse_status']=='failed'
    assert result.json()['locators']==[]

def test_ocr_candidate_cannot_be_promoted_to_confirmed_parse(client,source_directory,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'test','merchant_sku':'ocr'},headers=headers).json()
    source=client.post('/api/v1/skus/'+sku['id']+'/sources',content=b'test',headers={**headers,'X-Filename':'fixture.txt','X-Rights-Confirmed':'true'}).json()
    monkeypatch.setattr(parsing,'parse_isolated',lambda *args:[{'page':2,'text':'12345','status':'ocr_candidate','requires_review':True,'confidence':None}])
    result=client.post('/api/v1/sources/'+source['id']+'/parse',headers=headers).json()
    assert result['parse_status']=='awaiting_confirmation'
    assert result['locators'][0]['confidence'] is None
    assert result['locators'][0]['page']==2
