import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app.execution import Task
from app.shot_edits import merge_shots,plan


class ShotEditTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine)
        self.s=sessionmaker(self.engine,expire_on_commit=False)()
        self.work=Record(id='work',workspace='w',kind='work',data={'platforms':['douyin'],'current_result':'result'})
        self.result=Record(id='result',workspace='w',kind='result_revision',data={'work_id':'work','source_task_id':'original','copy':{'douyin':{'shots':[{'narration':'a','visual_description':'v','asset_slot':'white'},{'narration':'b','visual_description':'v','asset_slot':'scene_1'}]}}})
        self.s.add_all([self.work,self.result]);self.s.commit()

    def tearDown(self):self.s.close();self.engine.dispose()

    def test_narration_only_once_and_visual_static_is_free(self):
        nodes,count=plan(self.s,self.work,{'shots':[{'index':0,'narration':'x'},{'index':1,'narration':'y'}]})
        self.assertEqual(nodes,{'tts','subtitles','video_compose'});self.assertEqual(count,0)
        self.s.add(Record(id='original:douyin/static/1',workspace='w',kind='step',data={'state':'succeeded'}));self.s.commit()
        nodes,count=plan(self.s,self.work,{'shots':[{'index':0,'asset_slot':'scene_2'},{'index':1,'visual_description':'new'}]})
        self.assertEqual(count,1);self.assertEqual(nodes,{'dynamic','static_clip','video_compose'})

    def test_merge_noop_and_rejections(self):
        self.assertEqual(merge_shots([{'index':0,'narration':'x'}],[{'index':0,'asset_slot':'white'}]),[{'index':0,'narration':'x','asset_slot':'white'}])
        self.assertEqual(plan(self.s,self.work,{'shots':[{'index':0,'narration':'a','asset_slot':'white'}]}),(set(),0))
        for patches in [[{'index':True}], [{'index':0},{'index':0}], [{'index':0,'duration':5}], [{'index':3}], [{'index':0,'asset_slot':'bad'}]]:
            with self.assertRaises(HTTPException):plan(self.s,self.work,{'shots':patches})

    def test_full_video_conflict_clear_and_whole_narration(self):
        self.result.data={**self.result.data,'render_settings':{'douyin':{'asset_id':'video'}}};self.s.commit()
        with self.assertRaises(HTTPException) as error:plan(self.s,self.work,{'shots':[{'index':0,'narration':'x'}]})
        self.assertEqual(error.exception.detail['code'],'SHOT_EDIT_CONFLICTS_WITH_FULL_VIDEO_REPLACEMENT')
        self.assertIn('tts',plan(self.s,self.work,{'asset_id':None,'shots':[{'index':0,'narration':'x'}]})[0])
        with self.assertRaises(HTTPException) as error:plan(self.s,self.work,{'narration':'not mapped'})
        self.assertEqual(error.exception.detail['code'],'NARRATION_REQUIRES_SHOT_MAPPING')

    def test_apply_requires_current_quote_and_replays_original_task(self):
        from unittest.mock import patch
        from app.main import changes, apply_work, RevisionAction
        from sqlalchemy import select
        from marketing_worker import business

        self.s.add(Record(id='profile',workspace='w',kind='profile',data={'status':'confirmed'}))
        self.work.data = {**self.work.data, 'creation_request_id': 'request', 'profile_id': 'profile',
                          'draft': {'shots': [{'index': 0, 'narration': 'new'}]}}
        self.s.commit()
        authorization = {'bounds': {'tts': '0.05'}, 'price_version': 'v1', 'budget_id': 'budget'}
        action = RevisionAction(expected_revision=self.work.revision, authorized=True)
        with patch.object(business, 'readiness', return_value=[]), patch.object(
            business, 'authorization_snapshot', side_effect=lambda *args: authorization
        ):
            with self.assertRaises(HTTPException) as error:
                apply_work('work', action, 'one', 'w', self.s)
            self.assertEqual(error.exception.detail['code'], 'CHANGE_QUOTE_REQUIRED')
            quote = changes('work', 'w', self.s)
            action.quote_id = quote['quote_id']
            authorization = {**authorization, 'bounds': {'tts': '0.06'}}
            with self.assertRaises(HTTPException) as error:
                apply_work('work', action, 'one', 'w', self.s)
            self.assertEqual(error.exception.detail['code'], 'CHANGE_QUOTE_STALE')
            self.assertIsNone(self.s.scalar(select(Task)))
            action.quote_id = changes('work', 'w', self.s)['quote_id']
            accepted = apply_work('work', action, 'one', 'w', self.s)
            with self.assertRaises(HTTPException) as error:
                apply_work('work', action, 'two', 'w', self.s)
            self.assertEqual(error.exception.detail['code'], 'CHANGE_QUOTE_STALE')
            second_quote = changes('work', 'w', self.s)['quote_id']
            second_action = RevisionAction(expected_revision=action.expected_revision, authorized=True, quote_id=second_quote)
            with self.assertRaises(HTTPException) as error:
                apply_work('work', second_action, 'two', 'w', self.s)
            self.assertEqual(error.exception.detail['code'], 'EDIT_ALREADY_ACTIVE')
            from app.recovery import recover
            failed_task = Task(id='failed-edit', workspace='w', state='failed', phase='edit_run',
                               payload={'work_id':'work','base_draft_revision':action.expected_revision,
                                        'base_result_id':'result'})
            self.s.add(failed_task)
            self.s.commit()
            with self.assertRaises(HTTPException) as error:
                recover(self.s, failed_task)
            self.assertEqual(error.exception.detail['code'], 'EDIT_ALREADY_ACTIVE')
            self.work.revision += 1
            self.work.data = {**self.work.data, 'draft': {}}
            self.s.commit()
            self.assertEqual(apply_work('work', action, 'one', 'w', self.s), accepted)

    def test_worker_checks_edit_base_before_reservation_and_handler(self):
        from decimal import Decimal
        from unittest.mock import Mock
        from sqlalchemy import select
        from app.execution import Budget, ExternalCall
        from app.ledger import CallReservation
        from marketing_worker.persistence import AuthorizedServices

        self.s.add_all([
            Budget(id='budget', workspace='w', cap=Decimal('1')),
            Task(id='edit', workspace='w', state='running', phase='edit_run', fencing_token=1,
                 payload={'work_id':'work','base_draft_revision':self.work.revision,'base_result_id':'result'}),
        ])
        self.s.commit()
        self.work.revision += 1
        self.s.commit()
        handler = Mock()
        service = AuthorizedServices(sessionmaker(self.engine), 'budget', Mock(), {'tts':handler},
                                     {'tts':Decimal('0.05')}, 'edit', 'w', 1)
        with self.assertRaisesRegex(ValueError, 'stale_edit_result'):
            service.invoke('tts', {'text':'new'}, 'edit:tts')
        handler.assert_not_called()
        self.assertIsNone(self.s.scalar(select(ExternalCall)))
        self.assertIsNone(self.s.scalar(select(CallReservation)))

    def test_minimax_quote_and_worker_use_billable_shot_duration(self):
        from decimal import Decimal
        from unittest.mock import Mock, patch
        from sqlalchemy import select
        from app.execution import Budget, ExternalCall
        from app.ledger import CallReservation
        from app.main import changes, apply_work, RevisionAction
        from marketing_worker import business
        from marketing_worker.persistence import AuthorizedServices

        self.s.add_all([Record(id='profile',workspace='w',kind='profile',data={'status':'confirmed'}),
                        Budget(id='budget',workspace='w',cap=Decimal('10'),settled=Decimal('5'))])
        shots = [{'duration':3.2,'asset_slot':'white'}, {'duration':4.1,'asset_slot':'white'},
                 {'duration':15,'asset_slot':'white'}]
        self.result.data = {**self.result.data, 'copy':{'douyin':{'shots':shots}}}
        self.s.add(Record(id='original:douyin/static/2',workspace='w',kind='step',data={'state':'succeeded'}))
        self.work.data = {**self.work.data,'creation_request_id':'request','profile_id':'profile',
                          'draft':{'shots':[{'index':index,'asset_slot':'scene_1'} for index in range(3)]}}
        self.s.commit()
        authorization = {'bounds':{'dynamic':'7.50'},'price_version':'minimax-cn-2026-11-11',
                         'budget_id':'budget','providers':{'video':'MiniMax-H3'},
                         'provider_parameters':{'video':{'resolution':'768P'}}}
        with patch.object(business,'readiness',return_value=[]), patch.object(
            business,'authorization_snapshot',side_effect=lambda *args: authorization
        ):
            quote = changes('work','w',self.s)
            self.assertEqual(Decimal(quote['cost_upper_bound']), Decimal('4.50'))
            action = RevisionAction(expected_revision=self.work.revision,authorized=True,quote_id=quote['quote_id'])
            accepted = apply_work('work',action,'short-shots','w',self.s)
        task = self.s.get(Task,accepted['task_id'])
        task.state = 'running'
        task.fencing_token = 1
        self.s.commit()
        handler = Mock(return_value={'id':'example'})
        service = AuthorizedServices(sessionmaker(self.engine),'budget',Mock(),{'dynamic':handler},
                                     authorization['bounds'],task.id,'w',1)
        service.invoke('dynamic',{'shot':shots[0]},'short-1')
        service.invoke('dynamic',{'shot':shots[1]},'short-2')
        with self.assertRaisesRegex(ValueError,'consent_cost_upper_bound_exceeded'):
            service.invoke('dynamic',{'shot':shots[1]},'short-extra')
        self.assertEqual(handler.call_count,2)
        self.assertIsNone(self.s.get(ExternalCall,'short-extra'))
        self.assertEqual(list(self.s.scalars(select(CallReservation.upper_bound).order_by(CallReservation.id))),
                         [Decimal('2.00'),Decimal('2.50')])

    def test_minimax_bound_rejects_unsupported_duration_and_insufficient_ceiling(self):
        from decimal import Decimal
        from app.pricing import dynamic_bound
        authorization = {'bounds':{'dynamic':'2.00'},'price_version':'minimax-cn-2026-11-11',
                         'providers':{'video':'MiniMax-H3'},
                         'provider_parameters':{'video':{'resolution':'768P'}}}
        self.assertEqual(dynamic_bound(authorization,4), Decimal('2.00'))
        with self.assertRaisesRegex(ValueError,'dynamic_cost_exceeds_configured_bound'):
            dynamic_bound(authorization,4.1)
        with self.assertRaisesRegex(ValueError,'invalid_minimax_video_duration'):
            dynamic_bound(authorization,15.1)
        self.assertEqual(dynamic_bound({**authorization,'price_version':'other'},4.1),Decimal('2.00'))

        from app.pricing import creation_reservation_floor
        authorization['bounds'].update(text='0.10',product_image='0.05',tts='0.10')
        self.assertEqual(creation_reservation_floor(authorization,2,1),Decimal('2.30'))
        self.assertEqual(creation_reservation_floor(authorization,5,2),Decimal('8.40'))
