from pathlib import Path
import hashlib
from tempfile import TemporaryDirectory
from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import select
from app.db import Record
from app.execution import Task
from .media import repair_patch, save_image


def repair_handler(repository,job,services_factory=None):
    payload=job['payload']
    from app.sources import ROOT
    with repository.sessions() as session:
        base=session.get(Record,payload['candidate_asset_id'])
        if not base or base.kind!='asset' or base.workspace!=job['workspace'] or base.data.get('work_id')!=payload['work_id'] or base.data.get('deleting'):
            raise ValueError('repair_asset_scope')
        data=dict(base.data)
        work=session.get(Record,payload['work_id'])
        profile=session.get(Record,work.data['profile_id']) if work and not work.data.get('deleting') else None
        if not profile or profile.workspace!=job['workspace'] or profile.kind!='profile' or profile.data.get('status')!='confirmed' or profile.data.get('deleting'):
            raise ValueError('fact_revoked')
        paths=[]
        ai_repair = 'instruction' in payload
        source_ids = [payload['mask_source_id']] if ai_repair else [payload['original_source_id'],payload['mask_source_id']]
        for index,row in enumerate([base,*(session.get(Record, source_id) for source_id in source_ids)]):
            if not row or row.workspace!=job['workspace'] or row.data.get('deleting'):
                raise ValueError('repair_source_scope')
            if index and (row.kind!='source' or row.data.get('type')!='image' or row.data.get('sku_id')!=work.data['sku_id'] or not row.data.get('rights_confirmed')):
                raise ValueError('repair_source_rights')
            key=row.data.get('repair_render_key') if index==0 else None
            path=(ROOT/(key or row.data['object_key'])).resolve()
            digest=row.data['repair_render_sha256'] if key else row.data['sha256']
            if payload.get('repair_input_sha256', {}).get(row.id, digest) != digest:
                raise ValueError('repair_source_changed')
            if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('repair_source_hash')
            paths.append(path)
    output=ROOT/(hashlib.sha256(job['id'].encode()).hexdigest()+'.png')
    with TemporaryDirectory(dir=ROOT) as directory:
        repaired=Path(directory)/'repair.png'
        if ai_repair:
            if not services_factory:
                raise ValueError('repair_model_not_configured')
            generate_patch(services_factory(job), job, *paths, repaired)
        else:
            repair_patch(*paths,repaired)
        with Image.open(repaired) as original:
            sample=original.convert('RGB')
        if data.get('media_kind')=='product_image':
            render_path=output.with_name(output.stem+'-render.png')
            render=save_image(sample,render_path)
            data.update(repair_render_key=render_path.name,repair_render_sha256=render['sha256'])
        marker=ImageDraw.Draw(sample)
        marker.rectangle((0,max(0,sample.height-24),sample.width,sample.height),fill='black')
        marker.text((4,max(0,sample.height-20)),'AI GENERATED - INTERNAL PREVIEW - UNREVIEWED',fill='white')
        result=save_image(sample,output)
    with repository.sessions.begin() as session:
        task=session.scalar(select(Task).where(Task.id==job['id']).with_for_update())
        if not task or task.workspace!=job['workspace'] or task.state!='running' or task.fencing_token!=job['fencing_token']:
            raise ValueError('stale_repair')
        identifier=job['id']+':asset'
        for field in ('release_object_key','release_sha256','label_rule_version','label_verification'):
            data.pop(field,None)
        session.add(Record(id=identifier,workspace=job['workspace'],kind='asset',data={**data,'sha256':result['sha256'],'object_key':output.name,'review':'pending','sample_marked':True,'extension':'.png','parent_asset_id':payload['candidate_asset_id'],'repair_task_id':job['id']}))
    return {'asset_id':identifier,'status':'awaiting_review'}


def generate_patch(services, job, candidate, mask, output):
    """Pad both references equally, then composite only within the uploaded mask."""
    normalized = (1152, 2048)
    with Image.open(candidate) as source, Image.open(mask) as coverage:
        scene = source.convert('RGB')
        matte = coverage.convert('L')
    if scene.size != matte.size or matte.getbbox() is None:
        raise ValueError('invalid_repair_mask')
    references = {}
    for key, image in (('candidate', scene), ('mask', matte)):
        padded = ImageOps.pad(image, normalized, method=Image.Resampling.LANCZOS, color=0)
        references[key] = save_image(padded, output.parent/(key+'.png'))
    result = services.invoke('product_image', {'slot':'repair', 'instruction':job['payload']['instruction'],
                                               **references}, job['id']+':repair')
    with Image.open(result['path']) as generated:
        if generated.size != normalized:
            raise ValueError('repair_output_size_mismatch')
        fitted = ImageOps.contain(scene, normalized, method=Image.Resampling.LANCZOS)
        left = (normalized[0]-fitted.width)//2
        top = (normalized[1]-fitted.height)//2
        patch = generated.crop((left,top,left+fitted.width,top+fitted.height))
        patch = patch.convert('RGB').resize(scene.size,Image.Resampling.LANCZOS)
    save_image(Image.composite(patch,scene,matte),output)
