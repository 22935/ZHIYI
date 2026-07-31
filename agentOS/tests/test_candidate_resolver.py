from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.recovery import CandidateResolver, ExecutionBinding


class _Agent(BaseAgent):
    def __init__(self, name, *, domain="test", skills=None, priority=0, enabled=True):
        super().__init__(
            AgentProfile(
                agentName=name,
                agentId=f"id-{name}",
                domain=domain,
                capabilities=["analyze"],
                allowedSkills=skills or [],
                bindingPriority=priority,
                enabled=enabled,
            )
        )

    async def run(self, context):
        return AgentOutput(output={})


def _resolver():
    registry = AgentRegistry()
    registry.register(_Agent("first", skills=["search"], priority=1))
    registry.register(_Agent("second", skills=["search", "verify"], priority=5))
    registry.register(_Agent("disabled", skills=["search"], priority=9, enabled=False))
    registry.register(_Agent("foreign", domain="other", skills=["search"], priority=10))
    return CandidateResolver(registry)


def test_resolver_returns_all_compatible_candidates_in_stable_priority_order():
    resolver = _resolver()
    first = resolver.resolve_candidates(
        domain="test", capability="analyze", required_skills=["search"]
    )
    second = resolver.resolve_candidates(
        domain="test", capability="analyze", required_skills=["search"]
    )

    assert [item.agent_name for item in first] == ["second", "first"]
    assert [item.binding_id for item in first] == [item.binding_id for item in second]
    assert all(isinstance(item, ExecutionBinding) for item in first)
    assert ExecutionBinding.from_agent(
        next(iter(_resolver().agent_registry.all())),
        capability="analyze",
        registration_order=0,
    ).binding_id == first[1].binding_id


def test_resolver_filters_domain_skills_disabled_and_excluded_bindings():
    resolver = _resolver()
    candidates = resolver.resolve_candidates(
        domain="test", capability="analyze", required_skills=["verify"]
    )
    assert [item.agent_name for item in candidates] == ["second"]

    excluded = resolver.resolve_candidates(
        domain="test",
        capability="analyze",
        required_skills=["search"],
        excluded_binding_ids=[candidates[0].binding_id],
    )
    assert [item.agent_name for item in excluded] == ["first"]
    assert resolver.resolve_candidates(domain="other", capability="missing") == []
