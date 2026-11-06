-- 下线用户反馈功能：user_feedback 自 2025-12 建表以来零写入、前端无调用方
-- （2026-11-06 审计：行数 0、pg_stat ins=0、前端 src 零引用）。
-- 控制器/服务/投影/实体已随本批删除；V4 历史迁移保留不动，索引用表级联删除。
DROP TABLE IF EXISTS user_feedback;
