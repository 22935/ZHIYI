import asyncio
import time
from types import SimpleNamespace

from app.llm.gateway import LLMGateway, set_llm_gateway_for_tests
from packs.legal.agents.contract_review_migration import ContractParseAgent


class _BlockingProvider:
    provider_name = "blocking-test"
    model = "blocking-test"

    def generate_text(self, prompt, **kwargs):
        return ""

    def generate_json(self, prompt, schema, **kwargs):
        time.sleep(0.15)
        return {
            "contract_title": "测试合同",
            "parties": [],
            "contract_type": "软件开发合同",
            "key_dates": [],
            "amounts": [],
            "obligations": [],
            "summary": "测试摘要",
        }


async def test_contract_llm_node_does_not_block_progress_requests():
    set_llm_gateway_for_tests(LLMGateway(provider=_BlockingProvider()))
    context = SimpleNamespace(
        task=SimpleNamespace(input={"contractText": "甲方委托乙方开发软件。"}),
        memory=SimpleNamespace(observations={}),
    )

    started = time.perf_counter()
    generation = asyncio.create_task(ContractParseAgent().run(context))
    await asyncio.sleep(0.01)
    heartbeat_elapsed = time.perf_counter() - started
    result = await generation

    assert heartbeat_elapsed < 0.08
    assert result.output["contract_type"] == "软件开发合同"
