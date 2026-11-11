"""In-flight upload quotas under the owning SKU row lock."""
import time,uuid
from sqlalchemy import select
from fastapi import HTTPException
from .db import Record

SOURCE_COUNTS={'image':20,'document':10,'video':5,'audio':5}

def reserve_upload(session,workspace,sku_id,name,size):
    suffix=name.lower().rsplit('.',1)[-1]
    kind='video' if suffix=='mp4' else 'image' if suffix in {'png','jpg','jpeg'} else 'audio' if suffix in {'wav','mp3'} else 'document'
    maximum={'image':20,'document':30,'video':200,'audio':20}[kind]*1024*1024
    if size<=0 or size>maximum:raise HTTPException(413,'文件大小超限')
    sku=session.scalar(select(Record).where(Record.id==sku_id,Record.workspace==workspace,Record.kind=='sku').with_for_update())
    if sku is None or sku.data.get('deleting'):
        raise HTTPException(404,'商品不存在')
    rows=session.scalars(select(Record).where(Record.workspace==workspace,Record.kind.in_(['source','upload_reservation']))).all()
    active=[r for r in rows if r.data.get('sku_id')==sku_id and not r.data.get('deleting') and (r.kind=='source' or r.data['expires']>time.time())]
    if sum(r.data['size'] for r in active)+size>1024**3 or sum(r.data['type']==kind for r in active)>=SOURCE_COUNTS[kind]:raise HTTPException(413,'商品素材配额不足')
    reservation=Record(id=str(uuid.uuid4()),workspace=workspace,kind='upload_reservation',data={'sku_id':sku_id,'size':size,'type':kind,'expires':time.time()+900})
    session.add(reservation);session.commit()
    return reservation

def release_upload(session,reservation):
    session.delete(reservation);session.commit()
