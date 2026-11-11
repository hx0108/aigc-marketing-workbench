"""Persistent step orchestration; services own authorized external calls and storage."""
from decimal import Decimal, InvalidOperation
from .fact_validation import validate_numeric_claims, visual_numeric_text
from .platform_style import STYLES, poster_slot


class ContractError(ValueError):
    pass


def failure_details(error):
    from .http_providers import ProviderRejected, ExternalUnknown
    result={'code':getattr(error,'code',type(error).__name__)}
    if isinstance(error,ProviderRejected):
        if error.status_code is not None:result['provider_status']=error.status_code
        if error.provider_code is not None:result['provider_code']=error.provider_code
    if isinstance(error,ExternalUnknown):
        if error.status_code is not None:result['provider_status']=error.status_code
        if error.transport_error is not None:result['transport_error']=error.transport_error
    return result


def validate_copy(copy, request):
    platforms = request['platforms']
    if not isinstance(copy, dict) or set(copy) != set(platforms):
        raise ContractError('platform_mismatch')
    facts = {fact['id'] for fact in request['facts'] if fact.get('validity') == 'active'}
    for platform in platforms:
        item = copy[platform]
        if not isinstance(item, dict):
            raise ContractError('copy_fields_required')
        if set(item) - {'title','body','narration','poster_title','selling_points','shots','fact_refs','marketing_angle','audience','objective','platform_expression','creative_rationale','visual_plan'}:
            raise ContractError('unknown_copy_field')
        for field in ('marketing_angle','audience','objective','platform_expression','creative_rationale'):
            if field in item and (not isinstance(item[field],str) or not 0<len(item[field].strip())<=500):
                raise ContractError('invalid_creative_field')
        if 'visual_plan' in item:
            from .creative_direction import validate_plan
            validate_plan(item['visual_plan'],request['facts'],platform)
        points=item.get('selling_points', [])
        if not isinstance(points,list) or len(points)>8 or not all(isinstance(point,str) and 0<len(point)<=200 for point in points):
            raise ContractError('invalid_selling_points')
        if 'fact_refs' in item and (not isinstance(item['fact_refs'],list) or not item['fact_refs'] or not all(isinstance(ref,str) for ref in item['fact_refs']) or not set(item['fact_refs'])<=facts):
            raise ContractError('invalid_fact_reference')
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in ('title', 'body', 'narration', 'poster_title')):
            raise ContractError('copy_fields_required')
        shots = item.get('shots', [])
        if not isinstance(shots, list) or not shots:
            raise ContractError('shots_required')
        durations = []
        for shot in shots:
            if not isinstance(shot, dict) or isinstance(shot.get('duration'), bool):
                raise ContractError('invalid_shot_duration')
            if set(shot) - {'duration','narration','fact_refs','visual_description','asset_slot'}:
                raise ContractError('unknown_shot_field')
            if 'asset_slot' in shot and shot['asset_slot'] not in ('white','scene_1','scene_2'):
                raise ContractError('invalid_asset_slot')
            if 'visual_description' in shot and (not isinstance(shot['visual_description'],str) or not 0<len(shot['visual_description'].strip())<=1000):
                raise ContractError('invalid_visual_description')
            if 'narration' in shot and (not isinstance(shot['narration'],str) or not shot['narration'].strip()):
                raise ContractError('invalid_shot_narration')
            try:
                duration = Decimal(str(shot.get('duration')))
            except InvalidOperation:
                raise ContractError('invalid_shot_duration') from None
            if not duration.is_finite() or duration <= 0:
                raise ContractError('invalid_shot_duration')
            durations.append(duration)
        if sum(durations) != Decimal(str(request['duration_seconds'])):
            raise ContractError('shot_duration_mismatch')
        for shot in shots:
            refs = shot.get('fact_refs')
            if not isinstance(refs, list) or not refs or not all(isinstance(ref,str) for ref in refs) or not set(refs) <= facts:
                raise ContractError('invalid_fact_reference')
            validate_numeric_claims(shot.get('narration',''),refs,{fact['id']:fact for fact in request['facts']})
            validate_numeric_claims(visual_numeric_text(shot.get('visual_description','')),refs,{fact['id']:fact for fact in request['facts']})
        global_refs=item.get('fact_refs',[])
        for text in [item['title'],item['body'],item['narration'],item['poster_title'],*points]:
            validate_numeric_claims(text,global_refs,{fact['id']:fact for fact in request['facts']})
    if len(platforms)==2:
        first,second=(copy[platform] for platform in platforms)
        for field in ('title','body','narration'):
            if ''.join(ch for ch in first[field].casefold() if ch.isalnum())==''.join(ch for ch in second[field].casefold() if ch.isalnum()):
                raise ContractError('duplicate_platform_'+field)
    return copy


class Pipeline:
    def __init__(self, store, services):
        self.store, self.services = store, services

    def step(self, task_id, key, kind, payload):
        old = self.store.read(task_id, key)
        if old and old['state'] == 'succeeded':
            return old['result']
        if old and old['state'] in ('submitting', 'external_unknown'):
            raise ContractError('reconciliation_required')
        if self.store.canceled(task_id):
            raise ContractError('canceled')
        self.store.write(task_id, key, 'submitting', None)
        try:
            result = self.services.invoke(kind, payload, task_id + ':' + key)
        except Exception as error:
            state = 'external_unknown' if getattr(error, 'code', '') == 'external_unknown' else 'failed'
            self.store.write(task_id, key, state, failure_details(error))
            raise
        self.store.write(task_id, key, 'succeeded', result)
        return result

    def execute(self, task_id, request):
        copy = request.get('manual_copy')
        if copy is None:
            copy = self.step(task_id, 'copy', 'text', request)
        copy = validate_copy(copy, request)
        platforms=request['platforms']
        resolved={}
        for platform,content in copy.items():
            scene=poster_slot(platform,platforms)
            shots=[]
            for index,shot in enumerate(content['shots']):
                slot=shot.get('asset_slot',scene)
                if len(platforms)==2 and (index==0 or slot!='white'):
                    slot=scene
                shots.append({**shot,'asset_slot':slot})
            from .creative_direction import resolved_plan
            resolved[platform]={**content,'shots':shots,'visual_plan':resolved_plan(content,request['facts'],platform)}
        copy=resolved
        images = {}
        for slot in ('white', 'scene_1', 'scene_2'):
            images[slot] = self.step(task_id, 'image/' + slot, 'product_image', {'slot': slot, 'request': request, 'copy':copy})
        result = {'images': images, 'platforms': {}, 'copy':copy, 'render_settings':{}}
        for platform in request['platforms']:
            content = copy[platform]
            layout=STYLES[platform]['layout']
            scene=poster_slot(platform,request['platforms'])
            result['render_settings'][platform]={'poster_layout':layout,'poster_scene':scene,'visual_plan':content['visual_plan']}
            branches = {}
            for branch in ('video', 'poster'):
                try:
                    if branch == 'video':
                        clips = []
                        for index, shot in enumerate(content['shots']):
                            fallback=f'{platform}/{index}' in request.get('static_fallback_shots',[])
                            clips.append(self.step(task_id, f'{platform}/'+('static' if fallback else 'dynamic')+f'/{index}', 'static_clip' if fallback else 'dynamic', {'shot': shot, 'images': images,'platform':platform,'visual_plan':content['visual_plan'],'facts':request['facts']}))
                        voice = self.step(task_id, f'{platform}/voice', 'tts', {'text': content['narration']})
                        output = self.step(task_id, f'{platform}/video', 'video_render', {'clips': clips, 'voice': voice, 'duration': request['duration_seconds'], 'copy': content})
                        if alignment := output.get('voice_alignment'):
                            result['render_settings'][platform]['voice_alignment'] = alignment
                    else:
                        output = self.step(task_id, f'{platform}/poster', 'poster_render', {'copy': content, 'images': images, 'platform': platform,'layout':layout,'image_slot':scene})
                    branches[branch] = {'state': 'awaiting_review', 'result': output}
                except Exception as error:
                    if getattr(error,'code','')=='paused':raise
                    branches[branch] = {'state': 'external_unknown' if getattr(error, 'code', '') == 'external_unknown' else 'failed', **failure_details(error)}
            result['platforms'][platform] = branches
        return result
