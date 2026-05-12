# 联邦智枢 Backend

Spring Boot后端服务

## 技术栈

- Spring Boot 3.2.0
- Java 17
- PostgreSQL
- Redis
- WebClient (调用Python AI服务)

## 项目结构

```
backend/
├── src/main/java/com/kinlin/ai/
│   ├── config/          # 配置类
│   ├── controller/     # 控制器层
│   ├── service/         # 业务逻辑层
│   ├── repository/      # 数据访问层
│   ├── entity/         # 实体类
│   ├── dto/            # 数据传输对象
│   └── exception/      # 异常处理
```

## 启动说明

1. 配置数据库和Redis
2. 修改 `application.yml` 中的配置
3. 运行 `KinlinAiApplication.main()`

## API接口

- `POST /api/chat/text` - 发送文本消息
- `GET /api/chat/history/{contextId}` - 获取对话历史
- `GET /api/roles/builtin` - 获取内置角色

