"""Thin request-scoped bridge to the independent TypeScript engine.

No algorithm duplication: this host supplies budget/Provider adapters and returns
SDK ModelInputData. Child processes never receive API credentials or run tools.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)
WORKER = Path(__file__).resolve().parents[3] / "oscode-context" / "src" / "worker.ts"


class CompactionBridgeError(RuntimeError):
    pass


def _wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _upper_bound(messages, instructions, tools):
    def images(value):
        if isinstance(value, dict):
            return int(value.get("type") in {"input_image", "image_url", "image"}) + sum(images(v) for v in value.values())
        return sum(images(v) for v in value) if isinstance(value, list) else 0
    return (len(instructions.encode("utf8")) + (len(_wire(tools).encode("utf8")) if tools else 0) + 64
            + sum(len(_wire(m).encode("utf8")) + 24 + images(m) * 8192 for m in messages))


class TypeScriptInputFilter:
    def __init__(self, *, context_id, model, base_url, api_key, budget, config, tools, tokenizer=None, node="", invoke=None):
        self.context_id, self.model, self.base_url, self.api_key = context_id, model, base_url, api_key
        self.budget, self.config, self.tools, self.tokenizer = budget, config, tools, tokenizer
        self.node, self.invoke = node, invoke
        self.process = None
        self.last_metrics = None
        self._lock = asyncio.Lock()

    async def _send(self, value):
        if self.process is None or self.process.stdin is None:
            raise CompactionBridgeError("Compaction worker is not running")
        self.process.stdin.write((_wire(value) + "\n").encode("utf8"))
        await self.process.stdin.drain()

    async def __call__(self, call):
        from agents.run import ModelInputData
        data = call.model_data
        # Cheap UTF-8 upper bound admits short input without spawning a process,
        # loading tokenizers or making any auxiliary Provider call.
        limit = self.budget["contextWindow"] - self.budget["outputReserve"] - self.budget["safetyMargin"]
        if _upper_bound(data.input, data.instructions or "", self.tools) < int(limit * self.config.get("triggerRatio", .85)):
            return data
        async with self._lock:
            source_hash = hashlib.sha256(_wire(data.input).encode('utf8')).digest()
            try:
                async with asyncio.timeout(120):
                    if self.process is None:
                        executable = self.node or shutil.which("node")
                        if not executable:
                            raise CompactionBridgeError("Node >=24.9 is required when OScode compaction is enabled")
                        # Do not inherit .env, provider keys or service credentials.
                        child_env = {key: value for key, value in os.environ.items()
                                     if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}}
                        self.process = await asyncio.create_subprocess_exec(
                            executable, str(WORKER), stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                            env=child_env, limit=32 * 1024 * 1024)
                    await self._send({"type": "project", "request": {
                        "contextId": self.context_id, "provider": self.base_url.rstrip("/"), "model": self.model,
                        "messages": data.input, "instructions": data.instructions or "", "tools": self.tools,
                        "budget": self.budget}, "config": self.config, "tokenizer": self.tokenizer})
                    while True:
                        line = await self.process.stdout.readline()
                        if not line:
                            raise CompactionBridgeError("Compaction worker exited; original history retained")
                        reply = json.loads(line)
                        if reply.get("type") == "summarize":
                            try:
                                from app.ai_engine.model_runtime import generate_with_runtime_model
                                invoke = self.invoke or generate_with_runtime_model
                                async with asyncio.timeout(45):
                                    summary = await invoke(text=reply["text"], context=[{"role": "system", "content": reply["instruction"]}],
                                                           model=self.model, base_url=self.base_url, api_key=self.api_key,
                                                           reasoning_effort="disabled", parameters={"max_tokens": reply["maxTokens"]})
                                await self._send({"type": "summary", "id": reply["id"], "result": {
                                    "text": summary["text"], "totalTokens": summary.get("total_tokens") or summary.get("tokens_used") or 0}})
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                await self._send({"type": "summary", "id": reply["id"], "error": True})
                        elif reply.get("type") == "result":
                            if hashlib.sha256(_wire(data.input).encode('utf8')).digest() != source_hash:
                                raise CompactionBridgeError("Source history changed while summarizing")
                            result = reply["projection"]
                            self.last_metrics = {"status": result["status"], **result["metrics"]}
                            log = logger.warning if result["metrics"].get("failed") else logger.info
                            log("oscode_context_compaction %s", _wire({"status": result["status"], **result["metrics"]}))
                            return ModelInputData(input=result["messages"], instructions=data.instructions)
                        else:
                            raise CompactionBridgeError("Compaction rejected input; original history retained")
            except BaseException:
                await self.close()
                raise

    async def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def build_input_filter(*, agent, context_id: str, model: str, base_url: str, api_key: str, model_policies=None):
    from app.config import settings
    from app.llm.capabilities import provider_model_capabilities
    policy = dict((model_policies or {}).get(f"{base_url.rstrip('/')}::{model}", {}))
    caps = provider_model_capabilities(model, base_url)
    window = policy.get("context_window", caps.context_window_tokens)
    reserve = getattr(agent.model_settings, "max_tokens", None) or policy.get("output_reserve", min(4096, caps.max_output_tokens or 4096))
    margin = policy.get("safety_margin", 1024)
    if (not isinstance(window, int) or isinstance(window, bool) or window < 1
            or not isinstance(reserve, int) or isinstance(reserve, bool) or reserve < 1
            or not isinstance(margin, int) or isinstance(margin, bool) or margin < 0
            or reserve + margin >= window):
        raise CompactionBridgeError("Configure a verified model-specific context window/output/safety budget")
    if caps.max_output_tokens and reserve > caps.max_output_tokens:
        raise CompactionBridgeError("Output reserve exceeds provider output maximum")
    names = {"trigger_ratio": "triggerRatio", "target_ratio": "targetRatio", "retain_turns": "retainTurns",
             "retain_ratio": "retainRatio", "summary_max_tokens": "summaryMaxTokens", "max_summary_calls": "maxSummaryCalls",
             "threshold_chars": "thresholdChars", "head_chars": "headChars", "tail_chars": "tailChars"}
    config = {target: policy[source] for source, target in names.items() if source in policy}
    tools = [{"type": "function", "name": t.name, "description": t.description,
              "parameters": t.params_json_schema, "strict": t.strict_json_schema}
             for t in agent.tools if hasattr(t, "params_json_schema")]
    tokenizer = None
    if policy.get("tokenizer_json") or policy.get("tokenizer_config"):
        if not policy.get("tokenizer_json") or not policy.get("tokenizer_config"):
            raise CompactionBridgeError("Tokenizer JSON and config must be configured together")
        tokenizer = {"json": policy["tokenizer_json"], "config": policy["tokenizer_config"]}
    agent.model_settings = replace(agent.model_settings, max_tokens=reserve)
    return TypeScriptInputFilter(context_id=context_id, model=model, base_url=base_url, api_key=api_key,
                                 budget={"contextWindow": window, "outputReserve": reserve, "safetyMargin": margin},
                                 config=config, tools=tools, tokenizer=tokenizer,
                                 node=getattr(settings, "OSCODE_CONTEXT_COMPACTION_NODE", ""))
