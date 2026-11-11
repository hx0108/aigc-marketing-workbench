import copy
from pathlib import Path
from app.db import Record
from .pipeline import Pipeline
from .persistence import StepStore
from .business import persist_result


def edit_handler(repository,job,services_factory):
    payload=job['payload']; draft=payload['draft']; platform=draft['platform']
    base=payload['base_result']
    render_settings=copy.deepcopy(base.get('render_settings',{}))
    settings=render_settings.setdefault(platform,{})
    for key in ('voice','music','subtitle_style','asset_id','poster_layout'):
        if key in draft:settings[key]=draft[key]
    services=services_factory(job)
    store=StepStore(repository.sessions,job['workspace'],job['fencing_token'])
    pipeline=Pipeline(store,services)
    content=copy.deepcopy(base['copy'][platform])
    shot_changes=draft.get('shots',[])
    from fastapi import HTTPException
    from app.shot_edits import merge_shots
    try:shot_changes=merge_shots([],shot_changes)
    except HTTPException as error:raise ValueError(error.detail['code'].lower()) from None
    uploaded={}; reverted_sources=set(); shot_video_sources=dict(settings.get('shot_video_sources',{}))
    changed_visual=set(); changed_narration=False; seen=set()
    for change in shot_changes:
        index=change.get('index')
        if type(index) is not int or index in seen or not 0<=index<len(content['shots']):raise ValueError('invalid_shot_index')
        seen.add(index)
        if 'video_source_id' in change:
            uploaded[index]=change
            changed_visual.add(index)
        elif {'asset_slot','repair_asset_id','visual_description'} & change.keys() and str(index) in shot_video_sources:
            shot_video_sources.pop(str(index))
            reverted_sources.add(index)
        for key,value in change.items():
            if key in {'index','video_source_id','start_seconds'}:continue
            if not isinstance(value,str) or not value.strip():raise ValueError('invalid_shot_value')
            if key=='repair_asset_id':
                changed_visual.add(index)
                continue
            if key=='asset_slot' and value not in ('white','scene_1','scene_2'):raise ValueError('invalid_asset_slot')
            if content['shots'][index].get(key)==value:continue
            content['shots'][index][key]=value
            if key=='narration':changed_narration=True
            else:changed_visual.add(index)
    if changed_narration:content['narration']=''.join(shot['narration'] for shot in content['shots'])
    if settings.get('asset_id') and (changed_visual or changed_narration or reverted_sources):
        raise ValueError('shot_edit_conflicts_with_full_video_replacement')
    for field in ('title','body','poster_title','narration'):
        if field in draft:content[field]=draft[field]
    if 'narration' in draft:
        if not isinstance(content['narration'],str) or not content['narration'].strip():
            raise ValueError('invalid_shot_value')
        if len(content['shots'])==1:
            content['shots'][0]['narration']=content['narration']
        elif content['narration']!=''.join(shot.get('narration','') for shot in content['shots']):
            raise ValueError('narration_requires_shot_mapping')
    if 'poster_points' in draft:
        points=draft['poster_points']
        content['selling_points']=[points.strip()] if isinstance(points,str) and points.strip() else points or []
    branches=copy.deepcopy(base['branches'])
    step_sources=dict(base.get('step_sources',{}))
    for index in reverted_sources:
        step_sources.pop(f'{platform}/source_clip/{index}',None)
    poster_copy_changed='poster_title' in draft or 'poster_points' in draft
    video=bool(changed_visual or changed_narration or reverted_sources) or any(key in draft for key in ('narration','voice','music','subtitle_style','asset_id'))
    with repository.sessions() as session:
        from app.shot_edits import approved_repair, approved_replacement_video
        from app.sources import authorized_video_clip
        source_inputs={}
        if video and (uploaded or shot_video_sources):
            work=session.get(Record,payload['work_id'])
            if not work or work.workspace!=job['workspace'] or work.kind!='work' or work.data.get('deleting'):
                raise ValueError('video_source_required')
            for index, change in uploaded.items():
                clip=authorized_video_clip(session,job['workspace'],work.data.get('sku_id'),
                    change['video_source_id'],change['start_seconds'],content['shots'][index]['duration'])
                source_inputs[index]=clip
                shot_video_sources[str(index)]={field:clip[field] for field in ('source_id','start_seconds','revision','sha256')}
            for index, reference in shot_video_sources.items():
                if int(index) in uploaded:continue
                clip=authorized_video_clip(session,job['workspace'],work.data.get('sku_id'),reference['source_id'],
                    reference['start_seconds'],content['shots'][int(index)]['duration'])
                if clip['revision']!=reference['revision'] or clip['sha256']!=reference['sha256']:
                    raise ValueError('video_source_version_changed')
        replacement=None
        if video and settings.get('asset_id') is not None:
            replacement=approved_replacement_video(session,base,job['workspace'],payload['work_id'],platform,
                settings['asset_id'],services.private_root,inherited='asset_id' not in draft)
        for change in shot_changes:
            if repair_id:=change.get('repair_asset_id'):
                slot=content['shots'][change['index']].get('asset_slot',settings.get('poster_scene','scene_1'))
                if not approved_repair(session,base,job['workspace'],payload['work_id'],repair_id,slot):
                    raise ValueError('approved_repair_render_source_required')
        if shot_changes or poster_copy_changed:
            profile=session.get(Record,payload.get('profile_id',job['payload'].get('request',{}).get('profile_id')))
            if not profile or profile.workspace!=job['workspace'] or profile.data.get('status')!='confirmed':raise ValueError('confirmed_profile_required')
            from .fact_validation import validate_numeric_claims
            facts=profile.data['facts']
            facts={str(key):{'id':str(key),'value':value,'validity':'active'} for key,value in facts.items()} if isinstance(facts,dict) else {fact['id']:fact for fact in facts}
            for change in shot_changes:
                shot=content['shots'][change['index']]
                for field in ('narration','visual_description'):
                    if field in change:validate_numeric_claims(shot[field],shot.get('fact_refs',[]),facts)
            if poster_copy_changed:
                refs=content.get('fact_refs',[])
                for text in [content['poster_title'],*content.get('selling_points',[])]:
                    validate_numeric_claims(text,refs,facts)
        original_task=base.get('source_task_id',base['assets'][0].split(':result:')[0])
        def prior(key):
            owner=base.get('step_sources',{}).get(key,original_task)
            row=session.get(Record,owner+':'+key)
            if not row or row.workspace!=job['workspace'] or row.data['state']!='succeeded':
                raise ValueError('reusable_step_missing')
            return row.data['result']
        images={slot:prior('image/'+slot) for slot in ('white','scene_1','scene_2')}
        poster=any(key in draft for key in ('poster_title','poster_points','poster_layout'))
        repair_sources={}
        if poster or changed_visual:
            slots={content['shots'][index].get('asset_slot',settings.get('poster_scene','scene_1')) for index in changed_visual if index not in uploaded}
            if poster:slots.add(settings.get('poster_scene','white'))
            for asset_id in base['assets']:
                asset=session.get(Record,asset_id)
                if not asset or asset.workspace!=job['workspace'] or asset.kind!='asset' or asset.data.get('work_id')!=payload['work_id']:
                    continue
                data=asset.data
                slot=data.get('slot')
                if data.get('media_kind')!='product_image' or not data.get('repair_task_id') or slot not in slots:
                    continue
                if data.get('review')!='approved' or data.get('deleting') or not data.get('repair_render_key'):
                    raise ValueError('approved_repair_render_source_required')
                images[slot]={'path':str(Path(services.private_root)/data['repair_render_key']),'sha256':data['repair_render_sha256']}
                repair_sources[slot]=asset.id
        if poster:
            image_slot=settings.get('poster_scene','white')
            result=pipeline.step(job['id'],platform+'/poster','poster_render',{'copy':content,'images':images,'platform':platform,'layout':settings.get('poster_layout','classic'),'image_slot':image_slot})
            if image_slot in repair_sources:
                result={**result,'repair_source_ids':[repair_sources[image_slot]]}
            branches[platform]['poster']={'state':'awaiting_review','result':result}
        if video:
            clips=[]
            shot_sources=dict(settings.get('shot_repair_sources',{}))
            for index in range(len(content['shots'])):
                if str(index) in shot_video_sources:
                    key=f'{platform}/source_clip/{index}'
                    if index in uploaded:
                        source=source_inputs[index]
                        clips.append(pipeline.step(job['id'],key,'source_clip',{'source':source,
                            'start_seconds':source['start_seconds'],'duration':float(content['shots'][index]['duration'])}))
                        step_sources[key]=job['id']
                    else:clips.append(prior(key))
                    continue
                static_key=f'{platform}/static/{index}'
                owner=base.get('step_sources',{}).get(static_key,original_task)
                static=session.get(Record,owner+':'+static_key)
                key=static_key if static and static.workspace==job['workspace'] and static.data.get('state')=='succeeded' else f'{platform}/dynamic/{index}'
                if index in changed_visual:
                    shot={'asset_slot':settings.get('poster_scene','scene_1'),**content['shots'][index]}
                    clips.append(pipeline.step(job['id'],key,'static_clip' if key==static_key else 'dynamic',{'shot':shot,'images':images,'platform':platform}))
                    shot_sources.pop(str(index),None)
                    if shot['asset_slot'] in repair_sources:
                        shot_sources[str(index)]=repair_sources[shot['asset_slot']]
                    step_sources[key]=job['id']
                else:clips.append(prior(key))
            voice=prior(platform+'/voice')
            if changed_narration or 'voice' in draft or 'narration' in draft:
                voice=pipeline.step(job['id'],platform+'/voice','tts',{'text':content['narration'],'voice':settings.get('voice','Cherry')})
            settings['shot_repair_sources']=shot_sources
            settings['shot_video_sources']=shot_video_sources
            video_repair_sources={source_id for index,source_id in shot_sources.items() if index not in shot_video_sources}
            if replacement:
                clip, source_ids=replacement
                clips=[clip]
                video_repair_sources=set(source_ids)
            music=None
            if settings.get('music'):
                from app.sources import authorized_music
                work=session.get(Record,payload['work_id'])
                music_asset=authorized_music(session,job['workspace'],work.data.get('sku_id') if work else None,settings['music'])
                if not music_asset:
                    raise ValueError('authorized_music_asset_required')
                music={'path':str(Path(services.private_root)/music_asset.data['object_key']),'sha256':music_asset.data['sha256']}
            duration=sum(float(shot['duration']) for shot in content['shots'])
            result=pipeline.step(job['id'],platform+'/video','video_render',{'clips':clips,'voice':voice,'duration':duration,'copy':content,'music':music,'subtitle_style':settings.get('subtitle_style','default')})
            settings.pop('voice_alignment',None)
            if alignment:=result.get('voice_alignment'):
                settings['voice_alignment']=alignment
            if video_repair_sources:
                result={**result,'repair_source_ids':sorted(video_repair_sources)}
            branches[platform]['video']={'state':'awaiting_review','result':result}
    copies={**base['copy'],platform:content}
    if changed_narration or 'voice' in draft or 'narration' in draft:step_sources[platform+'/voice']=job['id']
    refreshed_slots=[]
    if poster:refreshed_slots.append(('marketing_poster',platform))
    if video:refreshed_slots.append(('cover',platform))
    return persist_result(repository.sessions,job,{'images':images,'platforms':branches,'copy':copies,'source_task_id':original_task,'step_sources':step_sources,'render_settings':render_settings,'refreshed_slots':refreshed_slots},services.private_root)


def rewrite_handler(repository,job,services_factory):
    services=services_factory(job)
    payload=job['payload']
    with repository.sessions() as session:
        profile=session.get(Record,payload['profile_id'])
        if not profile or profile.workspace!=job['workspace'] or profile.data.get('status')!='confirmed':
            raise ValueError('confirmed_profile_required')
        facts=profile.data['facts']
    result=services.invoke('text',{'instruction':payload['instruction'],'platforms':[payload['platform']],'facts':facts,'purpose':'copy_rewrite'},job['id']+':rewrite')
    platform=payload['platform']
    candidate=result.get(platform,{})
    from .fact_validation import validate_numeric_claims
    fact_map={str(key):{'id':str(key),'value':value,'validity':'active'} for key,value in facts.items()} if isinstance(facts,dict) else {fact['id']:fact for fact in facts}
    refs=candidate.get('fact_refs',[])
    if not isinstance(refs,list) or not all(isinstance(ref,str) for ref in refs):raise ValueError('invalid_fact_reference')
    changes={key:candidate[key] for key in ('title','body','narration') if isinstance(candidate.get(key),str)}
    if not changes:raise ValueError('empty_copy_candidate')
    for value in changes.values():validate_numeric_claims(value,refs,fact_map)
    with repository.sessions.begin() as session:
        session.add(Record(id=job['id']+':candidate',workspace=job['workspace'],kind='copy_candidate',data={'work_id':payload['work_id'],'platform':platform,'base_draft_revision':payload['base_draft_revision'],'changes':changes}))
    return {'candidate_id':job['id']+':candidate'}
