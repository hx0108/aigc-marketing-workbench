"""Explicit forward migrations with checksums; PostgreSQL only."""
from pathlib import Path
import hashlib
from sqlalchemy import text
from .db import engine

def migrate():
    if engine.dialect.name!='postgresql':raise RuntimeError('Migrations require PostgreSQL')
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(140410)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR PRIMARY KEY, checksum VARCHAR NOT NULL)'))
        for path in sorted((Path(__file__).resolve().parents[1]/'migrations').glob('*.sql')):
            sql=path.read_text(encoding='utf-8-sig');digest=hashlib.sha256(sql.encode()).hexdigest()
            previous=conn.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'),{'v':path.name}).scalar()
            if previous:
                if previous!=digest:raise RuntimeError('Applied migration checksum changed: '+path.name)
                continue
            for statement in sql.split(';'):
                if statement.strip():conn.execute(text(statement))
            conn.execute(text('INSERT INTO schema_migrations(version,checksum) VALUES (:v,:c)'),{'v':path.name,'c':digest})
if __name__=='__main__':migrate()
