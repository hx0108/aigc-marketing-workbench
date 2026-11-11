"""Server-issued edit quotes scoped to a specific draft and execution configuration."""
from fastapi import HTTPException


def calculate_quote(s, w, work):
    draft=work.data.get('draft',{});nodes=set()
    if draft.get('restore_revision_id'):
        return {'invalidated_nodes':['review','manifest'],'reused_nodes':['historical_media'],'affected_platforms':work.data['platforms'],'requires_authorization':False,'cost_upper_bound':0,'executable':True,'blockers':[],'expected_revision':work.revision}, None
    from .shot_edits import plan
    shot_nodes,dynamic_durations=plan(s,work,draft,include_durations=True)
    nodes.update(shot_nodes)
    for key in draft:
        nodes.update({'title':['copy','manifest'],'body':['copy','manifest'],'narration':['tts','subtitles','video_compose'],'voice':['tts','subtitles','video_compose'],'music':['video_compose'],'subtitle_style':['video_compose'],'poster_title':['poster_render'],'poster_points':['poster_render'],'poster_layout':['poster_render'],'asset_id':['video_compose']}.get(key,[]))
    free=not bool(nodes-{'copy','manifest'})
    if not nodes:return {'invalidated_nodes':[],'requires_authorization':False,'cost_upper_bound':0,'executable':False,'blockers':['NO_CHANGES'],'expected_revision':work.revision}, None
    if free:return {'invalidated_nodes':sorted(nodes),'requires_authorization':False,'cost_upper_bound':0,'executable':True,'blockers':[]}, None
    if draft.get('subtitle_style','default') not in {'default','large','small','dark_on_light'}:raise HTTPException(422,'不支持该字幕样式')
    if draft.get('music'):
        from .sources import authorized_music
        if not authorized_music(s,w,work.data.get('sku_id'),draft['music']):raise HTTPException(422,'配乐素材未授权或不属于当前商品')
    if nodes <= {'copy','manifest','poster_render','video_compose','static_clip','source_clip'}:
        operations=sorted({'video_render' if node=='video_compose' else node for node in nodes if node not in {'copy','manifest'}})
        authorization={'execution_mode':'local_only','allowed_operations':operations,'contract_version':'local-edit-v1'}
        quote={'invalidated_nodes':sorted(nodes),'requires_authorization':True,'cost_upper_bound':0,
               'executable':True,'blockers':[],'expected_revision':work.revision,'execution_mode':'local_only'}
        return quote,authorization
    try:
        from marketing_worker.business import readiness,authorization_snapshot
        blockers=readiness()
        if blockers:raise ValueError('PROVIDER_NOT_CONFIGURED')
        authorization=authorization_snapshot(w,work.data['creation_request_id'])
        from decimal import Decimal
        amount=Decimal(str(authorization['bounds']['tts'])) if 'tts' in nodes else Decimal('0')
        from .pricing import dynamic_bound
        amount += sum(dynamic_bound(authorization, duration) for duration in dynamic_durations)
        quote = {'invalidated_nodes':sorted(nodes),'requires_authorization':True,'cost_upper_bound':str(amount),'executable':True,'blockers':[],'price_version':authorization['price_version'],'budget_id':authorization['budget_id'],'expected_revision':work.revision}
        return quote, authorization
    except (ImportError,ValueError,KeyError) as error:
        blocker = {'invalid_minimax_video_duration':'INVALID_VIDEO_DURATION',
                   'dynamic_cost_exceeds_configured_bound':'DYNAMIC_COST_EXCEEDS_CONFIGURED_BOUND'}.get(str(error),'PRICE_NOT_CONFIGURED')
        return {'invalidated_nodes':sorted(nodes),'requires_authorization':True,'cost_upper_bound':None,'executable':False,'blockers':[blocker]}, None


def quote_scope(work, quote, authorization):
    return {'work_id': work.id, 'revision': work.revision,
            'current_result': work.data.get('current_result'),
            'draft': work.data.get('draft', {}), 'quote': quote, 'authorization': authorization}
