CREATE INDEX IF NOT EXISTS idx_messages_conversation_role_created
    ON messages(conversation_id, role, created_at, id);
