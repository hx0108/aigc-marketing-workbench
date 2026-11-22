"""Frozen photo inputs and local-only authorization for product films."""
import hashlib
import json

from sqlalchemy import select

from .db import Record
from .execution import Task


CONTRACT = 'photo-campaign-v1'
MESSAGES = {
    'PHOTO_DURATION_INVALID': '照片广告支持 6 到 30 秒。',
    'PHOTO_HEADLINE_INVALID': '海报标题限 32 字，数值卖点须与已确认的商品事实一致。',
    'PRODUCT_PHOTO_REQUIRED': '请在商品档案中确认至少一张有使用权的商品照片。',
    'WEAR_PHOTO_REQUIRED': '请选择当前档案中的单只入耳耳机外侧照片，或使用商品展示镜头。',
    'PHOTO_SOURCE_CHANGED': '商品照片或使用权已变化，请重新确认档案并生成。',
    'CONSENT_SCOPE_MISMATCH': '照片创作授权与当前任务不一致，请重新确认。',
    'FACT_REVOKED': '商品档案已失效，请重新确认。',
    'STALE_TASK_LEASE': '任务状态已变化。',
}


class CampaignError(ValueError):
    def __init__(self, code):
        self.code = code
        self.detail = {'code': code, 'message': MESSAGES[code]}
        super().__init__(code)


def _photos_in_profile(session, workspace, snapshot):
    sku_id = snapshot['sku_id']
    ids = list(dict.fromkeys(snapshot.get('source_ids', [])))
    rows = session.scalars(select(Record).where(
        Record.id.in_(ids), Record.kind == 'source', Record.workspace == workspace,
        Record.data['sku_id'].as_string() == sku_id,
    )).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids) or any(row.data.get('deleting') for row in rows):
        raise CampaignError('PHOTO_SOURCE_CHANGED')
    # Older manual masks lose their role when a new pair is selected.
    old_masks = session.scalars(select(Record.data['sources']['mask']['source_id'].as_string()).where(
        Record.workspace == workspace, Record.kind == 'source_selection',
        Record.data['sku_id'].as_string() == sku_id,
    )).all()
    mask_ids = set(old_masks)
    selection = snapshot.get('source_selection', {})
    if selection.get('mask'):
        mask_ids.add(selection['mask']['source_id'])
    ordered = [by_id[identifier] for identifier in ids]
    return [row for row in ordered if row.id not in mask_ids and row.data.get('type') == 'image'
            and row.data.get('role') != 'mask' and not row.data.get('is_subject_mask')
            and row.data.get('rights_confirmed') is True]


def _reference(photo):
    return {'source_id': photo.id, 'sha256': photo.data['sha256'], 'revision': photo.revision}


def _verified_path(photo):
    from .sources import ROOT
    try:
        path = (ROOT / photo.data['object_key']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise CampaignError('PHOTO_SOURCE_CHANGED')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != photo.data['sha256']:
                raise CampaignError('PHOTO_SOURCE_CHANGED')
    except (OSError, KeyError, TypeError):
        raise CampaignError('PHOTO_SOURCE_CHANGED') from None
    return path


def resolve_photos(session, workspace, request):
    """Return ordered private paths only after checking the frozen versions and bytes."""
    photos = _photos_in_profile(session, workspace, request['profile_snapshot'])
    refs = request.get('photo_sources', [])
    if not refs or [_reference(photo) for photo in photos] != refs:
        raise CampaignError('PHOTO_SOURCE_CHANGED')
    return [_verified_path(photo) for photo in photos]


def campaign_quote(request):
    scope = {key: request.get(key) for key in (
        'creative_mode','profile_id','sku_id','profile_snapshot','platforms','duration_seconds',
        'brief','photo_sources','wear_source_id',
    )}
    encoded = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {'execution_mode': 'local_only', 'contract_version': CONTRACT, 'providers': {},
            'cost_upper_bound': 0, 'scope_sha256': hashlib.sha256(encoded).hexdigest()}


def prepare_campaign(session, workspace, request):
    """Check the creative inputs once, before offering a zero-external-cost quote."""
    from marketing_worker.fact_validation import NumericFactError, validate_numeric_claims
    if not 6 <= request['duration_seconds'] <= 30:
        raise CampaignError('PHOTO_DURATION_INVALID')
    headline = request['brief'].strip()
    if len(headline) > 32 or any(ord(char) < 32 for char in headline):
        raise CampaignError('PHOTO_HEADLINE_INVALID')
    snapshot = request['profile_snapshot']
    facts = {key: {'id':key,'value':value,'validity':'active'} for key,value in snapshot['facts'].items()}
    try:
        validate_numeric_claims(headline, facts, facts)
    except NumericFactError:
        raise CampaignError('PHOTO_HEADLINE_INVALID') from None
    photos = _photos_in_profile(session, workspace, snapshot)
    if not photos:
        raise CampaignError('PRODUCT_PHOTO_REQUIRED')
    wear_id = request.get('wear_source_id')
    if wear_id is not None and wear_id not in {photo.id for photo in photos}:
        raise CampaignError('WEAR_PHOTO_REQUIRED')
    for photo in photos:
        _verified_path(photo)
    scoped_request = {**request, 'brief':headline, 'photo_sources':[_reference(photo) for photo in photos]}
    from .photo_storyboard import shot_plan
    storyboards = {
        platform: [{'view': view, 'seconds': seconds} for view, seconds in shot_plan(scoped_request, platform)]
        for platform in scoped_request['platforms']
    }
    return {**scoped_request, 'quote':campaign_quote(scoped_request), 'status':'ready', 'blockers':[],
            'storyboards':storyboards}


def verify_campaign_job(session, job):
    """Recheck the persisted admission and private files at the worker boundary."""
    workspace = job['workspace']
    payload = job['payload']
    task = session.get(Task, job['id'])
    if (not task or task.workspace != workspace or task.phase != 'creation_run' or task.state != 'running'
            or task.fencing_token != job['fencing_token']):
        raise CampaignError('STALE_TASK_LEASE')
    request = payload['request']
    if any(task.payload.get(key) != payload.get(key) for key in ('work_id','profile_id','request_id','request')):
        raise CampaignError('CONSENT_SCOPE_MISMATCH')
    def record(record_id, kind):
        row = session.get(Record, record_id) if record_id else None
        return row if row and row.workspace == workspace and row.kind == kind and not row.data.get('deleting') else None
    work = record(payload['work_id'], 'work')
    original = record(payload['request_id'], 'creation_request')
    profile = record(payload['profile_id'], 'profile')
    if not profile or profile.data.get('status') != 'confirmed' or not record(request['sku_id'], 'sku'):
        raise CampaignError('FACT_REVOKED')
    consent = record(request.get('consent_id'), 'processing_consent')
    quote = campaign_quote(request)
    if (not work or not original or not consent or request.get('creative_mode') != 'photo_campaign'
            or work.data.get('creation_request_id') != original.id or work.data.get('profile_id') != profile.id
            or work.data.get('sku_id') != request['sku_id'] or request.get('profile_id') != profile.id
            or original.data.get('status') != 'ready' or original.data.get('quote') != quote
            or campaign_quote(original.data) != quote or request.get('quote') != quote
            or consent.data.get('request_id') != original.id or consent.data.get('request_revision') != original.revision
            or consent.data.get('profile_id') != profile.id or consent.data.get('photo_sources') != request['photo_sources']
            or consent.data.get('wear_source_id') != request.get('wear_source_id')
            or any(consent.data.get(key) != value for key, value in quote.items())):
        raise CampaignError('CONSENT_SCOPE_MISMATCH')
    expected_facts = [{'id':key,'value':value,'validity':'active'} for key,value in request['profile_snapshot']['facts'].items()]
    if request.get('facts') != expected_facts:
        raise CampaignError('CONSENT_SCOPE_MISMATCH')
    return resolve_photos(session, workspace, request)
