ALTER TABLE records ADD COLUMN created_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE records ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE tasks ADD COLUMN created_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE tasks ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
CREATE INDEX ix_records_workspace_kind_created ON records(workspace,kind,created_at DESC,id);
CREATE INDEX ix_tasks_workspace_created ON tasks(workspace,created_at DESC,id);
