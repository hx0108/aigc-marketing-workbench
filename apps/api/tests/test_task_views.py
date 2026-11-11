import unittest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, Record
from app.execution import Budget,Task,ExternalCall
from app.ledger import prepare,settle
from app.task_views import task_view
class TaskViewTests(unittest.TestCase):
    def test_canceled_video_status_is_readable_without_exposing_provider_response(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        with sessionmaker(engine)() as s:
            task=Task(id='t',workspace='w',state='canceled',phase='creation_run',payload={})
            call=ExternalCall(id='call',intent_key='t:douyin/dynamic/0',task_id='t',state='external_unknown',request_hash='h')
            remote=Record(id='remote:'+call.intent_key,workspace='w',kind='provider_result',data={
                'response':{'id':'123','model':'MiniMax-H3','status':'succeeded','content':{'video_url':'https://example.invalid/private'}},
            })
            s.add_all([task,call,remote]);s.commit()
            view=task_view(s,task)
            self.assertEqual(view['next_actions'],['query'])
            self.assertEqual(view['execution_state'],'canceled')
            self.assertEqual(view['video_checks'],[{'call_id':'call','status':'succeeded'}])
            remote.workspace='other';s.commit()
            view=task_view(s,task)
            self.assertEqual(view['next_actions'],[])
            self.assertEqual(view['video_checks'],[])

    def test_canceled_unknown_call_keeps_visible_cost(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            s.add(Budget(id='b',workspace='w',cap=Decimal('10'),reserved=0,settled=0))
            task=Task(id='t',workspace='w',state='canceled',phase='creation_run',payload={'work_id':'work'})
            s.add(task);s.add(ExternalCall(id='c',intent_key='c',task_id='t',state='external_unknown',request_hash='h'));s.commit()
            prepare(s,'b','c','h','6');s.commit()
            view=task_view(s,task)
            self.assertEqual(Decimal(view['reserved_cost']),Decimal('6'))
            self.assertTrue(view['unknown_cost_flag'])
            self.assertEqual(view['cost_state'],'pending')
            self.assertEqual(view['next_actions'],[])
            settle(s,'b','c','bill','2',True,'final invoice')
            s.get(ExternalCall,'c').state='reconciled';s.commit()
            view=task_view(s,task)
            self.assertEqual(view['execution_state'],'canceled')
            self.assertEqual(Decimal(view['reserved_cost']),0)
            self.assertEqual(Decimal(view['settled_cost']),2)
            self.assertFalse(view['unknown_cost_flag'])
            self.assertEqual(view['cost_state'],'settled')

def test_safe_task_error_projection():
    from app.task_views import task_error
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        task=Task(id='safe',workspace='w',state='failed',phase='creation_run',payload={'_outcome':{'error_code':'NUMERIC_CLAIM_REVIEW_REQUIRED','raw':'secret'}})
        s.add(task);s.commit()
        result=task_error(s,task)
        assert result['code']=='NUMERIC_CLAIM_REVIEW_REQUIRED'
        assert '已停止' in result['message']
        assert 'secret' not in str(result)
        task.payload={'_outcome':{'error_code':'secret-path-key'}}
        assert task_error(s,task)['code']=='GENERATION_FAILED'
        s.add(Record(id='safe:copy',workspace='other',kind='task_step',data={'state':'failed','result':{'code':'text_input_too_large'}}));s.commit()
        assert task_error(s,task)['code']=='GENERATION_FAILED'
        task.state='external_unknown'
        assert '停止推进' in task_error(s,task)['message']
        task.state='running'
        assert task_error(s,task) is None
    engine.dispose()

def test_common_errors_have_safe_stage_and_no_blind_retry():
    from app.task_views import task_error
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        for code,stage in [('BUDGET_INSUFFICIENT','预算与授权'),('source_hash_mismatch','商品资料'),('provider_rejected','外部生成服务'),('TimeoutExpired','任务处理'),('voice_duration_mismatch','配音'),('text_input_too_large','创作文案')]:
            task=Task(id=code,workspace='w',state='failed',phase='creation_run',payload={'_outcome':{'error_code':code,'provider_status':401,'transport_error':'secret'}})
            error=task_error(s,task)
            assert error['code']==code and error['stage']==stage
            assert 'secret' not in str(error) and '401' not in str(error)
        task=Task(id='video-error',workspace='w',state='external_unknown',phase='creation_run',payload={})
        s.add(Record(id='video-error:douyin/dynamic/0',workspace='w',kind='task_step',data={'state':'external_unknown','result':{'code':'external_unknown','transport_error':'ReadTimeout','raw':'private'}}));s.commit()
        error=task_error(s,task)
        assert error['stage']=='生成画面'
        assert '费用预留保留' in error['hint'] and '不要重复生成' in error['hint']
        assert 'private' not in str(error)
    engine.dispose()
