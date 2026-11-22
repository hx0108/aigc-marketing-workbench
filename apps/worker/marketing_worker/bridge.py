import hashlib
import os
from pathlib import Path
from .media import compose_timeline, narration_duration, pad_narration, render_poster, VoiceDurationMismatch
from .pipeline import Pipeline
from .persistence import StepStore, AuthorizedServices


def local_render_font():
    candidates = [os.getenv('AIGC_RENDER_FONT'), '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 'C:/Windows/Fonts/msyh.ttc']
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise ValueError('local_render_font_required')


class RenderBridge:
    def __init__(self, private_root, font, *, output_root=None):
        self.root, self.font = Path(private_root).resolve(), font
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_root = self.root if output_root is None else Path(output_root).resolve()
        if not self.output_root.is_relative_to(self.root):
            raise ValueError('asset_outside_private_storage')

    def path(self, intent, extension):
        return self.output_root / (hashlib.sha256(intent.encode()).hexdigest() + extension)

    def input_path(self, asset):
        path = Path(asset['path']).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('asset_outside_private_storage')
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('asset_hash_mismatch')
        return path

    def poster(self, payload, intent):
        source = payload['images'][payload.get('image_slot','white')]
        image = self.input_path(source)
        copy = payload['copy']
        if platform := payload.get('campaign_platform'):
            from .campaign_media import poster
            args = (image, platform, copy['poster_title'], copy.get('selling_points', []), self.font)
            sample = poster(*args, self.path(intent,'.png'), internal_sample=True, scene_kind=source.get('scene_kind'))
            release = poster(*args, self.path(intent+'/release','.png'), internal_sample=False, scene_kind=source.get('scene_kind'))
            return {**sample, 'release': release, 'sample_marked': True}
        detail = self.input_path(payload['images']['white']) if copy.get('visual_plan') and payload['images'].get('white') else None
        sample=render_poster(image, self.path(intent, '.png'), copy['poster_title'], copy.get('selling_points', []), self.font,layout=payload.get('layout','classic'),creative_plan=copy.get('visual_plan'),detail_product=detail)
        release=render_poster(image,self.path(intent+'/release','.png'),copy['poster_title'],copy.get('selling_points',[]),self.font,layout=payload.get('layout','classic'),internal_sample=False,creative_plan=copy.get('visual_plan'),detail_product=detail)
        return {**sample,'release':release}

    def video(self, payload, intent):
        clips = [self.input_path(clip) for clip in payload['clips']]
        source_voice = self.input_path(payload['voice'])
        duration = float(payload['duration'])
        original_duration = narration_duration(source_voice)
        if original_duration > duration:
            raise VoiceDurationMismatch()
        voice = source_voice
        alignment = {'mode':'unchanged','source_seconds':original_duration,'target_seconds':duration,
            'source_sha256':payload['voice']['sha256']}
        if original_duration < duration:
            voice = self.path(f"{intent}/voice-padding/{payload['voice']['sha256']}/{duration}", '.wav')
            pad_narration(source_voice, voice, duration)
            alignment.update(mode='tail_silence', render_sha256=hashlib.sha256(voice.read_bytes()).hexdigest())
        music = self.input_path(payload['music']) if payload.get('music') else None
        arguments = (duration, payload['copy']['shots'], music, payload.get('subtitle_style','default'))
        output = self.path(intent, '.mp4')
        finish = compose_timeline
        options = {'font_path': self.font, 'creative_copy': payload['copy']}
        if platform := payload.get('campaign_platform'):
            from .campaign_finish import compose_campaign
            finish = compose_campaign
            options.update(platform=platform, creative_copy={**payload['copy'], 'product_name':payload.get('product_name',''),
                                                           'wearing_campaign':bool(payload.get('wearing_campaign'))})
        finish(clips, voice, output, *arguments, **options)
        release = self.path(intent+'/release', '.mp4')
        finish(clips, voice, release, *arguments, internal_sample=False, **options)
        return {'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'sample_marked':True,
            'voice_alignment':alignment,'release':{'path':str(release),'sha256':hashlib.sha256(release.read_bytes()).hexdigest()}}


def creation_handler(repository, job, services_factory):
    request = dict(job['payload']['request'])
    request['facts'] = request.get('facts', request.get('profile_snapshot', {}).get('facts', []))
    store = StepStore(repository.sessions, job['workspace'], job['fencing_token'])
    services = services_factory(job)
    result = Pipeline(store, services).execute(job['id'], request)
    if hasattr(services, 'persist_result'):
        return services.persist_result(job, result)
    return result
