from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


ARCHITECTURE_MERMAID = """flowchart LR
    Client[客户端/前端] -->|POST /auth/login| AuthRouter[FastAPI Auth Router]
    AuthRouter --> AuthService[Auth Service]
    AuthService --> UserRepo[(User DB)]
    AuthService --> PasswordHasher[passlib bcrypt]
    AuthService --> JwtProvider[JWT Provider]
    Client -->|Bearer Token| ProtectedRouter[Protected API Router]
    ProtectedRouter --> AuthDependency[JWT Verify Dependency]
    AuthDependency --> JwtProvider
    AuthDependency --> PermissionGuard[Permission Guard]
    PermissionGuard --> ProtectedRouter
    ProtectedRouter --> DomainService[业务服务]"""


LOGIN_SEQUENCE_MERMAID = """sequenceDiagram
    participant U as User
    participant C as Client
    participant API as FastAPI /auth/login
    participant DB as User DB
    participant JWT as JWT Provider
    U->>C: 输入用户名和密码
    C->>API: POST /auth/login
    API->>DB: 按 username 查询用户
    DB-->>API: 返回用户与 hashed_password
    API->>API: bcrypt 校验密码
    alt 密码正确且用户启用
        API->>JWT: 生成 access_token
        JWT-->>API: signed JWT
        API-->>C: 200 {access_token, token_type, expires_in}
        C-->>U: 登录成功
    else 认证失败
        API-->>C: 401/403
        C-->>U: 展示错误信息
    end"""


class DiagramGenerationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="diagram_generation",
                domain="programmer",
                capabilities=["diagram_generation"],
                allowedSkills=["diagram_generation"],
                description="Generates Mermaid diagrams from programmer workflow artifacts.",
            )
        )

    async def run(self, context):
        requirement = str(context.task.input.get("requirement") or context.task.title).strip()
        return AgentOutput(
            output={
                "title": "FastAPI JWT 用户认证与权限管理",
                "diagram_type": "mermaid",
                "mermaid_code": ARCHITECTURE_MERMAID,
                "sequence_mermaid_code": LOGIN_SEQUENCE_MERMAID,
                "source_query": requirement[:160],
            },
            summary="Diagram generation completed.",
        )
