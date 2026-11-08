-- Workspace authority only; Run/Step/Attempt state remains in AgentOS.
CREATE TABLE local_workspace_authorizations (
    workspace_id VARCHAR(80) PRIMARY KEY,
    user_id VARCHAR(160) NOT NULL,
    tenant_id VARCHAR(160) NOT NULL,
    canonical_root TEXT NOT NULL,
    root_identity TEXT NOT NULL,
    resource_id VARCHAR(200) NOT NULL,
    grant_id VARCHAR(100) NOT NULL UNIQUE,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ,
    UNIQUE (user_id, tenant_id, canonical_root, grant_id)
);
CREATE UNIQUE INDEX local_workspace_one_selected ON local_workspace_authorizations(user_id, tenant_id)
    WHERE selected AND NOT revoked;
