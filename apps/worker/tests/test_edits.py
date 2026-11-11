import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base,Record
from app.execution import Task
from marketing_worker.edits import edit_handler


class EditIntegrationTests(unittest.TestCase):
    def test_minimal_calls_and_latest_voice_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+directory+'/test.db')
            Base.metadata.create_all(engine); sessions=sessionmaker(engine)
            base={'assets':['original:result:image:white'],'source_task_id':'original','copy':{'douyin':{'title':'t','body':'b','poster_title':'p','narration':'n','shots':[{'duration':5,'narration':'n','fact_refs':['f1']}]}},'branches':{'douyin':{'video':{'state':'awaiting_review','result':{'id':'video'}},'poster':{'state':'awaiting_review','result':{'id':'poster'}}}}}
            with sessions.begin() as session:
                session.add(Record(id='profile',workspace='ws',kind='profile',data={'status':'confirmed','facts':{'f1':'red'}}))
                for key in ['image/white','image/scene_1','image/scene_2','douyin/dynamic/0','douyin/voice']:
                    session.add(Record(id='original:'+key,workspace='ws',kind='task_step',data={'state':'succeeded','result':{'id':'original:'+key}}))
            calls=[]
            class Services:
                private_root=directory
                def invoke(self,kind,payload,intent):
                    calls.append((kind,payload))
                    return {'id':intent}
            service=Services()
            def execute(identifier,draft,current):
                with sessions.begin() as session:session.add(Task(id=identifier,workspace='ws',state='running',phase='edit_run',fencing_token=1,payload={}))
                job={'id':identifier,'workspace':'ws','fencing_token':1,'payload':{'work_id':'work','profile_id':'profile','draft':{'platform':'douyin',**draft},'base_result':current}}
                with patch('marketing_worker.edits.persist_result',side_effect=lambda sessions,job,result,root:result):
                    return edit_handler(SimpleNamespace(sessions=sessions),job,lambda job:service)
            poster=execute('poster',{'poster_title':'new','title':'new title','body':'new body'},base)
            self.assertEqual([kind for kind,_ in calls],['poster_render'])
            self.assertEqual(poster['copy']['douyin']['title'],'new title')
            self.assertEqual(poster['copy']['douyin']['body'],'new body')
            self.assertEqual(base['copy']['douyin']['title'],'t')
            calls.clear()
            with self.assertRaises(ValueError):
                execute('unsupported-poster-claim',{'poster_points':['功率200W']},base)
            self.assertEqual(calls,[])
            execute('subtitle',{'subtitle_style':'large'},base)
            self.assertEqual([kind for kind,_ in calls],['video_render'])
            calls.clear()
            voice=execute('voice',{'voice':'Cherry'},base)
            self.assertEqual([kind for kind,_ in calls],['tts','video_render'])
            calls.clear()
            updated={**base,'copy':voice['copy'],'branches':voice['platforms'],'step_sources':voice['step_sources']}
            execute('second-subtitle',{'subtitle_style':'small'},updated)
            self.assertEqual([kind for kind,_ in calls],['video_render'])
            self.assertEqual(calls[0][1]['voice']['id'],'voice:douyin/voice')
            calls.clear()
            execute('whole-narration',{'narration':'updated speech'},base)
            self.assertEqual([kind for kind,_ in calls],['tts','video_render'])
            self.assertEqual(calls[0][1]['text'],calls[1][1]['copy']['shots'][0]['narration'])
            import copy
            multiple=copy.deepcopy(base)
            multiple['copy']['douyin']['shots'].append({'duration':5,'narration':'second','fact_refs':['f1']})
            calls.clear()
            with self.assertRaisesRegex(ValueError,'narration_requires_shot_mapping'):
                execute('unmapped-narration',{'narration':'unmapped new speech'},multiple)
            self.assertEqual(calls,[])
            calls.clear()
            inherited={**updated,'render_settings':{'douyin':{'subtitle_style':'large','voice':'Serena','poster_layout':'product_top'}}}
            inherited_result=execute('inherited-voice',{'voice':'Cherry'},inherited)
            self.assertEqual(calls[-1][1]['subtitle_style'],'large')
            self.assertEqual(inherited_result['render_settings']['douyin']['poster_layout'],'product_top')
            self.assertEqual(inherited['render_settings']['douyin']['voice'],'Serena')
            calls.clear()
            visual=execute('shot-visual',{'shots':[{'index':0,'visual_description':'red studio','asset_slot':'scene_2'}]},base)
            self.assertEqual([kind for kind,_ in calls],['dynamic','video_render'])
            self.assertEqual(calls[0][1]['shot']['asset_slot'],'scene_2')
            self.assertEqual(visual['step_sources']['douyin/dynamic/0'],'shot-visual')
            with sessions.begin() as session:
                session.add(Record(id='repaired',workspace='ws',kind='asset',data={
                    'work_id':'work','media_kind':'product_image','slot':'scene_2','repair_task_id':'repair',
                    'review':'approved','object_key':'marked.png','repair_render_key':'clean.png','repair_render_sha256':'clean-digest',
                }))
            calls.clear()
            repaired_base={**base,'copy':visual['copy'],'assets':['repaired']}
            repaired_result=execute('repaired-shot',{'shots':[{'index':0,'repair_asset_id':'repaired'}]},repaired_base)
            self.assertEqual([kind for kind,_ in calls],['dynamic','video_render'])
            self.assertTrue(calls[0][1]['images']['scene_2']['path'].endswith('clean.png'))
            self.assertEqual(calls[0][1]['images']['scene_2']['sha256'],'clean-digest')
            self.assertEqual(calls[0][1]['images']['white'],{'id':'original:image/white'})
            self.assertNotIn('repair_asset_id',repaired_result['copy']['douyin']['shots'][0])
            self.assertEqual(repaired_result['platforms']['douyin']['video']['result']['repair_source_ids'],['repaired'])
            calls.clear()
            repaired_poster=execute('repaired-poster',{'poster_title':'Updated poster'},{
                **repaired_base,'render_settings':{'douyin':{'poster_scene':'scene_2'}},
            })
            self.assertEqual([kind for kind,_ in calls],['poster_render'])
            self.assertEqual(repaired_poster['platforms']['douyin']['poster']['result']['repair_source_ids'],['repaired'])
            calls.clear()
            with self.assertRaisesRegex(ValueError,'approved_repair_render_source_required'):
                execute('wrong-slot-repair',{'shots':[{'index':0,'asset_slot':'white','repair_asset_id':'repaired'}]},repaired_base)
            self.assertEqual(calls,[])
            calls.clear()
            narrated=execute('shot-narration',{'shots':[{'index':0,'narration':'red shape'}]},base)
            self.assertEqual([kind for kind,_ in calls],['tts','video_render'])
            self.assertEqual(calls[0][1]['text'],'red shape')
            self.assertEqual(base['copy']['douyin']['shots'][0]['narration'],'n')
            calls.clear()
            unchanged={**base,'copy':visual['copy']}
            execute('unchanged-shot',{'shots':[{'index':0,'asset_slot':'scene_2','visual_description':'red studio','narration':'n'}]},unchanged)
            self.assertEqual(calls,[])
            for identifier,draft in [('inherited-conflict',{'shots':[{'index':0,'visual_description':'new visual'}]}),('new-conflict',{'asset_id':'replacement','shots':[{'index':0,'narration':'new narration'}]})]:
                conflicting={**base,'render_settings':{'douyin':{'asset_id':'replacement'}}} if identifier=='inherited-conflict' else base
                calls.clear()
                with self.assertRaisesRegex(ValueError,'shot_edit_conflicts_with_full_video_replacement'):execute(identifier,draft,conflicting)
                self.assertEqual(calls,[])
            with sessions.begin() as session:
                session.add(Record(id='foreign-video',workspace='ws',kind='asset',data={
                    'work_id':'other-work','media_kind':'video','slot':'douyin','review':'approved',
                }))
            with self.assertRaisesRegex(ValueError,'replacement_video_asset_required'):
                execute('foreign-video-job',{'asset_id':'foreign-video'},{**base,'assets':['foreign-video']})
            self.assertEqual(calls,[])
            with sessions.begin() as session:
                session.get(Record,'original:douyin/dynamic/0').data={'state':'external_unknown','result':None}
                session.add(Record(id='original:douyin/static/0',workspace='ws',kind='task_step',data={'state':'succeeded','result':{'id':'chosen-static'}}))
            calls.clear()
            execute('static-subtitle',{'subtitle_style':'large'},updated)
            self.assertEqual([kind for kind,_ in calls],['video_render'])
            self.assertEqual(calls[0][1]['clips'],[{'id':'chosen-static'}])
            self.assertEqual(calls[0][1]['voice']['id'],'voice:douyin/voice')
            calls.clear()
            execute('static-shot',{'shots':[{'index':0,'asset_slot':'white'}]},updated)
            self.assertEqual([kind for kind,_ in calls],['static_clip','video_render'])
            for identifier,change in [('bad-index',{'index':True,'narration':'x'}),('bad-duration',{'index':0,'duration':9}),('invented-value',{'index':0,'narration':'200W'})]:
                calls.clear()
                with self.assertRaises(ValueError):execute(identifier,{'shots':[change]},updated)
                self.assertEqual(calls,[])
            engine.dispose()
