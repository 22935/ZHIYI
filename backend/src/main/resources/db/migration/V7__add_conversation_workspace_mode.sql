ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS workspace_mode VARCHAR(16) NOT NULL DEFAULT 'chat';

UPDATE conversations
SET workspace_mode = 'chat'
WHERE workspace_mode IS NULL OR workspace_mode NOT IN ('agent', 'chat');

ALTER TABLE conversations
    ADD CONSTRAINT chk_conversations_workspace_mode
    CHECK (workspace_mode IN ('agent', 'chat'));

CREATE INDEX IF NOT EXISTS idx_conversations_user_workspace_updated
    ON conversations(user_id, workspace_mode, updated_at DESC);
