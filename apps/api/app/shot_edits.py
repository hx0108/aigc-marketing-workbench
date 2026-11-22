"""Deterministic shot patch validation and minimal recomputation plan."""
from fastapi import HTTPException
from hashlib import file_digest
from pathlib import Path
from .db import Record

KEYFRAME_FIELDS = ('first_frame_asset_id', 'last_frame_asset_id')

def reject(code):
    raise HTTPException(422, detail={'code': code})


def keyframe_assets(session, base, workspace, work_id, shot, root):
    from PIL import Image
    root = Path(root).resolve()
    frames = []
    for field in KEYFRAME_FIELDS:
        asset_id = shot[field]
        row = session.get(Record, asset_id) if asset_id in base.get('assets', []) else None
        if (not row or row.workspace != workspace or row.kind != 'asset'
                or row.data.get('work_id') != work_id or row.data.get('media_kind') != 'product_image'
                or row.data.get('review') != 'approved' or row.data.get('deleting')):
            reject('KEYFRAME_ASSET_REQUIRED')
        data = row.data
        try:
            key = data.get('repair_render_key') or data.get('release_object_key') or data['object_key']
            digest = data['repair_render_sha256'] if data.get('repair_render_key') else (
                data['release_sha256'] if data.get('release_object_key') else data['sha256'])
            path = (root / key).resolve()
            if not path.is_relative_to(root) or not 0 < path.stat().st_size <= 7*1024*1024:
                raise ValueError()
            with path.open('rb') as stream:
                if file_digest(stream, 'sha256').hexdigest() != digest:
                    raise ValueError()
            with Image.open(path) as image:
                short, long = sorted(image.size)
                if short < 256 or long > 5760 or 2*long > 5*short or image.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError()
                image.verify()
        except (KeyError, OSError, TypeError, ValueError, Image.DecompressionBombError):
            reject('KEYFRAME_ASSET_REQUIRED')
        if data.get('sample_marked') and key == data['object_key']:
            reject('KEYFRAME_ASSET_REQUIRED')
        frames.append({'path':str(path), 'sha256':digest})
    if frames[0]['sha256'] == frames[1]['sha256']:
        reject('KEYFRAME_PAIR_REQUIRED')
    return frames

def approved_repair(session,base,workspace,work_id,asset_id,slot):
    if asset_id not in base.get('assets',[]):return None
    asset=session.get(Record,asset_id)
    if not asset or asset.workspace!=workspace or asset.kind!='asset':return None
    data=asset.data
    if (data.get('work_id')==work_id and data.get('media_kind')=='product_image'
        and data.get('slot')==slot and data.get('repair_task_id') and data.get('review')=='approved'
        and not data.get('deleting') and data.get('repair_render_key') and data.get('repair_render_sha256')):
        return asset


def approved_replacement_video(session,base,workspace,work_id,platform,asset_id,root,*,inherited=False):
    if not isinstance(asset_id,str) or not asset_id or (not inherited and asset_id not in base.get('assets',[])):
        raise ValueError('replacement_video_asset_required')
    asset=session.get(Record,asset_id)
    if not asset or asset.workspace!=workspace or asset.kind!='asset':
        raise ValueError('replacement_video_asset_required')
    data=asset.data
    if (data.get('work_id')!=work_id or data.get('media_kind')!='video' or data.get('slot')!=platform
        or data.get('review')!='approved' or data.get('deleting')):
        raise ValueError('replacement_video_asset_required')
    if len(base.get('copy',{}).get(platform,{}).get('shots',[]))!=1:
        raise ValueError('replacement_video_requires_single_shot')
    try:
        root=Path(root).resolve()
        key=data.get('release_object_key') or data['object_key']
        digest=data.get('release_sha256') if data.get('release_object_key') else data['sha256']
        path=(root/key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError()
        with path.open('rb') as stream:
            if file_digest(stream,'sha256').hexdigest()!=digest:
                raise ValueError()
    except (KeyError,OSError,TypeError,ValueError):
        raise ValueError('replacement_video_hash_mismatch') from None
    return {'path':str(path),'sha256':digest},data.get('repair_source_ids',[])


def merge_shots(previous, incoming):
    if not isinstance(incoming, list):reject('INVALID_SHOT_CHANGES')
    seen=set()
    for item in incoming:
        if not isinstance(item, dict) or set(item)-{'index','narration','visual_description','asset_slot','repair_asset_id','video_source_id','start_seconds',*KEYFRAME_FIELDS}:reject('INVALID_SHOT_CHANGES')
        index=item.get('index')
        if type(index) is not int or index in seen:reject('INVALID_SHOT_INDEX')
        seen.add(index)
        if set(KEYFRAME_FIELDS) & item.keys():
            first, last = (item.get(field) for field in KEYFRAME_FIELDS)
            if (not all(field in item for field in KEYFRAME_FIELDS) or
                    (any(value is not None for value in (first,last)) and
                     (not all(isinstance(value,str) and 0 < len(value.strip()) <= 300 for value in (first,last)) or first == last))):
                reject('KEYFRAME_PAIR_REQUIRED')
        if 'video_source_id' in item and {'asset_slot','repair_asset_id','visual_description'} & item.keys():
            reject('VIDEO_SOURCE_CONFLICT')
        if ('start_seconds' in item)!=('video_source_id' in item):
            reject('VIDEO_SOURCE_TRIM_INVALID')
        for key,value in item.items():
            if key=='index' or key in KEYFRAME_FIELDS:continue
            if key=='start_seconds':
                if type(value) not in (int,float):reject('VIDEO_SOURCE_TRIM_INVALID')
                continue
            if not isinstance(value,str) or not value.strip():reject('INVALID_SHOT_VALUE')
            if key=='asset_slot' and value not in {'white','scene_1','scene_2'}:reject('INVALID_ASSET_SLOT')
    merged={item['index']:dict(item) for item in previous}
    for item in incoming:
        prior=merged.get(item['index'],{})
        if 'asset_slot' in item and 'repair_asset_id' not in item:
            prior.pop('repair_asset_id',None)
        if {'asset_slot','repair_asset_id','visual_description'} & item.keys():
            prior.pop('video_source_id',None)
            prior.pop('start_seconds',None)
        if 'video_source_id' in item:
            for field in ('asset_slot','repair_asset_id','visual_description'):
                prior.pop(field,None)
        patch = {**prior,**item}
        if patch.get('first_frame_asset_id') and ('video_source_id' in patch or 'repair_asset_id' in patch):
            reject('KEYFRAME_VIDEO_SOURCE_CONFLICT')
        merged[item['index']]=patch
    return [merged[index] for index in sorted(merged)]


def plan(session,work,draft,*,include_durations=False,keyframe_bindings=None):
    if not {'shots','narration','asset_id','shot_motion_indices'} & draft.keys():return set(),[] if include_durations else 0
    current=session.get(Record,work.data.get('current_result'))
    if not current or current.workspace!=work.workspace or current.kind!='result_revision' or current.data.get('work_id')!=work.id:reject('CURRENT_RESULT_UNAVAILABLE')
    base=current.data
    platform=draft.get('platform') or work.data['platforms'][0]
    content=base.get('copy',{}).get(platform,{})
    shots=content.get('shots',[])
    patches=merge_shots([],draft.get('shots',[]))
    visual=set();narration=False;revert_to_prior=False
    projected=[dict(shot) for shot in shots]
    settings=base.get('render_settings',{}).get(platform,{})
    uploaded={}
    prior_video=settings.get('shot_video_sources',{})
    motion=draft.get('shot_motion_indices',[])
    if not isinstance(motion,list) or len(motion)>1 or any(type(i) is not int or not 0<=i<len(shots) for i in motion):
        reject('INVALID_SHOT_INDEX')
    if motion:
        index=motion[0]
        original_id=work.data.get('creation_request_id')
        original=session.get(Record,original_id) if original_id else None
        if (not original or original.workspace!=work.workspace or original.kind!='creation_request'
            or original.data.get('creative_mode')!='photo_campaign' or not original.data.get('wear_source_id')
            or index!=0 or shots[index].get('asset_slot')!=settings.get('poster_scene')
            or str(index) in prior_video or str(index) in settings.get('shot_repair_sources',{})
            or any(p['index']==index and set(p)-{'index','narration'} for p in patches)):
            reject('WEARING_SHOT_REQUIRED')
        visual.add(index)
        if any(approved_repair(session,base,work.workspace,work.id,asset_id,settings['poster_scene'])
               for asset_id in base.get('assets',[])):
            reject('WEARING_SHOT_REQUIRED')
    for item in patches:
        index=item['index']
        if not 0<=index<len(shots):reject('INVALID_SHOT_INDEX')
        for key,value in item.items():
            if key in {'index','repair_asset_id','video_source_id','start_seconds'} or shots[index].get(key)==value:continue
            projected[index][key]=value
            if key=='narration':narration=True
            else:visual.add(index)
        if repair_id:=item.get('repair_asset_id'):
            slot=projected[index].get('asset_slot',settings.get('poster_scene','scene_1'))
            if not approved_repair(session,base,work.workspace,work.id,repair_id,slot):
                reject('APPROVED_REPAIR_RENDER_SOURCE_REQUIRED')
            visual.add(index)
        if 'video_source_id' in item:
            if projected[index].get('first_frame_asset_id'):
                reject('KEYFRAME_VIDEO_SOURCE_CONFLICT')
            from .sources import authorized_video_clip
            try:uploaded[index]=authorized_video_clip(session,work.workspace,work.data.get('sku_id'),
                item['video_source_id'],item['start_seconds'],shots[index]['duration'])
            except ValueError as error:reject(str(error).upper())
            visual.add(index)
        elif str(index) in prior_video and {'asset_slot','repair_asset_id','visual_description'} & item.keys():
            revert_to_prior=True
    if draft.get('asset_id',settings.get('asset_id')) and (visual or narration or revert_to_prior):reject('SHOT_EDIT_CONFLICTS_WITH_FULL_VIDEO_REPLACEMENT')
    if 'asset_id' in draft and draft['asset_id'] is not None:
        from .sources import ROOT
        try:approved_replacement_video(session,base,work.workspace,work.id,platform,draft['asset_id'],ROOT)
        except ValueError as error:reject(str(error).upper())
    if 'narration' in draft:
        value=draft['narration']
        if not isinstance(value,str) or not value.strip():reject('INVALID_SHOT_VALUE')
        if len(shots)>1 and value!=''.join(shot.get('narration','') for shot in projected):reject('NARRATION_REQUIRES_SHOT_MAPPING')
    nodes=set()
    if narration:nodes.update({'tts','subtitles','video_compose'})
    if revert_to_prior:nodes.add('video_compose')
    dynamic_durations=[]
    for index in sorted(visual):
        if index in uploaded:
            nodes.update({'source_clip','video_compose'})
            continue
        key=f'{platform}/static/{index}'
        owner=base.get('step_sources',{}).get(key,base.get('source_task_id'))
        if not owner and base.get('assets'):owner=base['assets'][0].split(':result:')[0]
        row=session.get(Record,str(owner)+':'+key)
        static=row and row.workspace==work.workspace and row.data.get('state')=='succeeded'
        if projected[index].get('first_frame_asset_id'):
            from .sources import ROOT
            if static or str(index) in prior_video or any(p['index']==index and p.get('repair_asset_id') for p in patches):
                reject('KEYFRAME_VIDEO_SOURCE_CONFLICT')
            duration = projected[index].get('duration')
            if type(duration) not in (int,float) or not 4 <= duration <= 15 or duration != int(duration):
                reject('KEYFRAME_DURATION_UNSUPPORTED')
            frames = keyframe_assets(session,base,work.workspace,work.id,projected[index],ROOT)
            if keyframe_bindings is not None:
                keyframe_bindings[str(index)] = [frame['sha256'] for frame in frames]
            nodes.add('keyframes')
        if static and index in motion:reject('WEARING_SHOT_REQUIRED')
        nodes.add('static_clip' if static else 'dynamic')
        nodes.add('video_compose')
        if not static:dynamic_durations.append(projected[index].get('duration'))
    return nodes,dynamic_durations if include_durations else len(dynamic_durations)
