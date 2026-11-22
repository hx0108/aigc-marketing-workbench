"""Workspace credentials are stored on a private API/worker mount, outside media."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.exc import IntegrityError

from .db import Record
from .execution import Budget


class MerchantKeys(BaseModel):
    model_config = ConfigDict(extra='forbid')
    minimax: SecretStr
    deepseek: SecretStr | None = None
    dashscope: SecretStr | None = None
    cap: Decimal = Field(gt=0, le=100000, decimal_places=2)


def directory():
    path = os.environ.get('AIGC_MERCHANT_KEY_DIR')
    if not path or not Path(path).is_dir():
        raise HTTPException(503, '商家密钥存储尚未配置')
    return Path(path)


def identifier(workspace):
    return 'merchant-keys-' + hashlib.sha256(workspace.encode()).hexdigest()


def save(session, workspace, body):
    from marketing_worker.business import readiness
    if readiness():
        raise HTTPException(503, '模型服务尚未就绪')
    keys = {provider+'_API_KEY': getattr(body, provider.lower()).get_secret_value().strip()
            for provider in ('DEEPSEEK','MINIMAX','DASHSCOPE') if getattr(body,provider.lower()) is not None}
    if ('DEEPSEEK_API_KEY' in keys) != ('DASHSCOPE_API_KEY' in keys):
        raise HTTPException(422,'请单独提交 MiniMax Key，或提交完整旧版配置')
    if any(not (8 <= len(v) <= 4096 and v.isascii() and all(33 <= ord(c) <= 126 for c in v)) for v in keys.values()):
        raise HTTPException(422, '请检查 API Key')
    name = identifier(workspace)
    row = session.get(Record, name, with_for_update=True)
    version = uuid.uuid4().hex
    target = directory() / version
    with os.fdopen(os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600),'w') as out:
        json.dump(keys,out)
    previous = row.data['version'] if row else None
    try:
        if row:
            budget = session.get(Budget,name,with_for_update=True)
            if body.cap < budget.reserved + budget.settled:
                raise HTTPException(409,'累计上限低于已使用或预留金额')
            budget.cap = body.cap
            row.data = {'version':version}
        else:
            session.add(Record(id=name,workspace=workspace,kind='merchant_provider',data={'version':version}))
            session.add(Budget(id=name,workspace=workspace,cap=body.cap))
        session.commit()
    except Exception as exc:
        session.rollback()
        target.unlink(missing_ok=True)
        if isinstance(exc,IntegrityError):
            raise HTTPException(409,'配置已变化，请刷新后重试') from None
        raise
    if previous:
        (target.parent / previous).unlink(missing_ok=True)
    return {'configured':True}


def merchant_configuration(workspace, base):
    from marketing_worker.configuration import compose_configuration
    name = identifier(workspace)
    with base['sessions']() as session:
        row = session.get(Record,name,with_for_update={'read':True})
        if not row:
            return None
        version = row.data['version']
        keys = json.loads((directory()/version).read_text())
    settings = dict(base['template'],workspace=workspace,budget_id=name,sources={},
                    consent_version=base['consent_version']+'-'+version)
    if 'DEEPSEEK_API_KEY' not in keys:
        host='https://api.minimaxi.com'
        settings['providers']=dict(settings['providers'],image={'model':'MiniMax-H3-Image','base_url':'https://api.minimax.cn'},text={'model':'MiniMax-M2.7','base_url':host},tts={'model':'speech-02-turbo','base_url':host})
        settings['bounds']=dict(settings['bounds'],product_image='1.00',text='0.25',tts='2.00')
    return compose_configuration(settings,keys,base['sessions'])
