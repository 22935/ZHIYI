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

## Manual `/compact`

In OScode, type `/compact` and send, or type `/` and choose the command suggestion. The command is handled locally rather than becoming a user message or starting a tool run. The UI displays progress, estimated before/after Token counts, or a no-op/failure explanation.

`POST /ai/chat/compact` uses the current conversation and model settings. It invokes the same TS engine with `force=true`. Completed turns, including the latest completed turn, may be summarized; a current request, unfinished tool group, system/developer messages and multimodal boundaries stay protected. Automatic compaction retains its configured recent-turn policy. Original stored and displayed chat records are retained.

Manual summary budgets are relative to replaceable history after fixed/protected input and checkpoint overhead are accounted for. If useful savings cannot fit a minimal summary, `unchanged` with `INSUFFICIENT_SAVINGS` is returned without calling the Provider. `no_safe_range` with `NO_COMPLETED_HISTORY` means no completed span can safely be replaced. Schema, budget and Provider failures have separate `failureCode` values and retain the original history. An oversized structured summary gets at most one measured rewrite, within the existing total summary-call budget; JSON is never truncated. UTF-8 allowance units are explicitly distinguished from the Provider's output-token cap.

Validated projections are held in the current page's Chat store and supplied as `context` on later streaming/text requests, with new complete messages appended. They are scoped to the conversation and model settings; source-prefix edits invalidate them. Switching conversations discards late results. Refreshing the page restores full raw context; there is no durable checkpoint database or cross-device sync.

The UI distinguishes the previous execution's Provider usage (which includes its temporary tool loop) from the next request's text-history estimate. The latter counts the actual checkpoint plus subsequent messages using the host's conservative UTF-8 allowance and fixed instruction/tool-schema allowance. New user input will be added to that estimate. Model/role changes invalidate the estimate; older history without allowance metadata is labelled as previous-call usage. Fixed allowance metadata travels in existing usage events and is retained by the Node backend for history reloads.

`OSCODE_CONTEXT_COMPACTION_MANUAL_ENABLED=true` enables this explicit endpoint independently of the automatic flag. Set it to `false` to disable manual requests. Model budgets, tokenizer assets and Node requirements below also apply to manual compaction. Restart the Python AI service after adding this route/configuration; Java uses its existing authenticated generic proxy.

## Automatic configuration (default OFF)

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
- Hysteresis and an eight-entry request-local memo avoid repeated same-prefix summary calls inside a tool loop. Automatic projections have no cross-request cache; explicit manual checkpoints can be reused by the same page. No DB migration is introduced.
- DSH's Session journal, durable shadow events, distributed locks, route-usage calibration, automatic overflow retry, and tool-schema prefix-cache replay are not migrated. The OScode command is a host integration; this remains an algorithm adaptation/function extraction, not a verbatim package migration.

Upstream commit, source/test/dependency SHA256 and full MIT license: `third_party/dsh/`.
