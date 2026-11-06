# N01A Windows Native development harness

> **已退役（2026-11-05）**：python Local Runtime 执行器删除后，本 harness 的 `up`
> 动作（原 spawn `runtime.main` host）一并移除，本文流程不再是可用入口。当前唯一
> 本地运行形态是持久化原生栈：`persistent.ps1` / `start-local-desktop.ps1`
> （见 README-N03.md），执行后端恒为 zhiyi-hands（DSH 基座）。`smoke`/`down`/
> `status` 动作仍随持久化栈可用。以下原文仅作历史参考。

Requires Windows 11 x64 and CPython 3.14. Uses the existing
`app.main`, composition root, HTTP transport and grant authority. No Docker
commands or production database migrations are performed by these scripts.

Create a **new** virtual environment outside this repository, then install:

```powershell
python -m venv "$env:TEMP\kinlin-native-venv"
$py = "$env:TEMP\kinlin-native-venv\Scripts\python.exe"
& $py -m pip install --require-hashes --only-binary=:all: -r apps/agent/requirements.lock -r apps/agent/requirements.native-tools.lock
& $py -m pip check
```

Use an absolute, nonexistent directory outside the repository for each run:

```powershell
$run = "$env:TEMP\kinlin-native-$([guid]::NewGuid().ToString('N'))"
$entry = '.\ops\scripts\infra\windows\native\native.ps1'
& $entry preflight -RunDir $run -Python $py
& $entry fixtures -RunDir $run -Python $py
# fixtures returns 2 if Windows cannot create a symlink. Keep that BLOCKED;
# the remaining real checks can still run without claiming full acceptance.
& $entry up -RunDir $run -Python $py -AiPort 18761 -HostPort 18765
& $entry status -RunDir $run -Python $py
& $entry smoke -RunDir $run -Python $py
& $py ops/scripts/infra/windows/native/verify_lifecycle.py $run
& $py ops/scripts/infra/windows/native/audit_secrets.py $run
& $entry down -RunDir $run -Python $py
```

`preflight` reads versions, dependency metadata, paths and port availability; it
does not create a run directory or start a service. `fixtures` is a separate
preparation stage that starts no service and imports no production application.
It first inspects an existing `workspace/symlink`, checks the real Windows
IO_REPARSE_TAG_SYMLINK (not a junction), and requires its target to be this run's
`outside` directory or `outside/sentinel.txt`. It preserves an existing sentinel.
Only if the symlink is absent does it attempt ordinary-user creation. WinError
1314 produces BLOCKED with no elevation, ACL change or Developer Mode change.
Junctions and the external temporary sentinel are also prepared at this stage.

An environment owner may independently prepare this exact new temporary layout
before `fixtures` is invoked. No existing link is copied or moved from an
unrelated workspace. The preparation receipt records timestamps and the preparer
token. `up` accepts only a nonexistent directory or a validated fixture-only
layout with that receipt, no runtime/data files, and an unchanged sentinel hash.
It never resumes or upgrades an earlier run. For compatibility, `up` on a new
directory prepares fixtures before starting either service. A new run explicitly
initializes only its three new core SQLite stores via
`prepare_agentos_runtime.py --apply --initialize-empty`, with read-only checks
before and after. Semantic/C2/Dispatch authority remains enabled. No model keys
or Redis/PostgreSQL connection configuration is inherited. No shell capability
is granted. The blank run-local `.env` prevents repository configuration from
overriding these isolated settings. Internal auth is configured with a random
token; only public health paths are used by the controller.

State records PID, process creation time, executable and full command without
credentials. Secrets are stored with Windows current-user DPAPI, inherited only
by owned children, and removed on successful stop/rollback. Do not publish run
databases or encrypted credentials. Logs and receipts stay in the run directory.
The launcher does not put credentials into the calling PowerShell environment.

`status` checks process identity, its actual loopback listening socket, and JSON
health. Dependency `DEGRADED` is reported separately. `packsRegistered` is
recorded without treating the HTTP status alone as acceptance. Preflight rejects
elevated/high-integrity launchers; actual Python service tokens are queried and
recorded to confirm ordinary-user execution.

`smoke` imports the **real `app.main` assembly** in another Windows Python process
with separately prepared fresh stores. It uses that Runtime's `LocalRuntimeClient`
and `HttpLocalRuntimeTransport` to reach the already running Host. It does not
claim the FastAPI business API provides an arbitrary file-write endpoint. Raw
signed requests are used only for malformed/adversarial protocol cases. All
file mutations are restricted to the run's workspace and containment sentinels.
Each invocation creates new smoke stores, an individually named log/receipt and
an owned worker process; the same run may be smoked again. The execution stage
never creates/repairs links or resets the sentinel. It consumes the independently
prepared fixture, checks preparation preceded Runtime startup, and exercises
read/write/patch plus directory list/new-file writes where applicable. Every
denial must be PATH_OUTSIDE_WORKSPACE and leave sentinel bytes/hash/mtime and
outside directory entries unchanged. `../` and junction cases remain separate.
Positive list operations use `files/`, since listing a root containing an escape
link is correctly rejected by the existing Host policy.

The receipt has a top-level status and explicit statuses for N01A-01 through 08:
PASS returns 0, BLOCKED returns 2, FAIL returns 1. Worker failure, missing/malformed
or stale receipts, missing checks and unknown check statuses are FAIL. FAIL takes
precedence over BLOCKED. A missing legal symlink fixture remains BLOCKED; neither
a junction nor a successful aggregation unit check proves symlink acceptance.
The smoke summary covers its eight checks, not the separate N01A-09 through 12
lifecycle/data/regression/secret requirements. Full PR acceptance still needs all
twelve. Each fresh worker record is retained for identity-checked cleanup.

`down` sends Ctrl+C through the owned process's dedicated hidden console so the
normal application shutdown paths run. It refuses a PID with changed identity,
retains state on shutdown failure, and never kills processes by name. Successful
stop checks ports, directory rename handles and the OS workflow lock. Data and
evidence remain. A second `down` is safe; a stopped `status` returns nonzero.

The maintenance-only `refresh_tool_lock.py` preserves exact tool pins and
original Linux hashes and adds published Windows/universal wheel hashes. The
Windows-only transitive requirements `colorama==0.4.6` and `pywin32==312` are
explicitly pinned. Network failures retain the previous lock; pip still verifies
artifact bytes with TLS and `--require-hashes`. Do not use the Windows tool lock
for the Linux image, which continues using its existing lock unchanged.
