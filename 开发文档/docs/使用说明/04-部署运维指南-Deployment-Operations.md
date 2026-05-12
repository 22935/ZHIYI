# 联邦智枢 技术文档 - 部署和运维指南

## 文档版本
- **版本号**: v1.0.0
- **更新日期**: 2025-01-02
- **文档作者**: 联邦智枢 开发团队

---

## 目录

1. [系统要求](#1-系统要求)
2. [部署方式](#2-部署方式)
3. [环境配置](#3-环境配置)
4. [部署步骤](#4-部署步骤)
5. [运维管理](#5-运维管理)
6. [故障排查](#6-故障排查)
7. [性能优化](#7-性能优化)
8. [安全配置](#8-安全配置)

---

## 1. 系统要求

### 1.1 硬件要求

#### 最低配置
- **CPU**: 4核心
- **内存**: 8GB RAM
- **存储**: 50GB 可用空间
- **网络**: 100Mbps 带宽

#### 推荐配置
- **CPU**: 8核心或更多
- **内存**: 16GB RAM 或更多
- **存储**: 100GB+ SSD
- **网络**: 1Gbps 带宽

### 1.2 软件要求

#### 操作系统
- **推荐**: 银河麒麟操作系统 (KylinOS) V10
- **支持**: Ubuntu 20.04+, CentOS 7+, Windows Server 2019+

#### 运行时环境
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **Java**: 17+ (如果手动部署后端)
- **Python**: 3.8+ (如果手动部署AI服务)
- **Node.js**: 18+ (如果手动部署前端)

### 1.3 依赖服务

- **PostgreSQL**: 14+ (数据库)
- **Redis**: 7+ (缓存)
- **Nginx**: 1.20+ (反向代理，可选)

---

## 2. 部署方式

### 2.1 Docker部署（推荐）

Docker部署是最简单、最推荐的部署方式，适合大多数场景。

**优点**:
- 环境隔离，避免依赖冲突
- 一键部署，简单快速
- 易于管理和维护
- 支持快速扩展

### 2.2 手动部署

手动部署适合需要自定义配置的场景。

**优点**:
- 完全控制部署过程
- 可以自定义配置
- 适合特殊环境

### 2.3 部署包部署

使用预构建的部署包进行部署，适合离线环境。

**优点**:
- 无需编译，快速部署
- 适合离线环境
- 包含所有依赖

---

## 3. 环境配置

### 3.1 环境变量配置

创建 `.env` 文件（在项目根目录）：

```bash
# 数据库配置
SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/kinlin_ai
SPRING_DATASOURCE_USERNAME=kinlin_ai
SPRING_DATASOURCE_PASSWORD=your_password_here
DB_USERNAME=kinlin_ai
DB_PASSWORD=your_password_here

# Redis配置
SPRING_REDIS_HOST=localhost
SPRING_REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# AI服务配置
DASHSCOPE_API_KEY=sk-your_api_key_here
QWEN_MODEL_BALANCED=qwen-plus

# JWT配置
APP_JWT_SECRET=your_jwt_secret_key_at_least_64_characters_long

# 服务端口
SERVER_PORT=8090
AI_SERVICE_PORT=8000
FRONTEND_PORT=80

# 环境
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### 3.2 配置文件

#### 后端配置 (`backend/src/main/resources/application.yml`)

```yaml
server:
  port: ${SERVER_PORT:8090}

spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
  
  data:
    redis:
      host: ${SPRING_REDIS_HOST}
      port: ${SPRING_REDIS_PORT}
      password: ${SPRING_REDIS_PASSWORD:}

app:
  jwt:
    secret: ${APP_JWT_SECRET}
    expiration: 86400000
```

#### AI服务配置 (`agent/app/config.py`)

```python
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 通义千问配置
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    qwen_model_balanced: str = os.getenv("QWEN_MODEL_BALANCED", "qwen-plus")
    
    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 4. 部署步骤

### 4.1 Docker部署

#### 4.1.1 快速部署

```bash
# 1. 克隆项目
git clone <repository-url>
cd Kinlin_AI

# 2. 配置环境变量
cp .env.example .env
vim .env  # 编辑配置文件

# 3. 启动服务
chmod +x scripts/deploy.sh
./scripts/deploy.sh prod
```

#### 4.1.2 详细部署步骤

**步骤1: 准备环境**

```bash
# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**步骤2: 配置环境变量**

```bash
# 创建.env文件
cat > .env << EOF
DB_USERNAME=kinlin_ai
DB_PASSWORD=your_secure_password
REDIS_PASSWORD=your_redis_password
DASHSCOPE_API_KEY=sk-your_api_key
APP_JWT_SECRET=your_jwt_secret_at_least_64_characters
EOF
```

**步骤3: 启动服务**

```bash
# 使用生产环境配置
docker-compose -f docker/docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker/docker-compose.prod.yml ps

# 查看日志
docker-compose -f docker/docker-compose.prod.yml logs -f
```

**步骤4: 验证部署**

```bash
# 检查后端服务
curl http://localhost:8090/health

# 检查AI服务
curl http://localhost:8000/health

# 检查前端服务
curl http://localhost:80
```

### 4.2 手动部署

#### 4.2.1 部署数据库

```bash
# 安装PostgreSQL
sudo apt-get update
sudo apt-get install postgresql-14

# 创建数据库
sudo -u postgres psql
CREATE DATABASE kinlin_ai;
CREATE USER kinlin_ai WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE kinlin_ai TO kinlin_ai;
\q

# 运行数据库迁移
cd backend
mvn flyway:migrate
```

#### 4.2.2 部署Redis

```bash
# 安装Redis
sudo apt-get install redis-server

# 配置Redis
sudo vim /etc/redis/redis.conf
# 设置密码: requirepass your_redis_password

# 启动Redis
sudo systemctl start redis
sudo systemctl enable redis
```

#### 4.2.3 部署后端服务

```bash
# 编译后端
cd backend
mvn clean package -DskipTests

# 运行后端
java -jar target/kinlin-ai-backend-1.0.0.jar \
  --spring.profiles.active=prod \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/kinlin_ai \
  --spring.datasource.username=kinlin_ai \
  --spring.datasource.password=your_password
```

#### 4.2.4 部署AI服务

```bash
# 安装Python依赖
cd agent
pip install -r requirements.txt

# 配置环境变量
export DASHSCOPE_API_KEY=sk-your_api_key

# 启动AI服务
python app/main.py
```

#### 4.2.5 部署前端服务

```bash
# 安装依赖
cd frontend
npm install

# 构建前端
npm run build

# 使用Nginx部署
sudo cp -r dist/* /var/www/html/
sudo systemctl restart nginx
```

### 4.3 部署包部署

#### 4.3.1 创建部署包

```bash
# 运行部署包创建脚本
./scripts/create-deployment-package.sh v1.0.0
```

#### 4.3.2 部署部署包

```bash
# 上传部署包到服务器
scp deployment-package/kinlin-ai-deploy-*.tar.gz user@server:/opt/

# 在服务器上解压
cd /opt
tar -xzf kinlin-ai-deploy-*.tar.gz
cd kinlin-ai-*

# 配置环境变量
cp config/.env.template .env
vim .env

# 运行部署脚本
./deploy.sh
```

---

## 5. 运维管理

### 5.1 服务管理

#### 5.1.1 启动服务

```bash
# Docker方式
docker-compose -f docker/docker-compose.prod.yml up -d

# 手动方式
# 后端
systemctl start kinlin-ai-backend

# AI服务
systemctl start kinlin-ai-agent

# 前端
systemctl start nginx
```

#### 5.1.2 停止服务

```bash
# Docker方式
docker-compose -f docker/docker-compose.prod.yml down

# 手动方式
systemctl stop kinlin-ai-backend
systemctl stop kinlin-ai-agent
systemctl stop nginx
```

#### 5.1.3 重启服务

```bash
# Docker方式
docker-compose -f docker/docker-compose.prod.yml restart

# 手动方式
systemctl restart kinlin-ai-backend
systemctl restart kinlin-ai-agent
systemctl restart nginx
```

#### 5.1.4 查看服务状态

```bash
# Docker方式
docker-compose -f docker/docker-compose.prod.yml ps

# 手动方式
systemctl status kinlin-ai-backend
systemctl status kinlin-ai-agent
systemctl status nginx
```

### 5.2 日志管理

#### 5.2.1 查看日志

```bash
# Docker方式
docker-compose -f docker/docker-compose.prod.yml logs -f backend
docker-compose -f docker/docker-compose.prod.yml logs -f ai-service
docker-compose -f docker/docker-compose.prod.yml logs -f frontend

# 手动方式
# 后端日志
tail -f backend/logs/application.log

# AI服务日志
tail -f agent/logs/kinlin_ai.log

# Nginx日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

#### 5.2.2 日志轮转

配置日志轮转（使用logrotate）：

```bash
# 创建logrotate配置
sudo vim /etc/logrotate.d/kinlin-ai

# 配置内容
/opt/kinlin-ai/backend/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 kinlin kinlin
}
```

### 5.3 监控管理

#### 5.3.1 健康检查

```bash
# 后端健康检查
curl http://localhost:8090/actuator/health

# AI服务健康检查
curl http://localhost:8000/health

# 前端健康检查
curl http://localhost:80
```

#### 5.3.2 性能监控

```bash
# 查看系统资源
htop

# 查看Docker容器资源
docker stats

# 查看数据库连接
psql -U kinlin_ai -d kinlin_ai -c "SELECT count(*) FROM pg_stat_activity;"

# 查看Redis状态
redis-cli info
```

#### 5.3.3 指标收集

系统提供以下监控指标：

- **响应时间**: 平均响应时间、P95、P99
- **吞吐量**: 每秒请求数
- **错误率**: 错误请求比例
- **资源使用**: CPU、内存、磁盘使用率

访问监控端点：

```bash
# 获取性能指标
curl http://localhost:8090/api/metrics

# 获取系统统计
curl http://localhost:8090/api/statistics/system
```

### 5.4 备份和恢复

#### 5.4.1 数据库备份

```bash
# 备份数据库
pg_dump -U kinlin_ai -d kinlin_ai > backup_$(date +%Y%m%d).sql

# 定时备份（使用cron）
0 2 * * * pg_dump -U kinlin_ai -d kinlin_ai > /backup/kinlin_ai_$(date +\%Y\%m\%d).sql
```

#### 5.4.2 数据库恢复

```bash
# 恢复数据库
psql -U kinlin_ai -d kinlin_ai < backup_20250102.sql
```

#### 5.4.3 文件备份

```bash
# 备份上传文件
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz agent/data/

# 备份配置文件
tar -czf config_backup_$(date +%Y%m%d).tar.gz .env config/
```

---

## 6. 故障排查

### 6.1 常见问题

#### 6.1.1 服务无法启动

**问题**: 服务启动失败

**排查步骤**:
1. 检查日志文件
2. 检查端口是否被占用
3. 检查配置文件是否正确
4. 检查依赖服务是否正常

**解决方案**:
```bash
# 检查端口占用
netstat -tulpn | grep 8090
netstat -tulpn | grep 8000

# 检查服务状态
systemctl status kinlin-ai-backend
docker ps -a

# 查看详细日志
journalctl -u kinlin-ai-backend -n 100
```

#### 6.1.2 数据库连接失败

**问题**: 无法连接到数据库

**排查步骤**:
1. 检查数据库服务是否运行
2. 检查连接配置是否正确
3. 检查网络连接
4. 检查防火墙设置

**解决方案**:
```bash
# 检查数据库服务
systemctl status postgresql

# 测试数据库连接
psql -U kinlin_ai -d kinlin_ai -h localhost

# 检查防火墙
sudo ufw status
sudo ufw allow 5432/tcp
```

#### 6.1.3 Redis连接失败

**问题**: 无法连接到Redis

**排查步骤**:
1. 检查Redis服务是否运行
2. 检查密码是否正确
3. 检查网络连接

**解决方案**:
```bash
# 检查Redis服务
systemctl status redis

# 测试Redis连接
redis-cli -a your_password ping

# 检查Redis配置
redis-cli -a your_password CONFIG GET requirepass
```

#### 6.1.4 AI服务调用失败

**问题**: AI服务返回错误

**排查步骤**:
1. 检查API密钥是否正确
2. 检查网络连接
3. 检查服务日志
4. 检查API配额

**解决方案**:
```bash
# 检查API密钥
echo $DASHSCOPE_API_KEY

# 测试API连接
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","input":{"messages":[{"role":"user","content":"你好"}]}}'

# 查看AI服务日志
tail -f agent/logs/kinlin_ai.log
```

### 6.2 性能问题

#### 6.2.1 响应慢

**问题**: 系统响应缓慢

**排查步骤**:
1. 检查系统资源使用情况
2. 检查数据库查询性能
3. 检查缓存命中率
4. 检查网络延迟

**解决方案**:
```bash
# 检查系统资源
top
htop
iostat -x 1

# 检查数据库性能
psql -U kinlin_ai -d kinlin_ai -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# 检查Redis性能
redis-cli --latency
redis-cli INFO stats
```

#### 6.2.2 内存泄漏

**问题**: 内存使用持续增长

**排查步骤**:
1. 检查Java堆内存使用
2. 检查Python内存使用
3. 检查缓存大小

**解决方案**:
```bash
# 检查Java内存
jmap -heap <pid>
jstat -gc <pid> 1000

# 检查Python内存
python -m memory_profiler app/main.py

# 清理Redis缓存
redis-cli FLUSHALL
```

### 6.3 日志分析

#### 6.3.1 错误日志分析

```bash
# 查找错误日志
grep -i error backend/logs/application.log | tail -20

# 查找异常堆栈
grep -A 20 "Exception" backend/logs/application.log | tail -50
```

#### 6.3.2 性能日志分析

```bash
# 查找慢查询
grep "slow query" backend/logs/application.log

# 查找高延迟请求
grep "response_time" backend/logs/application.log | awk '{if($NF > 2.0) print}'
```

---

## 7. 性能优化

### 7.1 数据库优化

#### 7.1.1 索引优化

```sql
-- 创建索引
CREATE INDEX idx_message_conversation_id ON message(conversation_id);
CREATE INDEX idx_message_created_at ON message(created_at);
CREATE INDEX idx_conversation_user_id ON conversation(user_id);

-- 分析查询计划
EXPLAIN ANALYZE SELECT * FROM message WHERE conversation_id = 'xxx';
```

#### 7.1.2 连接池优化

```yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000
```

### 7.2 缓存优化

#### 7.2.1 Redis配置优化

```bash
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

#### 7.2.2 缓存策略

- **对话上下文缓存**: 缓存时间 1小时
- **角色配置缓存**: 缓存时间 24小时
- **RAG检索结果缓存**: 缓存时间 30分钟

### 7.3 应用优化

#### 7.3.1 JVM参数优化

```bash
java -Xms2g -Xmx4g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:+HeapDumpOnOutOfMemoryError \
  -jar kinlin-ai-backend-1.0.0.jar
```

#### 7.3.2 异步处理

```java
@Async
public CompletableFuture<ChatResponse> processMessageAsync(ChatRequest request) {
    // 异步处理消息
}
```

### 7.4 网络优化

#### 7.4.1 Nginx配置优化

```nginx
# nginx.conf
worker_processes auto;
worker_connections 1024;

http {
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    gzip_min_length 1000;
    
    client_max_body_size 10M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
}
```

---

## 8. 安全配置

### 8.1 认证和授权

#### 8.1.1 JWT配置

```yaml
app:
  jwt:
    secret: ${APP_JWT_SECRET}  # 至少64字符
    expiration: 86400000  # 24小时
```

#### 8.1.2 密码加密

系统使用BCrypt算法加密密码，强度因子为10。

### 8.2 数据安全

#### 8.2.1 数据库加密

```sql
-- 启用SSL连接
ALTER SYSTEM SET ssl = on;
```

#### 8.2.2 敏感数据加密

敏感数据（如API密钥）应存储在环境变量中，不要硬编码在代码中。

### 8.3 网络安全

#### 8.3.1 HTTPS配置

```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
}
```

#### 8.3.2 防火墙配置

```bash
# 允许必要端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8090/tcp
sudo ufw enable
```

### 8.4 内容安全

#### 8.4.1 输入验证

所有用户输入都应进行验证和清理，防止SQL注入、XSS等攻击。

#### 8.4.2 内容审核

系统集成内容安全API，自动检测和过滤不当内容。

---

## 9. 总结

本文档详细介绍了联邦智枢系统的部署和运维指南，包括：

1. **系统要求**: 硬件、软件、依赖服务要求
2. **部署方式**: Docker、手动、部署包三种部署方式
3. **环境配置**: 环境变量和配置文件说明
4. **部署步骤**: 详细的部署步骤和验证方法
5. **运维管理**: 服务管理、日志管理、监控管理
6. **故障排查**: 常见问题和解决方案
7. **性能优化**: 数据库、缓存、应用、网络优化
8. **安全配置**: 认证授权、数据安全、网络安全

通过遵循本文档，可以成功部署和维护联邦智枢系统。

---

**文档结束**

