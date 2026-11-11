import hashlib
from pathlib import Path
from .media import compose_timeline, narration_duration, pad_narration, render_poster, VoiceDurationMismatch
from .pipeline import Pipeline
from .persistence import StepStore, AuthorizedServices


class RenderBridge:
    def __init__(self, private_root, font):
        self.root, self.font = Path(private_root).resolve(), font
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, intent, extension):
        return self.root / (hashlib.sha256(intent.encode()).hexdigest() + extension)

    def input_path(self, asset):
        path = Path(asset['path']).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('asset_outside_private_storage')
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('asset_hash_mismatch')
        return path

    def poster(self, payload, intent):
        image = self.input_path(payload['images'][payload.get('image_slot','white')])
        copy = payload['copy']
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
        compose_timeline(clips, voice, output, *arguments, font_path=self.font,creative_copy=payload['copy'])
        release = self.path(intent+'/release', '.mp4')
        compose_timeline(clips, voice, release, *arguments, internal_sample=False, font_path=self.font,creative_copy=payload['copy'])
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
