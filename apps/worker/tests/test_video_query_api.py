from decimal import Decimal

import httpx

from app import db
from app.db import Record
from app.execution import Budget, ExternalCall, Task
from app.ledger import prepare
from marketing_worker import business
from marketing_worker.http_providers import MiniMaxVideo
from test_core import client


def test_canceled_video_query_persists_status_without_changing_reservation(client, monkeypatch):
    call_id = 'call-video'
    intent = 'task:douyin/dynamic/0'
    remote_id = '123456'
    with db.Session.begin() as session:
        session.add_all([
            Budget(id='test-cap', workspace='one', cap=Decimal('10'), reserved=0, settled=0),
            Task(id='task', workspace='one', state='canceled', phase='creation_run', payload={}),
            ExternalCall(id=call_id, intent_key=intent, task_id='task', state='external_unknown', request_hash='request'),
            Record(id='remote:'+intent, workspace='one', kind='provider_result', data={
                'response': {'id': remote_id, 'model': 'MiniMax-H3'},
            }),
        ])
        session.flush()
        prepare(session, 'test-cap', call_id, 'request', '2.00')

    requests = []
    response_status = 200

    def provider(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(response_status, json={'task': {
            'id': remote_id, 'model': 'MiniMax-H3', 'status': 'succeeded',
            'content': {'url': 'https://example.invalid/private-video'},
        }})

    def save_remote(key, response):
        with db.Session.begin() as session:
            session.get(Record, 'remote:'+key).data = {'response': response}

    login = client.post('/api/v1/sessions', json={'username': 'tester', 'password': 'test-password-123'})
    headers = {'X-CSRF-Token': login.json()['csrf_token']}
    url = '/api/v1/tasks/task/actions'
    with httpx.Client(transport=httpx.MockTransport(provider)) as transport:
        config = {'workspace': 'one', 'video_query_price': '0', 'sessions': db.Session,
                  'providers': {'video': MiniMaxVideo('synthetic', 'https://api.minimax.cn', 'MiniMax-H3', client=transport)},
                  'save_remote': save_remote}
        monkeypatch.setattr(business, '_configuration', config)
        config['video_query_price'] = '0.01'
        blocked = client.post(url, headers=headers, json={'action': 'query'})
        assert blocked.status_code == 409
        assert requests == []

        config['video_query_price'] = '0'
        queried = client.post(url, headers=headers, json={'action': 'query'})
        assert queried.status_code == 200, queried.text
        assert requests == [('GET', '/v2/query/video_generation/'+remote_id)]
        assert 'private-video' not in queried.text

        response_status = 503
        unavailable = client.post(url, headers=headers, json={'action': 'query'})
        assert unavailable.status_code == 502
        assert unavailable.json()['detail']['code'] == 'VIDEO_QUERY_FAILED'

    detail = client.get('/api/v1/tasks/task').json()
    assert detail['video_checks'] == [{'call_id': call_id, 'status': 'succeeded'}]
    assert detail['execution_state'] == 'canceled'
    assert Decimal(detail['reserved_cost']) == Decimal('2.00')
    assert Decimal(detail['settled_cost']) == 0
    assert detail['unknown_cost_flag'] is True
