-- 深度下线四个内置角色（律师/教师/程序员/作家）：
-- 产品已不再使用内置角色，删除历史播种数据，防止它们继续出现在角色选择、
-- 语音角色下拉与用户画像中。自定义角色（CUSTOM）不受影响。
-- conversations.role_id / user_feedback.role_id 为可空且无外键，遗留引用按孤儿 id 容忍。
DELETE FROM roles WHERE role_type = 'BUILTIN';
