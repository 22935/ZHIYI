# OScode Context Compaction

Independent TypeScript engine, adapted from DeepSeek Harness MIT mechanisms. It has no Session, Cordis, AgentOS, scheduler, DB, Provider credentials, tool execution, or HTTP server.

```powershell
cd apps/oscode-context
npm ci --ignore-scripts
npm run typecheck
npm test
npm run benchmark
```

Node >=24.9 is required. Node runs TypeScript directly; there is no generated runtime bundle. `src/index.ts` is the standalone API. Inject `Summarize` to replace the Provider independently. `src/worker.ts` is only a request-scoped JSON-lines adapter.

## Integration

OScode's Python Chat API opts into `RunConfig.call_model_input_filter`. The default shared Tool Runtime path does not opt in. The Python adapter checks a UTF-8 upper bound for cheap short-request admission, then lazily starts one child process per active Runner when needed. That process is closed in the Runner's finalizer. It is not a resident service. Credentials stay in Python; the child receives only source data, schemas, model budgets and summary results.

The TS worker emits `summarize` RPC; Python calls the existing `generate_with_runtime_model` with no tools, disabled thinking and an explicit output cap. The summary call never uses Runner or this input filter. Existing API/SSE/Provider contracts remain unchanged.

## Configuration (default OFF)

`OSCODE_CONTEXT_COMPACTION_ENABLED=false` is the default. No deployment or runtime setting is changed by PR-CTX-01.

Optional model overrides use `OSCODE_CONTEXT_COMPACTION_MODELS`, a JSON object keyed by exact `base_url::effective_model`:

```json
{
  "https://api.deepseek.com::deepseek-flash": {
    "output_reserve": 4096,
    "safety_margin": 1024,
    "trigger_ratio": 0.85,
    "target_ratio": 0.65,
    "retain_turns": 2,
    "retain_ratio": 0.2,
    "summary_max_tokens": 2048,
    "max_summary_calls": 16
  }
}
```

A known Provider model's declared context window is used. An unknown model must explicitly declare `context_window`; there is no guessed global window. `output_reserve` becomes the actual main SDK request cap. For an exact local model tokenizer, additionally configure both `tokenizer_json` and `tokenizer_config` asset paths for that route. No asset is downloaded implicitly. `OSCODE_CONTEXT_COMPACTION_NODE` optionally names the Node executable.

Content is tokenized with a matching configured tokenizer, or OpenAI `js-tiktoken` for supported OpenAI models. Otherwise UTF-8 bytes form a conservative text allowance. Framing/tools and multimodal image placeholders remain estimated; `wireTokenCountExact=false` is always explicit. This implementation does NOT claim exact Provider wire counts. Image placeholders are conservative configured assumptions, not a visual-token endpoint; production multimodal calibration is still needed.

## Safety and current limits

- Original chat history is never overwritten or deleted. Only model input is projected.
- System/developer instructions, current user input, recent dialogue, active tool groups and multimodal references remain protected. Complete tool results can undergo marked deterministic head/tail pruning; errors and structured references are preserved.
- Orphan/duplicate tool IDs are rejected. Compaction cuts move to balanced complete-turn boundaries. No unfinished tool group is summarized.
- Structured summaries are lower-priority `user` background data, never new system instructions. Prompt injection inside historical data must not be executed.
- Protected old multimodal/opaque messages form hard range boundaries; a protected span that alone exceeds the budget fails explicitly instead of being cut.
- Summary schema, length, shrink target and source revision are validated before projection. Within the hard input limit, summary failure returns the entire original input with an explicit failure status/log. Over-limit failure blocks the request, retaining history.
- Hysteresis and an eight-entry request-local memo avoid repeated same-prefix summary calls inside a tool loop. No cross-request cache or DB migration is introduced. Consecutive HTTP requests may therefore pay for the same old prefix again.
- DSH's Session journal, durable shadow events, distributed locks, route-usage calibration, automatic overflow retry, UI compact command, and tool-schema prefix-cache replay are not migrated. This is an algorithm adaptation/function extraction, not a verbatim package migration.

Upstream commit, source/test/dependency SHA256 and full MIT license: `third_party/dsh/`.
