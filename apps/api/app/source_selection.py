"""Explicit reviewed product/mask selection, immutable input snapshot."""
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from PIL import Image, ImageOps
from io import BytesIO
from errno import EDQUOT, ENOSPC
import hashlib, uuid
from .db import Record
from .product_matte import extract_matte


def _image_source(session, workspace, sku_id, identifier):
    from .sources import ROOT
    source = session.get(Record, identifier)
    if (not source or source.workspace != workspace or source.kind != 'source'
            or source.data.get('sku_id') != sku_id or source.data.get('deleting')):
        raise HTTPException(404)
    if source.data.get('type') != 'image' or source.data.get('rights_confirmed') is not True:
        raise HTTPException(422, detail={'code':'SOURCE_RIGHTS_REQUIRED'})
    path = (ROOT / source.data['object_key']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise HTTPException(409, detail={'code':'SOURCE_HASH_MISMATCH'})
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != source.data['sha256']:
        raise HTTPException(409, detail={'code':'SOURCE_HASH_MISMATCH'})
    return source, path


def _reference(source):
    return {'source_id':source.id, 'sha256':source.data['sha256'], 'revision':source.revision}


def _matte(source):
    matte = extract_matte(source)
    if matte is None:
        raise HTTPException(422, detail={'code':'SUBJECT_ISOLATION_UNCERTAIN',
            'message':'这张照片的主体边缘难以识别。请更换拍摄角度，或补充主体遮罩。'})
    return matte


def _product_source(session, workspace, sku_id, identifier):
    row, path = _image_source(session, workspace, sku_id, identifier)
    if row.data.get('is_subject_mask') or row.data.get('role') == 'mask':
        raise HTTPException(422, detail={'code':'PRODUCT_IMAGE_REQUIRED'})
    return row, path

def source_pair(session,workspace,sku_id,product_id,mask_id):
    if product_id==mask_id:raise HTTPException(422,detail={'code':'MASK_MUST_BE_DISTINCT'})
    product, product_path = _product_source(session, workspace, sku_id, product_id)
    mask, mask_path = _image_source(session, workspace, sku_id, mask_id)
    if mask.data.get('derived_from_source_id') not in (None, product_id):
        raise HTTPException(422, detail={'code':'MASK_SOURCE_MISMATCH'})
    selected = {'product':_reference(product), 'mask':_reference(mask)}
    paths = {'product':product_path, 'mask':mask_path}
    with Image.open(paths['product']) as product,Image.open(paths['mask']) as mask:
        if product.size!=mask.size:raise HTTPException(422,detail={'code':'MASK_SIZE_MISMATCH'})
        low,high=mask.convert('L').getextrema()
        if low==high:raise HTTPException(422,detail={'code':'MASK_HAS_NO_REGION'})
    return selected,paths


def subject_preview(session,workspace,sku_id,product_id,mask_id=None):
    if mask_id:
        _,paths = source_pair(session,workspace,sku_id,product_id,mask_id)
        product_path = paths['product']
        with Image.open(paths['mask']) as mask:
            matte = mask.convert('L')
    else:
        _, product_path = _product_source(session, workspace, sku_id, product_id)
    with Image.open(product_path) as source:
        if not mask_id or session.get(Record, mask_id).data.get('derived_from_source_id'):
            matte = _matte(source)
        source.thumbnail((640, 640), Image.Resampling.LANCZOS)
        foreground = source.convert('RGBA')
        foreground.putalpha(matte.resize(source.size, Image.Resampling.LANCZOS))
        foreground = ImageOps.exif_transpose(foreground)
        foreground.info.clear()
        buffer=BytesIO()
        foreground.save(buffer,format='PNG')
    return buffer.getvalue()


def _derived_mask(session, workspace, sku_id, product, product_path, created):
    from .sources import ROOT, minimum_free_upload_space, require_upload_space, storage_full
    from .uploads import check_upload_quota
    with Image.open(product_path) as source:
        matte = _matte(source)
    matte.info.clear()
    buffer = BytesIO()
    matte.save(buffer, format='PNG')
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    # Bind a candidate to its exact source and pixels. Re-confirmation reuses
    # the same asset and never consumes another slot in the merchant's quota.
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, ':'.join(
        ('aigc-subject-mask', workspace, sku_id, product.id, product.data['sha256'], digest))))
    existing = session.get(Record, identifier)
    if existing:
        row, _ = _image_source(session, workspace, sku_id, identifier)
        if row.data.get('derived_from_source_id') != product.id or row.data['sha256'] != digest:
            raise HTTPException(409, detail={'code':'SOURCE_HASH_MISMATCH'})
        return row
    check_upload_quota(session, workspace, sku_id, 'image', len(data))
    require_upload_space(minimum_free_upload_space(), len(data))
    key = uuid.uuid4().hex
    path = ROOT / key
    try:
        with path.open('xb') as stream:
            created.append(path)
            stream.write(data)
    except OSError as error:
        if error.errno in (EDQUOT, ENOSPC):
            raise storage_full() from None
        raise
    row = Record(id=identifier, workspace=workspace, kind='source', data={
        'sku_id':sku_id, 'type':'image', 'name':'主体遮罩-' + identifier[:8] + '.png',
        'size':len(data), 'object_key':key, 'sha256':digest, 'rights_confirmed':True,
        'is_subject_mask':True, 'derived_from_source_id':product.id, 'parse_status':'pending'})
    session.add(row)
    session.flush()
    return row


def select_sources(session,workspace,sku_id,expected,product_id,mask_id,reviewed,mode='cutout'):
    if not reviewed:raise HTTPException(422,detail={'code':'SOURCE_REVIEW_REQUIRED'})
    sku=session.scalar(select(Record).where(Record.id==sku_id,Record.workspace==workspace,Record.kind=='sku').with_for_update())
    if not sku or sku.data.get('deleting'):raise HTTPException(404)
    if sku.revision!=expected:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    if mode not in {'whole_photo','cutout'} or (mode == 'whole_photo' and mask_id):
        raise HTTPException(422, detail={'code':'INVALID_SOURCE_SELECTION'})
    created = []
    try:
        if mask_id:
            selected, _ = source_pair(session, workspace, sku_id, product_id, mask_id)
        else:
            product, path = _product_source(session, workspace, sku_id, product_id)
            selected = {'product':_reference(product)}
            if mode == 'cutout':
                mask = _derived_mask(session, workspace, sku_id, product, path, created)
                selected['mask'] = _reference(mask)
        rows=session.scalars(select(Record).where(Record.workspace==workspace,Record.kind=='source',Record.data['sku_id'].as_string()==sku_id)).all()
        for row in rows:
            if row.data.get('role') in {'product','mask'}:
                was_mask = row.data['role'] == 'mask'
                row.data = {**row.data, 'role':None, **({'is_subject_mask':True} if was_mask else {})}
        for role,item in selected.items():
            row = session.get(Record, item['source_id'])
            row.data = {**row.data, 'role':role, 'role_reviewed':True,
                        **({'is_subject_mask':True} if role == 'mask' else {})}
        selection = Record(id=str(uuid.uuid4()), workspace=workspace, kind='source_selection',
            data={'sku_id':sku_id,'sources':selected,'mode':mode,'reviewed_by':workspace})
        session.add(selection)
        changed = session.execute(update(Record).where(Record.id==sku_id, Record.workspace==workspace,
            Record.revision==expected).values(data={**sku.data,'source_selection_id':selection.id}, revision=expected+1))
        if changed.rowcount != 1:
            raise HTTPException(409, detail={'code':'VERSION_CONFLICT'})
        session.commit()
    except BaseException as error:
        session.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        if isinstance(error, IntegrityError):
            raise HTTPException(409, detail={'code':'VERSION_CONFLICT'}) from None
        raise
    return {'id':selection.id,'sku_revision':expected+1,'sources':selected}
