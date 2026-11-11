"""PostgreSQL-only rate-limit concurrency evidence in an isolated random schema."""
import os,uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.auth_limits import consume
engine=create_engine(os.environ['DATABASE_URL'])
if engine.dialect.name!='postgresql':raise RuntimeError('PostgreSQL required')
schema='verify_login_'+uuid.uuid4().hex
with engine.begin() as connection:connection.execute(text('CREATE SCHEMA '+schema))
scoped=engine.execution_options(schema_translate_map={None:schema})
try:
    Base.metadata.create_all(scoped);sessions=sessionmaker(scoped)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(lambda _:consume('ip','concurrent',now=100,sessions=sessions)[0],range(16)))
    assert sum(outcomes)==5,outcomes
    assert not consume('ip','concurrent',now=159,sessions=sessionmaker(scoped))[0]
    assert consume('ip','concurrent',now=160,sessions=sessions)[0]
    print('PostgreSQL login limiter: 5 of 16 admitted; persistence and expiry passed')
finally:
    with engine.begin() as connection:connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    engine.dispose()
