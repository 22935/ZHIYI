from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


class CodebaseSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="codebase_search",
                domain="programmer",
                capabilities=["codebase_semantic_search"],
                allowedSkills=["codebase_semantic_search"],
                description="Finds reusable authentication and permission code in the current project.",
            )
        )

    async def run(self, context):
        requirement = str(context.task.input.get("requirement") or context.task.title).strip()
        hits = [
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/config/SecurityConfig.java",
                "language": "java",
                "score": 0.84,
                "content": "已有 Spring Security 过滤链，可借鉴公开路径、鉴权入口和无状态会话配置。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/filter/JwtAuthenticationFilter.java",
                "language": "java",
                "score": 0.81,
                "content": "已有 JWT 解析与用户上下文注入逻辑，可迁移为 FastAPI dependency/middleware。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/util/JwtUtil.java",
                "language": "java",
                "score": 0.79,
                "content": "已有 Token 生成、校验、过期处理思路，可复用 claims 设计。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/controller/AuthController.java",
                "language": "java",
                "score": 0.76,
                "content": "已有登录/注册接口形态，可对齐 /auth/login 的输入输出。",
            },
        ]
        return AgentOutput(
            output={
                "query": "FastAPI JWT auth permission existing code",
                "top_k": 5,
                "hits": hits,
                "index_status": {
                    "success": True,
                    "message": "模拟检索结果：当前仓库已有 Java/Spring 认证代码，可作为 FastAPI 版本的设计参考。",
                },
                "source_query": requirement[:160],
            },
            summary=f"Codebase search completed with {len(hits)} simulated hit(s).",
        )
