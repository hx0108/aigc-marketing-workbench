"""PRD 4.1 product identity and source completeness before confirmation."""
import hashlib
from fastapi import HTTPException
from sqlalchemy import select
from .db import Record

def validate_profile(session,workspace,profile):
    sku=session.get(Record,profile.data['sku_id'])
    if not sku or sku.workspace!=workspace or sku.kind!='sku' or sku.data.get('deleting'):raise HTTPException(404)
    missing=[]
    nonempty=lambda value:isinstance(value,str) and bool(value.strip())
    if not nonempty(sku.data.get('name')):missing.append('name')
    if not nonempty(sku.data.get('merchant_sku') or sku.data.get('model')):missing.append('merchant_sku')
    if not (nonempty(sku.data.get('specification') or sku.data.get('color')) or nonempty(sku.data.get('product_model')) or sku.data.get('single_spec_confirmed') is True):missing.append('specification_or_single_spec_confirmation')
    from .sources import ROOT
    has_image=False
    for source_id in profile.data.get('source_ids',[]):
        source=session.get(Record,source_id)
        if not source or source.workspace!=workspace or source.kind!='source' or source.data.get('sku_id')!=sku.id or source.data.get('deleting'):raise HTTPException(422,detail={'code':'SOURCE_SCOPE_INVALID'})
        if source.data.get('type')=='image' and source.data.get('role')!='mask' and source.data.get('rights_confirmed'):
            path=(ROOT/source.data['object_key']).resolve()
            if path.is_relative_to(ROOT) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==source.data['sha256']:has_image=True
    if not has_image:missing.append('current_product_image')
    if missing:raise HTTPException(422,detail={'code':'PROFILE_INCOMPLETE','message':'商品资料未完整，已保留草稿','missing_fields':missing})
    for field,actual in {'name':sku.data.get('name'),'merchant_sku':sku.data.get('merchant_sku') or sku.data.get('model'),'specification':sku.data.get('specification') or sku.data.get('color')}.items():
        if actual and field in profile.data.get('facts',{}) and profile.data['facts'][field]!=actual:raise HTTPException(422,detail={'code':'FACT_CONFLICT','field':field})
    if not profile.data.get('facts'):raise HTTPException(422,detail={'code':'FACT_REQUIRED'})
    if set(profile.data['facts'])-set(profile.data.get('fact_sources',{})):raise HTTPException(422,detail={'code':'FACT_SOURCE_REQUIRED'})
    source_ids=profile.data.get('source_ids',[])
    if source_ids:
        candidates=session.scalars(select(Record).where(Record.workspace==workspace,Record.kind=='fact_candidate',
            Record.data['sku_id'].as_string()==sku.id,Record.data['source_id'].as_string().in_(source_ids))).all()
        by_key={}
        for candidate in candidates:
            data=candidate.data
            by_key.setdefault(data['key'],[]).append((data['source_id'],data['value']))
        unresolved=[key for key,values in by_key.items() if len({value for _,value in values})>1 and
            (profile.data['fact_sources'].get(key,{}).get('source_id'),profile.data['facts'].get(key)) not in values]
        if unresolved:raise HTTPException(409,detail={'code':'FACT_CONFLICT_UNRESOLVED','keys':sorted(unresolved)})
