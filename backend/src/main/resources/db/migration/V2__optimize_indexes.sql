CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created ON users(created_at);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_role ON conversations(role_id);
CREATE INDEX idx_conversations_user_role ON conversations(user_id, role_id);
CREATE INDEX idx_conversations_updated ON conversations(updated_at);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_type ON messages(message_type);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);
CREATE INDEX idx_roles_name ON roles(name);
CREATE INDEX idx_roles_created ON roles(created_at);
CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at DESC);

ANALYZE users;
ANALYZE roles;
ANALYZE conversations;
ANALYZE messages;
