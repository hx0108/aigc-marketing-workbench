"""Trusted operator JSON configuration, with narrowly scoped credential loading."""
import json
import base64
import hashlib
from PIL import Image
from pathlib import Path
from .factory import build_providers, provider_adapters
from .business import configure
from app.db import Record, Session

KEYS={'DEEPSEEK_API_KEY','MINIMAX_API_KEY','DASHSCOPE_API_KEY'}


def verify_consent(session, job, settings):
    payload=job['payload']
    request=payload.get('request',{})
    identifier=payload.get('consent_id') or request.get('consent_id')
    consent=session.get(Record,identifier) if identifier else None
    if not consent or consent.workspace!=job['workspace'] or consent.kind!='processing_consent':
        raise ValueError('processing_consent_required')
    expected={key:settings.get(key) for key in ('price_version','budget_id','consent_version','bounds')}
    expected['providers']={key:value['model'] for key,value in settings['providers'].items()}
    adapters=provider_adapters(expected['providers'].get('video'))
    expected['provider_parameters']={key:{**adapters[key].defaults,**value.get('parameters',{})} for key,value in settings['providers'].items()}
    if any(consent.data.get(key)!=value for key,value in expected.items()):
        raise ValueError('authorization_scope_changed')
    scope={**request,**payload}
    if 'request_id' not in scope and payload.get('work_id'):
        work=session.get(Record,payload['work_id'])
        if not work or work.workspace!=job['workspace'] or work.kind!='work' or work.data.get('deleting'):
            raise ValueError('consent_scope_mismatch')
        scope['request_id']=work.data.get('creation_request_id')
    for key in ('request_id','work_id','source_ids','platforms','duration_seconds','base_result_id','base_draft_revision','draft','platform','instruction','quote_id'):
        if key in consent.data and consent.data[key]!=scope.get(key):
            raise ValueError('consent_scope_mismatch')
    profile_id=payload.get('profile_id') or request.get('profile_id')
    profile=session.get(Record,profile_id) if profile_id else None
    if not profile or profile.workspace!=job['workspace'] or profile.kind!='profile' or profile.data.get('status')!='confirmed' or profile.data.get('deleting'):
        raise ValueError('fact_revoked')
    if consent.data.get('profile_id')!=profile_id:
        raise ValueError('consent_scope_mismatch')


def read_credentials(path):
    values={}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key,value=line.split('=',1)
        key=key.strip()
        if key in KEYS:
            values[key]=value.strip().strip('"').strip("'")
    if not KEYS <= values.keys():
        raise ValueError('required_credentials_missing')
    return values


def load_configuration(path, sessions=Session):
    settings=json.loads(Path(path).read_text(encoding='utf-8'))
    from .media import timeline_font_options
    timeline_font_options(settings.get('font'))
    providers=build_providers(settings['providers'],read_credentials(settings['credentials_file']))
    def source_factory(job):
        from .source_resolver import resolve_sources
        return resolve_sources(sessions,job,settings['private_root'],settings.get('sources',{}))
    def policy_factory(job):
        def policy(kind,payload,intent):
            if not settings['enabled'] or job['workspace'] != settings['workspace'] or not intent.startswith(job['id']+':'):
                raise ValueError('consent_scope_mismatch')
            if kind not in settings['authorized_operations']:
                raise ValueError('operation_not_authorized')
            with sessions() as session:
                verify_consent(session,job,settings)
        return policy
    def save_remote(intent,response):
        with sessions.begin() as session:
            identifier='remote:'+intent
            row=session.get(Record,identifier)
            data={'response':response}
            if row: row.data=data
            else: session.add(Record(id=identifier,workspace=settings['workspace'],kind='provider_result',data=data))
    def publish_image(asset):
        path=Path(asset['path']).resolve()
        if not path.is_relative_to(Path(settings['private_root']).resolve()):
            raise ValueError('asset_outside_private_storage')
        data=path.read_bytes()
        if len(data)>7*1024*1024 or hashlib.sha256(data).hexdigest()!=asset['sha256']:
            raise ValueError('invalid_inline_image')
        with Image.open(path) as image:
            if image.format not in ('PNG','JPEG','WEBP'):
                raise ValueError('unsupported_inline_image')
            mime=Image.MIME[image.format]
            image.verify()
        return 'data:'+mime+';base64,'+base64.b64encode(data).decode('ascii')
    config={**settings,'providers':providers,'sessions':sessions,'policy_factory':policy_factory,'source_factory':source_factory,'save_remote':save_remote,'publish_image':publish_image}
    return configure(config)
