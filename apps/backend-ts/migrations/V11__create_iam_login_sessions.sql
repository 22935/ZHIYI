-- INT-2F-4A：IAM 登录会话持久权威（服务端撤销最小实现）。
-- 每次登录一行；revoked_at 非空即撤销，expires_at 到期为派生失效，不落第二份状态。
CREATE TABLE iam_login_sessions (
    sid UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP
);

CREATE INDEX idx_iam_login_sessions_user ON iam_login_sessions(user_id);
CREATE INDEX idx_iam_login_sessions_expires ON iam_login_sessions(expires_at);
