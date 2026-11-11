from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base,Record
from app.execution import Budget,Task,ExternalCall
from marketing_worker.persistence import AuthorizedServices
from marketing_worker.pipeline import ContractError
from marketing_worker.fact_validation import NumericFactError
from marketing_worker.http_providers import ExternalUnknown,TextInputTooLarge

@pytest.mark.parametrize('error,remote_workspace,expected',[(ContractError('invalid'),'one','response_received'),(NumericFactError('NUMERIC_FACT_MISMATCH'),'one','response_received'),(ContractError('invalid'),'other','external_unknown'),(ContractError('invalid'),None,'external_unknown'),(ExternalUnknown('transport'),'one','external_unknown'),(ValueError('unknown'),'one','external_unknown'),(TextInputTooLarge('large'),None,'external_unknown')])
def test_known_local_validation_keeps_reservation(error,remote_workspace,expected,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'));Base.metadata.create_all(engine);sessions=sessionmaker(engine)
    with sessions.begin() as s:
        s.add(Budget(id='b',workspace='one',cap=Decimal('10'),reserved=0,settled=0))
        s.add(Task(id='t',workspace='one',phase='creation_run',state='running',fencing_token=1,payload={}))
    def handler(payload,intent):
        if remote_workspace:
            with sessions.begin() as s:s.add(Record(id='remote:'+intent,workspace=remote_workspace,kind='provider_result',data={'response':{'choices':[]}}))
        raise error
    services=AuthorizedServices(sessions,'b',lambda *args:None,{'text':handler},{'text':'0.1'},'t','one',1)
    with pytest.raises(type(error)):services.invoke('text',{},'t:copy')
    with sessions() as s:
        assert s.get(ExternalCall,'t:copy').state==expected
        assert s.get(Budget,'b').reserved==Decimal('.1')
        assert s.get(Budget,'b').settled==0
    engine.dispose()
