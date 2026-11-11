import hashlib
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from PIL import Image
from app.db import Base, Record
from app.execution import Task
from marketing_worker.business import persist_result
from marketing_worker.configuration import read_credentials


class BusinessTests(unittest.TestCase):
    def test_private_results_are_persisted_under_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            engine=create_engine('sqlite:///'+str(root/'test.db'))
            Base.metadata.create_all(engine)
            sessions=sessionmaker(engine)
            asset=root/'asset.png'; Image.new('RGB',(32,32),'red').save(asset)
            item={'path':str(asset),'sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}
            with sessions.begin() as session:
                session.add(Task(id='task',workspace='ws',state='running',phase='creation_run',fencing_token=1,payload={}))
                session.add(Record(id='work',workspace='ws',kind='work',data={'sku_id':'sku'}))
            job={'id':'task','workspace':'ws','fencing_token':1,'payload':{'work_id':'work'}}
            result={'images':{slot:item for slot in ['white','scene_1','scene_2']},'platforms':{'douyin':{'poster':{'state':'awaiting_review','result':item},'video':{'state':'failed'}}}}
            stored=persist_result(sessions,job,result,root)
            self.assertEqual(len(stored['assets']),4)
            with sessions() as session:
                self.assertEqual(session.get(Record,'work').data['current_result'],'task:result')
                kinds={row.data['media_kind'] for row in session.scalars(select(Record).where(Record.kind=='asset'))}
                self.assertEqual(kinds,{'product_image','marketing_poster'})
            with sessions.begin() as session:
                session.get(Task,'task').fencing_token=2
                session.get(Record,'task:result:poster:douyin').data={
                    **session.get(Record,'task:result:poster:douyin').data,'review':'approved',
                }
            with self.assertRaises(ValueError): persist_result(sessions,job,result,root)
            resumed=persist_result(sessions,{**job,'fencing_token':2},{
                **result,'platforms':{**result['platforms'],
                    'xiaohongshu':{'poster':{'state':'awaiting_review','result':item},'video':{'state':'failed'}},
                },
            },root)
            self.assertNotEqual(resumed['result_revision'],stored['result_revision'])
            with sessions() as session:
                old=session.get(Record,stored['result_revision'])
                current=session.get(Record,resumed['result_revision'])
                self.assertEqual(old.data['assets'],stored['assets'])
                self.assertEqual(old.data['result_number'],1)
                self.assertEqual(current.data['result_number'],2)
                self.assertEqual(current.data['parent_revision'],old.id)
                self.assertEqual(set(current.data['assets'])-set(old.data['assets']),{current.id+':poster:xiaohongshu'})
                self.assertEqual(session.get(Record,'task:result:poster:douyin').data['review'],'approved')
                self.assertEqual(session.get(Record,'work').data['current_result'],current.id)
            engine.dispose()

    def test_credentials_loader_only_reads_required_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'.env'
            path.write_text('DEEPSEEK_API_KEY=a\nMINIMAX_API_KEY=b\nDASHSCOPE_API_KEY=d\nUNRELATED_SECRET=no',encoding='utf-8')
            self.assertEqual(len(read_credentials(path)),3)

    def test_configuration_rejects_nonfinite_or_unreservable_bounds(self):
        from marketing_worker.business import configuration_ready
        with tempfile.TemporaryDirectory() as directory:
            font=Path(directory)/'font';font.write_bytes(b'configuration-test')
            config={'enabled':True,'providers':dict.fromkeys(['text','image','video','tts'],object()),'private_root':directory,'font':str(font),'allowed_hosts':['example.com'],'budget_id':'b','bounds':dict.fromkeys(['text','product_image','dynamic','tts'],'1')}
            self.assertTrue(configuration_ready(config))
            for value in ['NaN','Infinity','0','-1','0.000000001',True,None]:
                with self.subTest(value=value):
                    self.assertFalse(configuration_ready({**config,'bounds':{**config['bounds'],'dynamic':value}}))

            self.assertTrue(configuration_ready({**config,'bounds':{**config['bounds'],'dynamic':'0.00000004'}}))
