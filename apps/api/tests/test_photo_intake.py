from io import BytesIO

from PIL import Image, ImageDraw

from app import db, sources
from app.db import Record
from app.product_matte import extract_matte
from test_api_boundaries import client, sign_in


def product_photo(size=(240, 320)):
    image = Image.new('RGB', size, '#e2ddd0')
    draw = ImageDraw.Draw(image)
    draw.ellipse((65, 35, 175, 145), fill='#555861')
    draw.rounded_rectangle((110, 100, 145, 260), radius=14, fill='#555861')
    draw.ellipse((90, 60, 150, 120), fill='#e2ddd0')  # A reflective face
    return image


def upload(client, headers, sku, image, name='product.jpg', orientation=None):
    encoded = BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(encoded, format='JPEG' if name.endswith('.jpg') else 'PNG', exif=exif)
    result = client.post('/api/v1/skus/'+sku+'/sources', content=encoded.getvalue(),
        headers={**headers,'X-Filename':name,'X-Rights-Confirmed':'true'})
    assert result.status_code == 201, result.text
    return result.json()['id']


def test_matte_keeps_contiguous_subject_and_internal_highlights():
    image = product_photo()
    mask = extract_matte(image)
    assert mask.size == image.size and mask.mode == 'L'
    assert mask.getpixel((120, 90)) == 255  # Highlight matches the backdrop
    assert mask.getpixel((127, 220)) == 255  # Stem
    assert mask.getpixel((90, 220)) == mask.getpixel((0, 0)) == 0
    image = image.convert('RGBA')
    image.putalpha(mask)
    assert extract_matte(image).getpixel((127, 220)) == 255
    assert extract_matte(Image.new('RGBA',(32,32))) is None
    assert extract_matte(Image.new('RGB',(150,130),'#888888')) is None


def test_auto_mask_is_reviewed_and_frozen_for_the_correct_photo(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    h = sign_in(client)
    sku = client.post('/api/v1/skus',headers=h,json={'name':'耳机','model':'A','single_spec_confirmed':True}).json()['id']
    original = upload(client,h,sku,product_photo(),orientation=6)
    api = '/api/v1/skus/'+sku
    preview = client.get(api+'/subject-preview',params={'product_id':original})
    assert preview.status_code == 200
    with Image.open(BytesIO(preview.content)) as subject:
        assert subject.size == (320,240)  # Honor camera orientation for display
        assert subject.getchannel('A').getextrema() == (0,255)
    assert len(client.get(api+'/sources').json()['items']) == 1  # Preview is read only
    body = {'expected_revision':1,'product_source_id':original}
    assert client.post(api+'/source-selection',headers=h,json=body).status_code == 422
    body['reviewed'] = True
    accepted = client.post(api+'/source-selection',headers=h,json=body)
    assert accepted.status_code == 200, accepted.text
    selection = accepted.json()['sources']
    mask_id = selection['mask']['source_id']
    with db.Session() as session:
        mask = session.get(Record,mask_id)
        assert mask.data['is_subject_mask'] and mask.data['derived_from_source_id'] == original
        with Image.open(tmp_path/mask.data['object_key']) as saved:
            assert saved.mode == 'L' and saved.size == (240,320) and not saved.getexif()
    profile = client.post(api+'/profiles',headers=h,json={'facts':{},'source_ids':[original]}).json()
    assert profile['source_selection'] == selection
    assert client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=h).status_code == 200
    second = upload(client,h,sku,product_photo(),'alternate.jpg')
    assert client.get(api+'/subject-preview',params={'product_id':second,'mask_id':mask_id}).status_code == 422
    revision = client.get('/api/v1/skus/'+sku).json()['revision']
    repeat = client.post(api+'/source-selection',headers=h,json={**body,'expected_revision':revision})
    assert repeat.status_code == 200 and repeat.json()['sources']['mask']['source_id'] == mask_id
    assert len(client.get(api+'/sources').json()['items']) == 3


def test_uncertain_outline_can_use_whole_photo_without_creating_a_mask(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    h = sign_in(client)
    sku = client.post('/api/v1/skus',headers=h,json={'name':'商品','model':'B','single_spec_confirmed':True}).json()['id']
    api = '/api/v1/skus/'+sku
    cluttered = Image.new('RGB',(220,300),'white')
    draw = ImageDraw.Draw(cluttered)
    for left in range(0,220,40):
        draw.rectangle((left,0,left+20,299),fill='navy')
    photo_id = upload(client,h,sku,cluttered)
    uncertain = client.get(api+'/subject-preview',params={'product_id':photo_id})
    assert uncertain.status_code == 422 and uncertain.json()['detail']['code'] == 'SUBJECT_ISOLATION_UNCERTAIN'
    body = {'expected_revision':1,'product_source_id':photo_id,'reviewed':True}
    assert client.post(api+'/source-selection',headers=h,json=body).status_code == 422
    accepted = client.post(api+'/source-selection',headers=h,json={**body,'mode':'whole_photo'})
    assert accepted.status_code == 200 and set(accepted.json()['sources']) == {'product'}
    assert len(client.get(api+'/sources').json()['items']) == 1
    profile = client.post(api+'/profiles',headers=h,json={'facts':{},'source_ids':[photo_id]}).json()
    assert client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=h).status_code == 200
    other = client.post('/api/v1/skus',headers=h,json={'name':'另一款','model':'C','single_spec_confirmed':True}).json()['id']
    assert client.get('/api/v1/skus/'+other+'/subject-preview',params={'product_id':photo_id}).status_code == 404
    with db.Session.begin() as session:
        source = session.get(Record,photo_id)
        source.data = {**source.data, 'rights_confirmed':False}
    assert client.get(api+'/subject-preview',params={'product_id':photo_id}).status_code == 422
