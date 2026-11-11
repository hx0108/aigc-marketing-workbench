"""Release requires an operator-verified ruleset and exact-version human reviews."""
from pathlib import Path
from datetime import datetime,timezone
import os,json,hashlib,uuid,zipfile,subprocess
from PIL import Image
from xml.etree import ElementTree
from .sources import ROOT
from .exporting import EXPORT_KINDS, package_manifest, require_release_rights
from .db import Record

LABELLED_KINDS={'video','marketing_poster','cover'}
IMPLICIT_LABEL_VERSION='GB45438-2025-TC260-202508'
IMPLICIT_FIELDS={'Label','ContentProducer','ProduceID','ReservedCode1','ContentPropagator','PropagateID','ReservedCode2'}
XMP_AIGC='{http://www.tc260.org.cn/ns/AIGC/1.0/}AIGC'


def unique_json_object(pairs):
    result=dict(pairs)
    if len(result)!=len(pairs):raise ValueError('duplicate metadata field')
    return result


def require_implicit_label(values):
    if not values:raise ValueError('IMPLICIT_LABEL_REQUIRED')
    try:
        if len(values)!=1 or len(values[0])>16384:raise ValueError
        value=json.loads(values[0],object_pairs_hook=unique_json_object)
        if not isinstance(value,dict) or set(value)!=IMPLICIT_FIELDS:raise ValueError
        if not all(isinstance(item,str) for item in value.values()) or value['Label']!='1':raise ValueError
        for field in ('ContentProducer','ProduceID','ContentPropagator','PropagateID'):
            if not value[field].strip():raise ValueError
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise ValueError('IMPLICIT_LABEL_INVALID') from None


def png_implicit_values(image):
    if image.format!='PNG':raise ValueError('IMPLICIT_LABEL_FORMAT_UNSUPPORTED')
    image.load()
    values=[]
    if 'AIGC' in image.text:
        try:
            payload=json.loads(image.text['AIGC'],object_pairs_hook=unique_json_object)
            if not isinstance(payload,dict) or set(payload)!={'AIGC'}:raise ValueError
            values.append(json.dumps(payload['AIGC']))
        except (ValueError,TypeError,RecursionError):
            raise ValueError('IMPLICIT_LABEL_INVALID') from None
    if xmp:=image.info.get('XML:com.adobe.xmp'):
        try:
            if len(xmp)>65536 or '<!DOCTYPE' in xmp:raise ValueError
            document=ElementTree.fromstring(xmp)
        except (ValueError,ElementTree.ParseError):
            raise ValueError('IMPLICIT_LABEL_INVALID') from None
        values.extend(node.text or '' for node in document.iter(XMP_AIGC))
        values.extend(node.attrib[XMP_AIGC] for node in document.iter() if XMP_AIGC in node.attrib)
    return values

def require_repair_reviews(session,work,assets):
    source_ids={source_id for asset in assets for source_id in asset.data.get('repair_source_ids',[])}
    for source_id in source_ids:
        source=session.get(Record,source_id)
        if (not source or source.workspace!=work.workspace or source.kind!='asset'
            or source.data.get('work_id')!=work.id or source.data.get('media_kind')!='product_image'
            or not source.data.get('repair_task_id') or source.data.get('deleting')
            or source.data.get('review')!='approved'):
            raise ValueError('REPAIR_SOURCE_REVIEW_REQUIRED')


def rules_fingerprint(rules):
    return hashlib.sha256(json.dumps(rules,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def release_file(asset,rules):
    data=asset.data
    key=data.get('release_object_key');digest=data.get('release_sha256')
    if not key or not digest:raise ValueError('RELEASE_ASSET_REQUIRED')
    path=(ROOT/key).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError('MEDIA_HASH_MISMATCH')
    kind=data['media_kind']
    if kind in LABELLED_KINDS or kind=='product_image':
        if rules.get('implicit_label_version')!=IMPLICIT_LABEL_VERSION:
            raise ValueError('IMPLICIT_LABEL_RULE_REQUIRED')
        values=[]
        try:
            if kind=='video':
                metadata=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,timeout=30,check=True).stdout)
                if 'mp4' not in metadata['format']['format_name'].split(','):raise ValueError('IMPLICIT_LABEL_FORMAT_UNSUPPORTED')
                values=[value for key,value in metadata['format'].get('tags',{}).items() if key=='AIGC']
                video=next(s for s in metadata['streams'] if s['codec_type']=='video')
                width,height=video['width'],video['height']
            else:
                with Image.open(path) as image:
                    width,height=image.size
                    values=png_implicit_values(image)
        except (OSError,subprocess.SubprocessError,StopIteration,KeyError,TypeError):
            raise ValueError('MEDIA_SPEC_MISMATCH') from None
        require_implicit_label(values)
    if kind in LABELLED_KINDS:
        policy=rules['platforms'].get(data.get('slot'),{}).get(kind)
        if not policy:raise ValueError('RULESET_SPEC_MISSING')
        if kind=='video' and video.get('codec_name')!=policy['codec']:raise ValueError('MEDIA_SPEC_MISMATCH')
        if [width,height]!=policy['size']:raise ValueError('MEDIA_SPEC_MISMATCH')
    return path


def label_binding(asset,rules):
    return {'rule_version':rules['version'],'rule_sha256':rules_fingerprint(rules),
            'release_sha256':asset.data.get('release_sha256'),'asset_revision':asset.revision}


def require_label_verification(asset,rules):
    if asset.data.get('media_kind') not in LABELLED_KINDS:return
    verification=asset.data.get('label_verification') or {}
    if any(verification.get(key)!=value for key,value in label_binding(asset,rules).items()) or not verification.get('reviewer') or not verification.get('evidence'):
        raise ValueError('LABEL_VERIFICATION_REQUIRED')


def verify_label(asset,rules,expected_revision,expected_sha256,reviewer,evidence):
    if asset.data.get('media_kind') not in LABELLED_KINDS:raise ValueError('LABEL_NOT_APPLICABLE')
    if asset.data.get('review')!='approved':raise ValueError('REVIEW_REQUIRED')
    if asset.revision!=expected_revision or asset.data.get('release_sha256')!=expected_sha256:raise ValueError('VERSION_CONFLICT')
    if not reviewer.strip() or not evidence.strip() or len(reviewer)>120 or len(evidence)>500:raise ValueError('LABEL_EVIDENCE_REQUIRED')
    release_file(asset,rules)
    return {**label_binding(asset,rules),'reviewer':reviewer.strip(),'evidence':evidence.strip()}

def ruleset():
    path=os.environ.get('AIGC_RULESET_FILE')
    if not path:raise ValueError('RULESET_UNVERIFIED')
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        expiry=datetime.fromisoformat(data['valid_until'].replace('Z','+00:00'))
        if expiry.tzinfo is None or not isinstance(data.get('platforms'),dict):raise ValueError()
        for platform,policies in data['platforms'].items():
            if platform not in {'douyin','xiaohongshu'} or not isinstance(policies,dict):raise ValueError()
            for kind,policy in policies.items():
                if kind not in {'video','marketing_poster','cover'} or not isinstance(policy,dict):raise ValueError()
                size=policy.get('size')
                if not isinstance(size,list) or len(size)!=2 or any(type(value)!=int or value<=0 for value in size):raise ValueError()
                if kind=='video' and not isinstance(policy.get('codec'),str):raise ValueError()
    except (OSError,ValueError,KeyError,TypeError,AttributeError):raise ValueError('RULESET_INVALID') from None
    if data.get('verified') is not True or not data.get('version') or not data.get('evidence') or not data.get('reviewer'):raise ValueError('RULESET_UNVERIFIED')
    if data.get('implicit_label_version')!=IMPLICIT_LABEL_VERSION:raise ValueError('IMPLICIT_LABEL_RULE_REQUIRED')
    if expiry<=datetime.now(timezone.utc):raise ValueError('RULESET_EXPIRED')
    return data

def package_release(work,assets,selection,*,rights=None,partial=False):
    rules=ruleset()
    platforms=work.data['platforms']
    wanted=EXPORT_KINDS[selection]
    chosen=[a for a in assets if a.data.get('media_kind') in wanted]
    if not chosen and partial:raise ValueError('MEDIA_NOT_AVAILABLE')
    slots=[(a.data['media_kind'],a.data.get('slot')) for a in chosen]
    if len(slots)!=len(set(slots)):raise ValueError('DUPLICATE_SLOT')
    if any(slot not in (['white','scene_1','scene_2'] if kind=='product_image' else platforms) for kind,slot in slots):raise ValueError('UNSELECTED_PLATFORM')
    selected_platforms = {slot for kind, slot in slots if kind != 'product_image'} if partial else set(platforms)
    if not selected_platforms<=set(rules.get('platforms',{})):raise ValueError('RULESET_PLATFORM_MISSING')
    required=set()
    if selection in {'video_only','full_suite'}:required|={(k,p) for p in platforms for k in ['video','cover','copy']}
    if selection in {'poster_only','full_suite'}:required|={('marketing_poster',p) for p in platforms}
    if selection=='full_suite':required|={('product_image',slot) for slot in ['white','scene_1','scene_2']}
    if not partial and required-set(slots):raise ValueError('INCOMPLETE_SELECTION')
    files=[]
    for asset in chosen:
        if asset.data.get('review')!='approved':raise ValueError('REVIEW_REQUIRED')
        path=release_file(asset,rules)
        require_label_verification(asset,rules)
        files.append((asset,path))
    require_release_rights(rights)
    key=uuid.uuid4().hex
    manifest=package_manifest(work,selection,'release',chosen,rules['version'],rights=rights,partial=partial)
    manifest['rule_sha256']=rules_fingerprint(rules)
    with zipfile.ZipFile(ROOT/key,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        for asset,path in files:archive.write(path,asset.id+asset.data.get('extension','.bin'))
    return {'object_key':key,'sha256':hashlib.sha256((ROOT/key).read_bytes()).hexdigest(),'manifest':manifest}

