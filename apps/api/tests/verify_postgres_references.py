"""Real composite FK checks in a disposable schema; no business data modified."""
import os,uuid,json
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.exc import IntegrityError

engine=create_engine(os.environ['DATABASE_URL'])
schema='verify_references_'+uuid.uuid4().hex
def insert(connection,id,workspace,kind,data):
    connection.execute(text('INSERT INTO records(id,workspace,kind,revision,data) VALUES(:id,:w,:k,1,CAST(:d AS json))'),{'id':id,'w':workspace,'k':kind,'d':json.dumps(data)})
def transaction():
    return engine.begin()
try:
    with transaction() as c:
        c.execute(text('CREATE SCHEMA '+schema));c.execute(text('SET LOCAL search_path TO '+schema))
        c.execute(text('CREATE TABLE records(id varchar PRIMARY KEY,workspace varchar NOT NULL,kind varchar NOT NULL,revision integer NOT NULL,data json NOT NULL)'))
        insert(c,'legacy','a','source',{'sku_id':'missing'})
        for statement in (Path(__file__).resolve().parents[1]/'migrations/008_workspace_references.sql').read_text().split(';'):
            if statement.strip():c.execute(text(statement))
        insert(c,'sku-a','a','sku',{});insert(c,'sku-b','b','sku',{})
        insert(c,'source','a','source',{'sku_id':'sku-a'})
        insert(c,'work','a','work',{'current_result':'result'})
        insert(c,'result','a','result_revision',{'work_id':'work'})
    failures=0
    for statement,params in [
        ('INSERT INTO records VALUES (:id,:w,:k,1,CAST(:d AS json),DEFAULT,DEFAULT,DEFAULT,DEFAULT)',{'id':'bad','w':'a','k':'source','d':json.dumps({'sku_id':'sku-b'})}),
        ("UPDATE records SET data=CAST(:d AS json) WHERE id='source'",{'d':json.dumps({'sku_id':'sku-b'})}),
        ("UPDATE records SET workspace='b' WHERE id='result'",{}),
        ("DELETE FROM records WHERE id='sku-a'",{}),
    ]:
        try:
            with transaction() as c:
                c.execute(text('SET LOCAL search_path TO '+schema));c.execute(text(statement),params)
        except IntegrityError:failures+=1
    assert failures==4,failures
    with transaction() as c:
        c.execute(text('SET LOCAL search_path TO '+schema))
        assert c.execute(text("SELECT count(*) FROM records WHERE id='legacy'")).scalar()==1
        assert c.execute(text("SELECT count(*) FROM pg_constraint WHERE conrelid='records'::regclass AND contype='f' AND NOT convalidated")).scalar()==4
    print('Composite FK: cross-workspace insert/update/workspace mutation/delete rejected; same-workspace cycle accepted; legacy retained and explicitly unvalidated')
finally:
    with transaction() as c:c.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))
    engine.dispose()
