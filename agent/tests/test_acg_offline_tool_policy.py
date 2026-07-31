from packs.legal.agents.statute import StatuteAgent


def test_legal_statute_agent_uses_only_local_tools_while_acg_is_offline():
    assert set(StatuteAgent().profile.allowed_tools) == {
        "knowledge_search",
        "current_datetime",
    }
