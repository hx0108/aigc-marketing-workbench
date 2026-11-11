import unittest
from marketing_worker.pipeline import Pipeline, validate_copy, ContractError


class Store:
    def __init__(self): self.rows = {}
    def read(self, task, key): return self.rows.get((task, key))
    def write(self, task, key, state, result): self.rows[(task,key)] = {'state':state,'result':result}
    def canceled(self, task): return False


class PipelineTests(unittest.TestCase):
    def test_dual_platforms_route_distinct_visuals_and_reject_reused_copy(self):
        request={'platforms':['douyin','xiaohongshu'],'duration_seconds':5,'facts':[{'id':'f1','validity':'active'}]}
        item=dict(title='看商品',body='看清外观',narration='看一下商品',poster_title='商品展示',
                  shots=[{'duration':3,'fact_refs':['f1'],'asset_slot':'scene_2'},{'duration':2,'fact_refs':['f1'],'asset_slot':'white'}])
        copy={'douyin':item,'xiaohongshu':{**item,'title':'看商品！'}}
        with self.assertRaisesRegex(ContractError,'duplicate_platform_title'):
            validate_copy(copy,request)
        copy['xiaohongshu']={**item,'title':'日常挑选笔记','body':'选购前核对规格','narration':'从日常使用场景了解商品',
                             'shots':[{'duration':3,'fact_refs':['f1']},item['shots'][1]]}
        calls=[]
        class Services:
            def invoke(self,kind,payload,intent):
                calls.append((kind,payload))
                return copy if kind=='text' else {'id':intent}
        result=Pipeline(Store(),Services()).execute('dual',request)
        self.assertEqual([(p['platform'],p['shot']['asset_slot']) for kind,p in calls if kind=='dynamic'],
                         [('douyin','scene_1'),('douyin','white'),('xiaohongshu','scene_2'),('xiaohongshu','white')])
        self.assertEqual([(p['image_slot'],p['layout']) for kind,p in calls if kind=='poster_render'],
                         [('scene_1','classic'),('scene_2','product_top')])
        self.assertEqual(len([kind for kind,_ in calls if kind=='product_image']),3)
        self.assertEqual(result['render_settings']['xiaohongshu']['poster_scene'],'scene_2')

    def test_creative_fields_are_data_not_execution_controls(self):
        request={'platforms':['douyin'],'duration_seconds':5,'facts':[{'id':'f1','validity':'active'}]}
        item=dict(title='t',body='b',narration='n',poster_title='p',marketing_angle='confirmed appearance',audience='desktop users',objective='show shape',platform_expression='concise hook',creative_rationale='source f1',shots=[{'duration':5,'fact_refs':['f1'],'asset_slot':'white','visual_description':'Close-up, restrained camera pan'}])
        self.assertEqual(validate_copy({'douyin':item},request)['douyin']['shots'][0]['asset_slot'],'white')
        item['shots'][0]['asset_slot']='https://untrusted.example'
        with self.assertRaises(ContractError):validate_copy({'douyin':item},request)
    def test_static_fallback_is_explicit(self):
        request={'platforms':['douyin'],'duration_seconds':5,'facts':[{'id':'f1','validity':'active'}],'static_fallback_shots':['douyin/0']}
        content={'douyin':dict(title='t',body='b',narration='n',poster_title='p',shots=[{'duration':5,'fact_refs':['f1']}])}
        calls=[]
        class Services:
            def invoke(self,kind,payload,intent):
                calls.append(kind)
                return content if kind=='text' else {'id':intent}
        result=Pipeline(Store(),Services()).execute('task',request)
        self.assertEqual(result['copy']['douyin']['shots'][0]['asset_slot'],'scene_1')
        self.assertNotIn('asset_slot',content['douyin']['shots'][0])
        self.assertIn('static_clip',calls)
        self.assertNotIn('dynamic',calls)
    def test_unknown_model_fields_rejected(self):
        request={'platforms':['douyin'],'duration_seconds':5,'facts':[{'id':'f1','validity':'active'}]}
        item=dict(title='t',body='b',narration='n',poster_title='p',shots=[{'duration':5,'fact_refs':['f1']}])
        item['execute_url']='https://malicious.example'
        with self.assertRaises(ContractError):validate_copy({'douyin':item},request)
        del item['execute_url']
        item['shots'][0]['provider']='unexpected'
        with self.assertRaises(ContractError):validate_copy({'douyin':item},request)

    def test_invalid_model_durations_are_domain_errors(self):
        request={'platforms':['douyin'],'duration_seconds':5,'facts':[{'id':'f1','validity':'active'}]}
        for value in ['NaN','Infinity',True,None,{},-1]:
            with self.subTest(value=value):
                content={'douyin':dict(title='x',body='x',narration='x',poster_title='x',shots=[{'duration':value,'fact_refs':['f1']}])}
                with self.assertRaisesRegex(ContractError,'invalid_shot_duration'):
                    validate_copy(content,request)

    def test_partial_failure_reuses_successful_media(self):
        request = {'platforms':['douyin'], 'duration_seconds':5, 'facts':[{'id':'f1','validity':'active'}]}
        content = {'douyin':dict(title='title', body='body', narration='speech', poster_title='poster', shots=[{'duration':5,'fact_refs':['f1']}])}
        class Services:
            def __init__(self): self.calls=[]; self.fail=True
            def invoke(self, kind, payload, intent):
                self.calls.append(kind)
                if kind == 'text': return content
                if kind == 'poster_render' and self.fail: raise ValueError('overflow')
                return {'asset_id':intent}
        services, store = Services(), Store()
        pipeline = Pipeline(store, services)
        first = pipeline.execute('task', request)
        self.assertEqual(first['platforms']['douyin']['video']['state'], 'awaiting_review')
        self.assertEqual(first['platforms']['douyin']['poster']['state'], 'failed')
        services.fail=False
        second = pipeline.execute('task', request)
        self.assertEqual(second['platforms']['douyin']['poster']['state'], 'awaiting_review')
        self.assertEqual(services.calls.count('dynamic'), 1)
        self.assertEqual(services.calls.count('tts'), 1)

    def test_unknown_step_not_resubmitted(self):
        store=Store(); store.write('task','copy','external_unknown',None)
        with self.assertRaises(ContractError): Pipeline(store, None).step('task','copy','text',{})

    def test_invalid_fact_rejected(self):
        with self.assertRaises(ContractError):
            validate_copy({'douyin':dict(title='x',body='x',narration='x',poster_title='x',shots=[{'duration':5,'fact_refs':['missing']}])}, {'platforms':['douyin'],'duration_seconds':5,'facts':[]})
