import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base,Record
from app.execution import Task
from app.versions import apply_text
class VersionTests(unittest.TestCase):
    def test_title_change_preserves_media_and_creates_revision(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            s.add_all([Record(id='result',workspace='w',kind='result_revision',data={'work_id':'work','assets':['video'],'copy':{'title':'old'}}),Record(id='work',workspace='w',kind='work',data={'current_result':'result','draft':{'title':'new'}})])
            s.commit();answer=apply_text(s,'w','work',1)
            self.assertEqual(answer['media_calls'],0)
            new=s.get(Record,answer['current_result']);self.assertEqual(new.data['assets'],['video'])
            self.assertEqual(new.data['copy']['title'],'new')
            self.assertEqual(new.data['result_number'],2)
            self.assertNotIn('result_number',s.get(Record,'result').data)
            self.assertEqual(s.get(Record,'result').data['copy']['title'],'old')

    def test_conflict_and_media_change_leave_current_result_intact(self):
        from fastapi import HTTPException
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            s.add_all([Record(id='result',workspace='w',kind='result_revision',data={'work_id':'work','assets':['video']}),Record(id='work',workspace='w',kind='work',data={'current_result':'result','draft':{'narration':'changed'}})])
            s.commit()
            for expected,code in [(0,'VERSION_CONFLICT'),(1,'MEDIA_UPDATE_AUTHORIZATION_REQUIRED')]:
                with self.assertRaises(HTTPException) as error:
                    apply_text(s,'w','work',expected)
                self.assertEqual(error.exception.detail['code'],code)
                s.rollback()
                self.assertEqual(s.get(Record,'work').data['current_result'],'result')
                self.assertEqual(s.get(Record,'work').data['draft'],{'narration':'changed'})

    def test_revoked_profile_blocks_text_application(self):
        from fastapi import HTTPException
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            s.add_all([Record(id='profile',workspace='w',kind='profile',data={'status':'revoked'}),Record(id='result',workspace='w',kind='result_revision',data={'work_id':'work'}),Record(id='work',workspace='w',kind='work',data={'profile_id':'profile','current_result':'result','draft':{'title':'new'}})])
            s.commit()
            with self.assertRaises(HTTPException) as error:apply_text(s,'w','work',1)
            self.assertEqual(error.exception.detail['code'],'FACT_REVOKED')
            self.assertEqual(s.get(Record,'work').data['current_result'],'result')
    def test_historical_media_restore_creates_new_revision(self):
        from app import sources
        from app.versions import apply_restore
        from fastapi import HTTPException
        import tempfile,hashlib
        from pathlib import Path
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with tempfile.TemporaryDirectory() as directory:
            old=sources.ROOT;sources.ROOT=Path(directory)
            try:
                (sources.ROOT/'video').write_bytes(b'original-media')
                with sessionmaker(engine,expire_on_commit=False)() as s:
                    video=Record(id='asset',workspace='w',kind='asset',data={
                        'work_id':'work','object_key':'video','slot':'douyin','media_kind':'video',
                        'sha256':hashlib.sha256(b'original-media').hexdigest(),'repair_source_ids':['repair'],
                    })
                    repair=Record(id='repair',workspace='w',kind='asset',data={'work_id':'work','media_kind':'product_image',
                        'repair_task_id':'repair-task','review':'rejected'})
                    s.add_all([video,repair,Record(id='profile',workspace='w',kind='profile',data={'status':'confirmed'}),
                        Record(id='past',workspace='w',kind='result_revision',data={'work_id':'work','assets':['asset']}),
                        Record(id='work',workspace='w',kind='work',data={'profile_id':'profile','platforms':['douyin'],
                            'current_result':'newer','draft':{'restore_revision_id':'past'}})])
                    s.commit()
                    with self.assertRaises(HTTPException) as error:apply_restore(s,'w','work',1)
                    self.assertEqual(error.exception.detail['code'],'REPAIR_SOURCE_REVIEW_REQUIRED')
                    self.assertEqual(s.get(Record,'work').data['current_result'],'newer')
                    self.assertEqual(s.get(Record,'work').data['draft'],{'restore_revision_id':'past'})
                    repair.data={**repair.data,'review':'approved'}
                    s.commit()
                    result=apply_restore(s,'w','work',1)
                    self.assertNotEqual(result['current_result'],'past')
                    self.assertEqual(s.get(Record,result['current_result']).data['assets'],['asset'])
                    self.assertEqual(s.get(Record,result['current_result']).data['result_number'],2)
                    self.assertEqual(s.get(Record,'work').data['missing_items'],['douyin/poster'])
                    self.assertEqual(s.get(Record,'work').data['status'],'partial')
                    self.assertEqual((sources.ROOT/'video').read_bytes(),b'original-media')
                    self.assertEqual(result['media_calls'],0)
            finally:sources.ROOT=old

    def test_unselected_platform_cannot_create_copy_revision(self):
        from fastapi import HTTPException
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            s.add_all([Record(id='r',workspace='w',kind='result_revision',data={'work_id':'w','copy':{}}),Record(id='w',workspace='w',kind='work',data={'platforms':['douyin'],'current_result':'r','draft':{'platform':'xiaohongshu','title':'new'}})]);s.commit()
            with self.assertRaises(HTTPException) as error:apply_text(s,'w','w',1)
            self.assertEqual(error.exception.detail['code'],'INVALID_PLATFORM')
            self.assertEqual(s.get(Record,'w').data['current_result'],'r')
    def test_text_revision_creates_sample_and_release_copy(self):
        from app import sources
        from pathlib import Path
        import tempfile,json
        from unittest.mock import patch
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with tempfile.TemporaryDirectory() as directory,patch.object(sources,'ROOT',Path(directory)):
            with sessionmaker(engine,expire_on_commit=False)() as s:
                s.add_all([Record(id='r',workspace='w',kind='result_revision',data={'work_id':'work','copy':{'douyin':{'title':'old'}}}),Record(id='work',workspace='w',kind='work',data={'platforms':['douyin'],'current_result':'r','draft':{'title':'new'}})]);s.commit()
                answer=apply_text(s,'w','work',1)
                revision=s.get(Record,answer['current_result']);asset=s.get(Record,revision.data['assets'][0])
                self.assertEqual(asset.data['review'],'pending')
                sample=json.loads((sources.ROOT/asset.data['object_key']).read_text(encoding='utf-8'))
                release=json.loads((sources.ROOT/asset.data['release_object_key']).read_text(encoding='utf-8'))
                self.assertIn('notice',sample);self.assertNotIn('notice',release)
                self.assertEqual(release['copy']['title'],'new')
