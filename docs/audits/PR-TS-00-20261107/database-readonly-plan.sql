-- PR-TS-00: NOT EXECUTED. Run only against the verified, already-running real N03 DB.
-- Never start PostgreSQL or decrypt credentials as a side effect of this script.
-- Connect with an approved read-only account; retain only structure/anonymous aggregates.
BEGIN READ ONLY;
SELECT current_setting('server_version') AS server_version,
       current_setting('transaction_read_only') AS transaction_read_only;
SELECT installed_rank, version, description, type, script, checksum, success
FROM flyway_schema_history ORDER BY installed_rank;
SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default
FROM information_schema.columns WHERE table_schema='public'
ORDER BY table_name,ordinal_position;
SELECT tablename,indexname,indexdef FROM pg_indexes
WHERE schemaname='public' ORDER BY tablename,indexname;
SELECT c.relname AS table_name,k.conname,k.contype,pg_get_constraintdef(k.oid)
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY c.relname,k.conname;
SELECT count(*) AS user_count FROM users;
WITH actors AS (SELECT id,'U'||row_number() OVER(ORDER BY id) AS actor FROM users)
SELECT a.actor,
 (SELECT count(*) FROM conversations c WHERE c.user_id=a.id) AS conversations,
 (SELECT count(*) FROM roles r WHERE r.user_id=a.id) AS roles,
 (SELECT count(*) FROM iam_login_sessions s WHERE s.user_id=a.id) AS login_sessions
FROM actors a ORDER BY a.actor;
WITH actors AS (SELECT id::text AS id,'U'||row_number() OVER(ORDER BY id) AS actor FROM users),
tenants AS (SELECT tenant_id,'T'||row_number() OVER(ORDER BY tenant_id) AS tenant
 FROM (SELECT DISTINCT tenant_id FROM local_workspace_authorizations) t)
SELECT coalesce(a.actor,'UNMATCHED_OWNER') AS actor,t.tenant,
 count(*) AS grants,
 count(*) FILTER(WHERE w.selected) AS selected,
 count(*) FILTER(WHERE w.revoked) AS revoked,
 count(*) FILTER(WHERE w.selected AND NOT w.revoked) AS selected_live
FROM local_workspace_authorizations w
LEFT JOIN actors a ON a.id=w.user_id JOIN tenants t ON t.tenant_id=w.tenant_id
GROUP BY a.actor,t.tenant ORDER BY actor,t.tenant;
SELECT 'conversation_owner_missing' AS finding,count(*) AS n FROM conversations c
LEFT JOIN users u ON u.id=c.user_id WHERE c.user_id IS NOT NULL AND u.id IS NULL
UNION ALL SELECT 'conversation_owner_null',count(*) FROM conversations WHERE user_id IS NULL
UNION ALL SELECT 'role_owner_missing',count(*) FROM roles r
LEFT JOIN users u ON u.id=r.user_id WHERE r.user_id IS NOT NULL AND u.id IS NULL
UNION ALL SELECT 'custom_role_owner_null',count(*) FROM roles WHERE role_type='CUSTOM' AND user_id IS NULL
UNION ALL SELECT 'conversation_role_missing',count(*) FROM conversations c
LEFT JOIN roles r ON r.id=c.role_id WHERE c.role_id IS NOT NULL AND r.id IS NULL
UNION ALL SELECT 'message_conversation_missing',count(*) FROM messages m
LEFT JOIN conversations c ON c.id=m.conversation_id WHERE c.id IS NULL
UNION ALL SELECT 'workspace_owner_missing',count(*) FROM local_workspace_authorizations w
LEFT JOIN users u ON u.id::text=w.user_id WHERE u.id IS NULL
UNION ALL SELECT 'cross_owner_custom_role',count(*) FROM conversations c
JOIN roles r ON r.id=c.role_id WHERE r.role_type='CUSTOM' AND c.user_id IS DISTINCT FROM r.user_id;
SELECT count(*) AS owner_tenant_groups_with_multiple_selected FROM
(SELECT user_id,tenant_id FROM local_workspace_authorizations WHERE selected AND NOT revoked
 GROUP BY user_id,tenant_id HAVING count(*)>1) q;
SELECT count(*) AS roots_with_multiple_owners FROM
(SELECT canonical_root FROM local_workspace_authorizations
 GROUP BY canonical_root HAVING count(DISTINCT (user_id,tenant_id))>1) q;
-- No canonical_root, user UUID, username, email, message text, secret or JSON payload is output.
ROLLBACK;
