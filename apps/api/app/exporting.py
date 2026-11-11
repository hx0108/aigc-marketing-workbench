"""Package immutable, explicitly sample-marked artifacts; never relabel release."""
import hashlib,json,uuid,zipfile
from .sources import ROOT, authorized_music

EXPORT_KINDS = {
    'video_only': {'video', 'cover', 'copy'},
    'poster_only': {'marketing_poster'},
    'full_suite': {'video', 'cover', 'copy', 'marketing_poster', 'product_image'},
}


def omitted_slots(work, selection, assets):
    expected = {
        (kind, slot)
        for kind in EXPORT_KINDS[selection]
        for slot in (('white', 'scene_1', 'scene_2') if kind == 'product_image' else work.data['platforms'])
    }
    present = {(asset.data['media_kind'], asset.data.get('slot')) for asset in assets}
    return [f'{kind}/{slot}' for kind, slot in sorted(expected - present)]


def export_rights(session, workspace, work, result, selection, assets):
    from .db import Record

    def scoped_record(record_id, kind):
        record = session.get(Record, record_id) if record_id else None
        if record and record.workspace == workspace and record.kind == kind and not record.data.get('deleting'):
            return record
        return None

    request_id = work.data.get('creation_request_id')
    request = scoped_record(request_id, 'creation_request')
    profile = scoped_record(work.data.get('profile_id'), 'profile') if not request_id else None
    snapshot = request.data.get('profile_snapshot') if request else None
    if profile:
        snapshot = profile.data
    source_ids = (snapshot or {}).get('source_ids', [])
    records = []
    for source_id in dict.fromkeys(source_ids):
        source = scoped_record(source_id, 'source')
        if source and source.data.get('sku_id') != work.data.get('sku_id'):
            source = None
        records.append(_rights_entry(source_id, source, 'source'))
    if 'video' in EXPORT_KINDS[selection]:
        video_platforms = {asset.data.get('slot') for asset in assets if asset.data.get('media_kind') in {'video','cover'}}
        for platform in work.data.get('platforms', []):
            if platform not in video_platforms:
                continue
            settings = result.data.get('render_settings', {}).get(platform, {})
            music_id = settings.get('music')
            if music_id:
                music = authorized_music(session, workspace, work.data.get('sku_id'), music_id)
                records.append({**_rights_entry(music_id, music, 'music'), 'platform': platform})
            for index,reference in settings.get('shot_video_sources',{}).items():
                source_id=reference['source_id']
                source=scoped_record(source_id,'source')
                if source and (source.data.get('sku_id')!=work.data.get('sku_id') or source.data.get('type')!='video'
                    or source.revision!=reference['revision'] or source.data.get('sha256')!=reference['sha256']
                    or source.data.get('physical_deleted')):
                    source=None
                records.append({**_rights_entry(source_id,source,'video_clip'),'platform':platform,
                    'shot_index':int(index),'start_seconds':reference['start_seconds']})
    return {'source_provenance_available': bool(source_ids), 'materials': records}


def _rights_entry(record_id, record, kind):
    confirmed = record.data.get('rights_confirmed') if record else None
    confirmation = 'unknown'
    if confirmed is True:
        confirmation = 'user_confirmed'
    elif confirmed is False:
        confirmation = 'not_confirmed'
    return {
        'id': record_id,
        'kind': kind,
        'revision': record.revision if record else None,
        'confirmation': confirmation,
    }


def require_release_rights(rights):
    if not rights or not rights.get('source_provenance_available'):
        raise ValueError('MATERIAL_RIGHTS_UNVERIFIED')
    materials=rights.get('materials',[])
    if not any(material['kind']=='source' for material in materials) or any(material['confirmation']!='user_confirmed' for material in materials):
        raise ValueError('MATERIAL_RIGHTS_UNVERIFIED')


def package_manifest(work, selection, mode, assets, rule_version=None, rights=None, partial=False):
    is_sample = mode == 'sample'
    entries = []
    for asset in assets:
        data = asset.data
        kind, slot = data['media_kind'], data.get('slot')
        entries.append({
            'id': asset.id,
            'revision': asset.revision,
            'sha256': data['sha256' if is_sample else 'release_sha256'],
            'kind': kind,
            'slot': slot,
            'platform': None if kind == 'product_image' else slot,
            'review': data.get('review'),
            'label': {
                'internal_sample': bool(data.get('sample_marked')) if is_sample else False,
                'verified_rule_version': None if is_sample else (data.get('label_verification') or {}).get('rule_version'),
            },
        })
    manifest = {
        'mode': mode,
        'selection': selection,
        'sku_id': work.data.get('sku_id'),
        'profile_id': work.data.get('profile_id'),
        'result_revision_id': work.data.get('current_result'),
        'platforms': work.data.get('platforms', []),
        'work_id': work.id,
        'work_revision': work.revision,
        'work_status': work.data.get('status'),
        'missing_items': work.data.get('missing_items', []),
        'assets': entries,
    }
    if rule_version is not None:
        manifest['rule_version'] = rule_version
    if rights is not None:
        manifest['material_rights'] = rights
    if partial:
        missing = omitted_slots(work, selection, assets)
        for item in manifest['missing_items']:
            platform, separator, branch = item.partition('/')
            if separator and platform in manifest['platforms'] and branch in {'video', 'poster'}:
                kind = 'marketing_poster' if branch == 'poster' else branch
                item = f'{kind}/{platform}'
            missing.append(item)
        manifest['partial'] = bool(missing)
        manifest['missing_items'] = sorted(set(missing))
    return manifest

def verified_package_path(data):
    path = (ROOT / data['object_key']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('PACKAGE_NOT_AVAILABLE')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != data.get('sha256'):
        raise ValueError('PACKAGE_HASH_MISMATCH')
    return path

def build_sample(work,assets,selection,*,rights=None,partial=False):
    wanted=EXPORT_KINDS[selection]
    selected=[a for a in assets if a.data.get('media_kind') in wanted]
    if not selected:raise ValueError('MEDIA_NOT_AVAILABLE')
    platforms=work.data.get('platforms',[])
    required=set()
    if selection in {'video_only','full_suite'}:
        required.update(('video',p) for p in platforms)
    if selection in {'poster_only','full_suite'}:
        required.update(('marketing_poster',p) for p in platforms)
    if selection=='full_suite':
        required.update(('product_image',slot) for slot in ['white','scene_1','scene_2'])
        required.update((kind,p) for p in platforms for kind in ['cover','copy'])
    present={(a.data.get('media_kind'),a.data.get('slot')) for a in selected}
    slots=[(a.data.get('media_kind'),a.data.get('slot')) for a in selected]
    if len(slots)!=len(set(slots)):
        raise ValueError('AMBIGUOUS_ASSET_SELECTION')
    if any(slot not in (('white', 'scene_1', 'scene_2') if kind == 'product_image' else platforms) for kind,slot in slots):
        raise ValueError('UNSELECTED_PLATFORM_ASSET')
    missing=sorted(required-present)
    if missing and not partial:raise ValueError('INCOMPLETE_SELECTION:'+','.join(kind+'/'+slot for kind,slot in missing))
    for asset in selected:
        if asset.data.get('review')=='rejected':raise ValueError('ASSET_REJECTED')
        if partial and asset.data.get('review') != 'approved':raise ValueError('REVIEW_REQUIRED')
        if not asset.data.get('sample_marked'):raise ValueError('SAMPLE_MARK_REQUIRED')
        path=(ROOT/asset.data['object_key']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('MEDIA_NOT_AVAILABLE')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=asset.data.get('sha256'):raise ValueError('MEDIA_HASH_MISMATCH')
    key=uuid.uuid4().hex
    manifest=package_manifest(work,selection,'sample',selected,rights=rights,partial=partial)
    with zipfile.ZipFile(ROOT/key,'x',compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        for asset in selected:package.write(ROOT/asset.data['object_key'],asset.id+asset.data.get('extension','.bin'))
    return {'object_key':key,'manifest':manifest,'sha256':hashlib.sha256((ROOT/key).read_bytes()).hexdigest()}

