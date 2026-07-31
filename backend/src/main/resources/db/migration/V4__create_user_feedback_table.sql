CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    conversation_id UUID,
    message_id UUID,
    role_id UUID,
    feedback_type VARCHAR(50) NOT NULL,
    rating INTEGER,
    content TEXT,
    sentiment VARCHAR(20),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_user ON user_feedback(user_id);
CREATE INDEX idx_feedback_conversation ON user_feedback(conversation_id);
CREATE INDEX idx_feedback_message ON user_feedback(message_id);
CREATE INDEX idx_feedback_role ON user_feedback(role_id);
CREATE INDEX idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX idx_feedback_sentiment ON user_feedback(sentiment);
CREATE INDEX idx_feedback_created ON user_feedback(created_at);
