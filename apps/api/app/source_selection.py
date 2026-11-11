"""Explicit reviewed product/mask selection, immutable input snapshot."""
from sqlalchemy import select
from fastapi import HTTPException
from PIL import Image
from io import BytesIO
import hashlib,uuid
from .db import Record

def source_pair(session,workspace,sku_id,product_id,mask_id):
    if product_id==mask_id:raise HTTPException(422,detail={'code':'MASK_MUST_BE_DISTINCT'})
    from .sources import ROOT
    selected={};paths={}
    for role,identifier in [('product',product_id),('mask',mask_id)]:
        source=session.get(Record,identifier)
        if not source or source.workspace!=workspace or source.kind!='source' or source.data.get('sku_id')!=sku_id or source.data.get('deleting'):raise HTTPException(404)
        if source.data.get('type')!='image' or not source.data.get('rights_confirmed'):raise HTTPException(422,detail={'code':'SOURCE_RIGHTS_REQUIRED'})
        path=(ROOT/source.data['object_key']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source.data['sha256']:raise HTTPException(409,detail={'code':'SOURCE_HASH_MISMATCH'})
        selected[role]={'source_id':identifier,'sha256':source.data['sha256'],'revision':source.revision};paths[role]=path
    with Image.open(paths['product']) as product,Image.open(paths['mask']) as mask:
        if product.size!=mask.size:raise HTTPException(422,detail={'code':'MASK_SIZE_MISMATCH'})
        low,high=mask.convert('L').getextrema()
        if low==high:raise HTTPException(422,detail={'code':'MASK_HAS_NO_REGION'})
    return selected,paths


def subject_preview(session,workspace,sku_id,product_id,mask_id):
    _,paths=source_pair(session,workspace,sku_id,product_id,mask_id)
    with Image.open(paths['product']) as source, Image.open(paths['mask']) as mask:
        foreground=source.convert('RGBA')
        foreground.putalpha(mask.convert('L'))
        foreground.thumbnail((640,640),Image.Resampling.LANCZOS)
        buffer=BytesIO()
        foreground.save(buffer,format='PNG')
    return buffer.getvalue()


def select_sources(session,workspace,sku_id,expected,product_id,mask_id,reviewed):
    if not reviewed:raise HTTPException(422,detail={'code':'SOURCE_REVIEW_REQUIRED'})
    sku=session.scalar(select(Record).where(Record.id==sku_id,Record.workspace==workspace,Record.kind=='sku').with_for_update())
    if not sku or sku.data.get('deleting'):raise HTTPException(404)
    if sku.revision!=expected:raise HTTPException(409,detail={'code':'VERSION_CONFLICT'})
    selected,_=source_pair(session,workspace,sku_id,product_id,mask_id)
    rows=session.scalars(select(Record).where(Record.workspace==workspace,Record.kind=='source',Record.data['sku_id'].as_string()==sku_id)).all()
    for row in rows:
        if row.data.get('sku_id')==sku_id and row.data.get('role') in {'product','mask'}:row.data={**row.data,'role':None}
    for role,item in selected.items():
        row=session.get(Record,item['source_id']);row.data={**row.data,'role':role,'role_reviewed':True}
    selection=Record(id=str(uuid.uuid4()),workspace=workspace,kind='source_selection',data={'sku_id':sku_id,'sources':selected,'reviewed_by':workspace})
    session.add(selection);sku.data={**sku.data,'source_selection_id':selection.id};sku.revision+=1
    session.commit()
    return {'id':selection.id,'sku_revision':sku.revision,'sources':selected}
