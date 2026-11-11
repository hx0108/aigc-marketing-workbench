"""Read-only counts, without exposing IDs/content or claiming legacy validation."""
import os
from sqlalchemy import create_engine,text
engine=create_engine(os.environ['DATABASE_URL'])
references={'sku_id':('source','profile','work','creation_request'),'profile_id':('work','creation_request'),'work_id':('asset','result_revision'),'current_result':('work',)}
with engine.connect() as connection:
    for field,kinds in references.items():
        rows=connection.execute(text("SELECT count(*) FILTER (WHERE target.id IS NULL) AS missing, count(*) FILTER (WHERE target.id IS NOT NULL AND target.workspace<>source.workspace) AS cross_workspace FROM records source LEFT JOIN records target ON target.id=source.data->>:field WHERE source.kind=ANY(:kinds) AND NULLIF(source.data->>:field,'') IS NOT NULL"),{'field':field,'kinds':list(kinds)}).one()
        print(field, 'missing=',rows.missing,'cross_workspace=',rows.cross_workspace)
engine.dispose()
