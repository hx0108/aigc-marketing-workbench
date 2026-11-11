import hashlib
import io
import os
import uuid
from pathlib import Path
from PIL import Image
from app.db import Record


def resolve_sources(sessions,job,root,configured):
    root=Path(root).resolve()
    with sessions() as session:
        request=job['payload'].get('request')
        if request is None:
            work=session.get(Record,job['payload']['work_id'])
            if not work or work.workspace!=job['workspace']:raise ValueError('work_not_found')
            creation=session.get(Record,work.data['creation_request_id'])
            if not creation or creation.workspace!=job['workspace']:raise ValueError('creation_not_found')
            request=creation.data
        sku_id=request['sku_id']
        # Synthetic fixtures remain explicit; production source selection uses persisted roles.
        if sku_id in configured:
            if not request.get('synthetic_fixture') or sku_id!='synthetic-sku':
                raise ValueError('synthetic_override_not_authorized')
            return configured[sku_id]
        ids=request.get('source_ids',request.get('profile_snapshot',{}).get('source_ids',[]))
        selection=request.get('source_selection',request.get('profile_snapshot',{}).get('source_selection',{}))
        selected_roles={value['source_id']:role for role,value in selection.items() if role in ('product','mask')}
        if selection:ids=list(selected_roles)
        result={}
        for identifier in ids:
            row=session.get(Record,identifier)
            if not row or row.workspace!=job['workspace'] or row.kind!='source' or row.data.get('sku_id')!=sku_id or not row.data.get('rights_confirmed') or row.data.get('deleting'):
                raise ValueError('source_scope_invalid')
            role=selected_roles.get(identifier) if selection else row.data.get('role')
            if role not in ('product','mask'):continue
            if selection and selection[role]['sha256']!=row.data['sha256']:
                raise ValueError('source_snapshot_hash_mismatch')
            if role in result:raise ValueError('ambiguous_product_sources')
            path=(root/row.data['object_key']).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=row.data['sha256']:
                raise ValueError('source_hash_mismatch')
            result[role]={'path':str(path),'sha256':row.data['sha256']}
        if not {'product','mask'}<=result.keys():raise ValueError('reviewed_product_and_mask_required')
    white=root/'white-background-1080x1440.png'
    buffer=io.BytesIO();Image.new('RGB',(1080,1440),'white').save(buffer,format='PNG')
    expected=buffer.getvalue()
    # Existing files are accepted only if byte-identical to the deterministic background.
    temporary=root/('white-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(expected);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,white)
        except FileExistsError:pass
    finally:
        temporary.unlink(missing_ok=True)
    if white.read_bytes()!=expected:raise ValueError('white_background_integrity')
    result['white_background']={'path':str(white),'sha256':hashlib.sha256(expected).hexdigest()}
    return result
