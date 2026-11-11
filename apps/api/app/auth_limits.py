"""Atomic database-backed login windows shared by all API processes."""
import hashlib,time
from sqlalchemy import String,Integer,Float,case
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,Session
class LoginRateLimit(Base):
    __tablename__='login_rate_limits'
    key:Mapped[str]=mapped_column(String,primary_key=True)
    count:Mapped[int]=mapped_column(Integer)
    expires:Mapped[float]=mapped_column(Float,index=True)

def consume(scope,identity,now=None,sessions=Session):
    now=time.time() if now is None else now
    key=hashlib.sha256((scope+':'+identity).encode()).hexdigest()
    with sessions.begin() as session:
        dialect=session.get_bind().dialect.name
        if dialect=='postgresql':from sqlalchemy.dialects.postgresql import insert
        elif dialect=='sqlite':from sqlalchemy.dialects.sqlite import insert
        else:raise RuntimeError('Unsupported login rate-limit database')
        reset=LoginRateLimit.expires<=now
        statement=insert(LoginRateLimit).values(key=key,count=1,expires=now+60)
        statement=statement.on_conflict_do_update(index_elements=['key'],set_={'count':case((reset,1),(LoginRateLimit.count>=6,6),else_=LoginRateLimit.count+1),'expires':case((reset,now+60),else_=LoginRateLimit.expires)}).returning(LoginRateLimit.count,LoginRateLimit.expires)
        count,expires=session.execute(statement).one()
    return count<=5,max(1,int(expires-now))
