import unittest,tempfile,hashlib,json,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,PngImagePlugin
from app import db, exporting, release, release_verify
from app.db import Record
from test_core import client


def implicit_fields():
    return {'Label':'1','ContentProducer':'fixture','ProduceID':'fixture-1','ReservedCode1':'',
            'ContentPropagator':'fixture','PropagateID':'fixture-1','ReservedCode2':''}


def save_poster(path):
    metadata=PngImagePlugin.PngInfo()
    metadata.add_text('AIGC',json.dumps({'AIGC':implicit_fields()}))
    Image.new('RGB',(10,10)).save(path,pnginfo=metadata)


class ReleaseRuleTests(unittest.TestCase):
    def test_implicit_metadata_rejects_invalid_and_duplicate_fields(self):
        for value in ({**implicit_fields(),'Label':'2'},{**implicit_fields(),'ProduceID':''},
                      {**implicit_fields(),'ContentProducer':123}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'IMPLICIT_LABEL_INVALID'):
                release.require_implicit_label([json.dumps(value)])
        duplicate=json.dumps(implicit_fields()).replace('"Label": "1"', '"Label": "1", "Label": "1"')
        with self.assertRaisesRegex(ValueError,'IMPLICIT_LABEL_INVALID'):
            release.require_implicit_label([duplicate])

    def test_release_reads_final_png_and_mp4_implicit_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rules={'implicit_label_version':release.IMPLICIT_LABEL_VERSION,'platforms':{
                'douyin':{'marketing_poster':{'size':[10,10]},'video':{'size':[32,32],'codec':'h264'}}}}
            with patch.object(release,'ROOT',root):
                image=root/'poster.png'
                Image.new('RGB',(10,10)).save(image)
                poster=SimpleNamespace(data={'media_kind':'marketing_poster','slot':'douyin','release_object_key':image.name,
                    'release_sha256':hashlib.sha256(image.read_bytes()).hexdigest()})
                with self.assertRaisesRegex(ValueError,'IMPLICIT_LABEL_RULE_REQUIRED'):
                    release.release_file(poster,{**rules,'implicit_label_version':'old'})
                with self.assertRaisesRegex(ValueError,'IMPLICIT_LABEL_REQUIRED'):release.release_file(poster,rules)
                packet=PngImagePlugin.PngInfo()
                packet.add_itxt('XML:com.adobe.xmp','<root xmlns:tc="http://www.tc260.org.cn/ns/AIGC/1.0/">'
                    '<tc:AIGC>'+json.dumps(implicit_fields())+'</tc:AIGC></root>')
                Image.new('RGB',(10,10)).save(image,pnginfo=packet)
                poster.data['release_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
                self.assertEqual(release.release_file(poster,rules),image)
                packet.add_text('AIGC',json.dumps({'AIGC':implicit_fields()}))
                Image.new('RGB',(10,10)).save(image,pnginfo=packet)
                poster.data['release_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError,'IMPLICIT_LABEL_INVALID'):release.release_file(poster,rules)
                video=root/'video.mp4'
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=32x32:d=0.1',
                    '-c:v','libx264','-movflags','use_metadata_tags','-metadata','AIGC='+json.dumps(implicit_fields()),str(video)],
                    check=True,timeout=20)
                asset=SimpleNamespace(data={'media_kind':'video','slot':'douyin','release_object_key':video.name,
                    'release_sha256':hashlib.sha256(video.read_bytes()).hexdigest()})
                self.assertEqual(release.release_file(asset,rules),video)

    def test_worker_derivatives_preserve_originals_and_pass_release_gate(self):
        from marketing_worker.release_metadata import labelled_derivative
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=root/'image.png'
            Image.new('RGB',(10,10)).save(image)
            video=root/'video.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=32x32:d=0.1',
                '-c:v','libx264',str(video)],check=True,timeout=20)
            rules={'implicit_label_version':release.IMPLICIT_LABEL_VERSION,'platforms':{
                'douyin':{'marketing_poster':{'size':[10,10]},'video':{'size':[32,32],'codec':'h264'}}}}
            identity={'AIGC_RELEASE_CONTENT_PRODUCER':'fixture','AIGC_RELEASE_CONTENT_PROPAGATOR':'fixture'}
            with patch.object(release,'ROOT',root), patch.dict('os.environ',identity):
                for source,kind in ((image,'marketing_poster'),(video,'video'),(image,'cover'),(image,'product_image')):
                    original=source.read_bytes()
                    digest=hashlib.sha256(original).hexdigest()
                    tagged=labelled_derivative(source,digest,['workspace','work',kind,'douyin'],root)
                    self.assertNotEqual(tagged,source)
                    self.assertEqual(source.read_bytes(),original)
                    self.assertEqual(labelled_derivative(source,digest,['workspace','work',kind,'douyin'],root),tagged)
                    asset=SimpleNamespace(data={'media_kind':kind,'slot':'douyin','release_object_key':tagged.name,
                        'release_sha256':hashlib.sha256(tagged.read_bytes()).hexdigest()})
                    if kind=='cover':
                        rules['platforms']['douyin']['cover']={'size':[10,10]}
                    self.assertEqual(release.release_file(asset,rules),tagged)

    def test_verified_rule_and_exact_review_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);save_poster(root/'poster.png')
            asset=SimpleNamespace(id='poster',revision=1,data={'media_kind':'marketing_poster','slot':'douyin','release_object_key':'poster.png','release_sha256':hashlib.sha256((root/'poster.png').read_bytes()).hexdigest(),'review':'pending','label_rule_version':'test-rule','extension':'.png'})
            work=SimpleNamespace(id='w',revision=1,data={'platforms':['douyin']})
            rules={'version':'test-rule','implicit_label_version':release.IMPLICIT_LABEL_VERSION,'platforms':{'douyin':{'marketing_poster':{'size':[10,10]}}}}
            with patch.object(release,'ROOT',root),patch.object(release,'ruleset',return_value=rules):
                with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):release.package_release(work,[asset],'poster_only')
                asset.data['review']='approved'
                with self.assertRaisesRegex(ValueError,'LABEL_VERIFICATION_REQUIRED'):release.package_release(work,[asset],'poster_only')
                asset.data['label_verification']=release.verify_label(asset,rules,1,asset.data['release_sha256'],'operator','fixture evidence')
                rights={'source_provenance_available':True,'materials':[{'kind':'source','confirmation':'user_confirmed'}]}
                result=release.package_release(work,[asset],'poster_only',rights=rights)
                self.assertEqual(result['manifest']['mode'],'release')
                self.assertEqual(result['manifest']['assets'][0]['platform'], 'douyin')
                self.assertEqual(result['manifest']['assets'][0]['label'], {'internal_sample': False, 'verified_rule_version': 'test-rule'})
                self.assertTrue((root/result['object_key']).is_file())
                work.data['platforms'].append('xiaohongshu')
                partial=release.package_release(work,[asset],'poster_only',partial=True,rights=rights)
                self.assertTrue(partial['manifest']['partial'])
                self.assertEqual(partial['manifest']['missing_items'],['marketing_poster/xiaohongshu'])
                work.data['platforms'].pop()
                rules['reviewer']='changed without a version bump'
                with self.assertRaisesRegex(ValueError,'LABEL_VERIFICATION_REQUIRED'):release.package_release(work,[asset],'poster_only')
    def test_ruleset_missing_or_naive_expiry_is_invalid(self):
        import os,json
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rules.json'
            for data in ({'verified':True},{'valid_until':'2099-01-01T00:00:00','platforms':{}}):
                path.write_text(json.dumps(data),encoding='utf-8')
                with patch.dict(os.environ,{'AIGC_RULESET_FILE':str(path)}):
                    with self.assertRaisesRegex(ValueError,'RULESET_INVALID'):release.ruleset()
    def test_duplicate_and_unselected_slots_rejected(self):
        work=SimpleNamespace(id='w',revision=1,data={'platforms':['douyin']})
        asset=SimpleNamespace(id='a',data={'media_kind':'marketing_poster','slot':'douyin'})
        with patch.object(release,'ruleset',return_value={'platforms':{'douyin':{}}}):
            with self.assertRaisesRegex(ValueError,'DUPLICATE_SLOT'):release.package_release(work,[asset,asset],'poster_only')
            asset.data['slot']='xiaohongshu'
            with self.assertRaisesRegex(ValueError,'UNSELECTED_PLATFORM'):release.package_release(work,[asset],'poster_only')


def test_operator_binding_is_required_for_release_and_download(client,tmp_path,monkeypatch):
    path=tmp_path/'poster.png'
    save_poster(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    rules={'version':'test-rule','implicit_label_version':release.IMPLICIT_LABEL_VERSION,'platforms':{'douyin':{'marketing_poster':{'size':[10,10]}}}}
    monkeypatch.setattr(release,'ROOT',tmp_path)
    monkeypatch.setattr(exporting,'ROOT',tmp_path)
    monkeypatch.setattr(release,'ruleset',lambda:rules)
    monkeypatch.setattr(release_verify,'ruleset',lambda:rules)
    monkeypatch.setattr(release_verify,'local_database_only',lambda:None)
    with db.Session.begin() as session:
        session.add_all([
            Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','source_ids':['source']}),
            Record(id='source',workspace='one',kind='source',data={'sku_id':'sku','rights_confirmed':False}),
            Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','platforms':['douyin'],'current_result':'result'}),
            Record(id='result',workspace='one',kind='result_revision',data={'work_id':'work','assets':['poster']}),
            Record(id='poster',workspace='one',kind='asset',data={'work_id':'work','media_kind':'marketing_poster','slot':'douyin',
                'review':'approved','release_object_key':path.name,'release_sha256':digest,'extension':'.png','repair_source_ids':['repair'],
                'sample_marked':True,'object_key':path.name,'sha256':digest}),
            Record(id='repair',workspace='one',kind='asset',data={'work_id':'work','media_kind':'product_image',
                'review':'approved','repair_task_id':'repair-task'}),
        ])
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    body={'work_id':'work','mode':'release','selection':'poster_only'}
    export='/api/v1/export-packages'
    args=['--workspace','one','--asset-id','poster','--asset-revision','1','--release-sha256',digest,
          '--rule-sha256',release.rules_fingerprint(rules),'--reviewer','operator','--evidence','fixture-reference']
    assert release_verify.main(args)==0
    assert client.post(export,json=body,headers=headers).json()['detail']['code']=='LABEL_VERIFICATION_REQUIRED'
    assert release_verify.main([*args,'--apply'])==0
    assert client.post(export,json=body,headers=headers).json()['detail']['code']=='MATERIAL_RIGHTS_UNVERIFIED'
    with db.Session.begin() as session:
        session.get(Record,'source').data={'sku_id':'sku','rights_confirmed':True}
    package=client.post(export,json=body,headers=headers)
    assert package.status_code==200,package.text
    assert 'fixture-reference' not in client.get('/api/v1/works/work').text
    download='/api/v1/exports/'+package.json()['id']+'/download'
    assert client.get(download).status_code==200
    sample_body={**body,'mode':'sample'}
    sample=client.post(export,json=sample_body,headers=headers)
    assert sample.status_code==200,sample.text
    sample_download='/api/v1/exports/'+sample.json()['id']+'/download'
    assert client.get(sample_download).status_code==200
    repair_review='/api/v1/assets/repair/reviews'
    assert client.post(repair_review,json={'decision':'reject'},headers=headers).status_code==201
    for response in (client.post(export,json=body,headers=headers),client.get(download),
                     client.post(export,json=sample_body,headers=headers),client.get(sample_download)):
        assert response.status_code==409
        assert response.json()['detail']['code']=='REPAIR_SOURCE_REVIEW_REQUIRED'
    assert client.post(repair_review,json={'decision':'adopt'},headers=headers).status_code==201
    assert client.get(download).status_code==200
    with db.Session.begin() as session:
        session.get(Record,'source').revision+=1
    assert client.get(download).json()['detail']['code']=='MATERIAL_RIGHTS_CHANGED'
    with db.Session.begin() as session:
        session.get(Record,'source').data={'sku_id':'sku','rights_confirmed':False}
    assert client.get(download).json()['detail']['code']=='MATERIAL_RIGHTS_UNVERIFIED'
    rules['reviewer']='different evidence context'
    assert client.get(download).json()['detail']['code']=='RULESET_CHANGED'
    del rules['reviewer']
    review='/api/v1/assets/poster/reviews'
    assert client.post(review,json={'decision':'reject'},headers=headers).status_code==201
    for response in (client.post(export,json=sample_body,headers=headers),client.get(sample_download)):
        assert response.status_code==409
        assert response.json()['detail']['code']=='ASSET_REJECTED'
    conflict=client.post(review,json={'decision':'adopt','expected_review':'pending'},headers=headers)
    assert conflict.status_code==409 and conflict.json()['detail']['code']=='ASSET_REVIEW_CHANGED'
    assert client.post(review,json={'decision':'adopt'},headers=headers).status_code==201
    assert client.get(download).json()['detail']['code']=='LABEL_VERIFICATION_REQUIRED'
