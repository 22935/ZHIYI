import asyncio
import time
from types import SimpleNamespace

from app.ai_engine.kylin_sdk.client import KylinSDKClient


async def test_deepseek_generation_does_not_block_the_event_loop():
    client = KylinSDKClient(api_key="", api_endpoint="http://unused")

    class BlockingDeepSeekAdapter:
        def chat(self, **_kwargs):
            time.sleep(0.15)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(total_tokens=1),
            )

    client.use_deepseek = True
    client.deepseek_adapter = BlockingDeepSeekAdapter()

    started = time.perf_counter()
    generation = asyncio.create_task(client.generate_text("hello"))
    await asyncio.sleep(0.01)
    heartbeat_elapsed = time.perf_counter() - started
    result = await generation
    await client.client.aclose()

    assert heartbeat_elapsed < 0.08
    assert result["text"] == "ok"
