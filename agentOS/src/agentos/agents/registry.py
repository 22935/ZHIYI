"""AgentOS Core 的智能体注册表，负责按领域、名称和能力解析应用层 Pack 智能体。"""


from typing import Dict, Iterable, Optional, Tuple

from agentos.agents.base import BaseAgent


class AgentNotFound(KeyError):
    """工作流步骤找不到匹配智能体时抛出。"""


class AgentRegistry:
    """供 Core 解析应用层 Pack 智能体的注册表。"""

    def __init__(self):
        self._agents: Dict[Tuple[str, str], BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        domain = (agent.profile.domain or "").strip().lower()
        name = (agent.profile.agent_name or "").strip().lower()
        if not domain or not name:
            raise ValueError("agent domain and agentName are required")
        self._agents[(domain, name)] = agent

    def resolve(
        self,
        domain: str,
        agent_name: Optional[str] = None,
        capability: Optional[str] = None,
        *,
        allowed_agent_ids: Iterable[str] | None = None,
    ) -> BaseAgent:
        normalized_domain = (domain or "").strip().lower()
        normalized_name = (agent_name or "").strip().lower()

        allowed = set(allowed_agent_ids) if allowed_agent_ids is not None else None

        if normalized_name:
            agent = self._agents.get((normalized_domain, normalized_name))
            if agent is not None and (
                allowed is None or self.agent_id(agent) in allowed
            ):
                return agent
            if normalized_domain != "general":
                agent = self._agents.get(("general", normalized_name))
                if agent is not None and (
                    allowed is None or self.agent_id(agent) in allowed
                ):
                    return agent

        normalized_capability = (capability or "").strip().lower()
        if normalized_capability:
            candidate_domains = (
                (normalized_domain, "general")
                if normalized_domain != "general"
                else ("general",)
            )
            for candidate_domain in candidate_domains:
                for (agent_domain, _), agent in self._agents.items():
                    if agent_domain != candidate_domain:
                        continue
                    if allowed is not None and self.agent_id(agent) not in allowed:
                        continue
                    if normalized_capability in {
                        item.lower() for item in agent.profile.capabilities
                    }:
                        return agent

        raise AgentNotFound(
            f"agent not registered: domain={domain}, agentName={agent_name}, capability={capability}"
        )

    def all(self) -> Iterable[BaseAgent]:
        return tuple(self._agents.values())

    @staticmethod
    def agent_id(agent: BaseAgent) -> str:
        return str(agent.profile.agent_id or agent.profile.agent_name)

    def scoped(self, agent_ids: Iterable[str]) -> "ScopedAgentRegistry":
        return ScopedAgentRegistry(self, tuple(agent_ids))


class ScopedAgentRegistry:
    """Read-only per-run view over the process-wide AgentRegistry."""

    def __init__(self, registry: AgentRegistry, agent_ids: tuple[str, ...]) -> None:
        self._registry = registry
        self._agent_ids = frozenset(agent_ids)

    def all(self) -> Iterable[BaseAgent]:
        return tuple(
            agent
            for agent in self._registry.all()
            if self._registry.agent_id(agent) in self._agent_ids
        )

    def agent_id(self, agent: BaseAgent) -> str:
        return self._registry.agent_id(agent)

    def resolve(
        self,
        domain: str,
        agent_name: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> BaseAgent:
        return self._registry.resolve(
            domain,
            agent_name,
            capability,
            allowed_agent_ids=self._agent_ids,
        )
