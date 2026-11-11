from sqlalchemy import create_engine, String, Integer, JSON, ForeignKey,Index,func,and_,DateTime
from datetime import datetime,timezone
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
import os, uuid

class Base(DeclarativeBase): pass
class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda:str(uuid.uuid4()))
    workspace: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True),nullable=True,default=lambda:datetime.now(timezone.utc),server_default=func.now())
_merchant_sku=func.coalesce(func.nullif(Record.data['merchant_sku'].as_string(),''),Record.data['model'].as_string())
_sku_filter=and_(Record.kind=='sku',_merchant_sku!='')
Index('uq_workspace_merchant_sku',Record.workspace,_merchant_sku,unique=True,postgresql_where=_sku_filter,sqlite_where=_sku_filter)
Index('ix_records_workspace_kind_created',Record.workspace,Record.kind,Record.created_at.desc(),Record.id)
engine = create_engine(os.environ.get('DATABASE_URL', 'sqlite:///./development.db'))
Session = sessionmaker(engine, expire_on_commit=False)

def initialize(): Base.metadata.create_all(engine)
