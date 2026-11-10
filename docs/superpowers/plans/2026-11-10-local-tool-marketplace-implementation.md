# 本地工具资源商店 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供平台维护的 PDF 解析器和文件格式转换器本地工具包，并为资源器补齐单机可验证的结构化审计事件。

**Architecture:** 工具实现放入 `components/marketplace/builtins`，通过受控 loopback HTTP 服务暴露固定 `/health` 和 `/execute` 合同。平台 catalog 仅引用由构建脚本生成、带 SHA-256 的 ZIP 包；`MarketplaceService` 仍只负责任务、启动、健康和 Runtime 登记。`components/resource` 新增审计事件 port/store，由 Resource Plane 写入资源生命周期事实。

**Tech Stack:** Python 3.11、Pydantic、PyPDF2、python-docx、openpyxl、stdlib CSV/JSON/HTML、FastAPI/HTTPX、SQLite、pytest、Vue 3、Vitest。

---

## 文件结构

- `apps/agentOS/src/components/resource/ports/audit_store.py`：资源审计事件存储接口。
- `apps/agentOS/src/components/resource/infrastructure/audit_store.py`：内存与 SQLite 审计实现。
- `apps/agentOS/src/components/resource/application/resource_plane.py`：登记、轮换和观测异常时写入结构化事件。
- `apps/agentOS/src/components/marketplace/builtins/contracts.py`：PDF/转换工具的固定输入输出合同。
- `apps/agentOS/src/components/marketplace/builtins/pdf_parser.py`：受限 PDF 文本提取。
- `apps/agentOS/src/components/marketplace/builtins/file_converter.py`：白名单转换与输出路径隔离。
- `apps/agentOS/src/components/marketplace/builtins/server.py`：仅支持 `/health`、`/execute` 的本地工具服务入口。
- `apps/agentOS/src/components/marketplace/builtins/catalog.py`：生成两个平台 catalog 清单和 ZIP 包的构建器。
- `apps/agentOS/tests/components/resource/test_audit_store.py`：审计行为测试。
- `apps/agentOS/tests/components/marketplace/test_builtin_tools.py`：PDF/转换安全与结果测试。
- `apps/agentOS/tests/components/marketplace/test_builtin_catalog.py`：制品和 catalog 校验测试。
- `apps/frontend/src/components/resource-center/MarketplaceCatalogPanel.vue`：展示本地工具格式能力与运行需求。
- `apps/frontend/src/components/resource-center/MarketplaceCatalogPanel.spec.ts`：目录项呈现测试。
- `apps/agentOS/src/components/resource/README.md`：审计事件和本地工具 Runtime 边界。

### Task 1: 资源生命周期结构化审计

**Files:** Create `apps/agentOS/src/components/resource/ports/audit_store.py`, `apps/agentOS/src/components/resource/infrastructure/audit_store.py`, `apps/agentOS/tests/components/resource/test_audit_store.py`; Modify `apps/agentOS/src/components/resource/application/resource_plane.py`, `apps/agentOS/src/components/resource/ports/__init__.py`, `apps/agentOS/src/components/resource/infrastructure/__init__.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_resource_plane_records_registration_and_rotation_audit_events():
    plane = ResourcePlane(audit_store=InMemoryResourceAuditStore())
    plane.register_remote_runtime(profile(), snapshot())
    plane.rotate_runtime_credential("runtime:test")
    assert [(event.kind, event.resource_id) for event in plane.audit_events()] == [
        ("runtime_registered", "runtime:test"),
        ("credential_rotated", "runtime:test"),
    ]
```

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/components/resource/test_audit_store.py::test_resource_plane_records_registration_and_rotation_audit_events`

Expected: FAIL because `InMemoryResourceAuditStore` and `audit_events` do not exist.

- [ ] **Step 3: 实现最小合同和存储**

```python
@dataclass(frozen=True)
class ResourceAuditEvent:
    kind: str
    resource_id: str
    occurred_at: datetime
    metadata: Mapping[str, str]

class ResourceAuditStore(Protocol):
    def append(self, event: ResourceAuditEvent) -> None: ...
    def list(self, resource_id: str | None = None, *, limit: int = 100) -> list[ResourceAuditEvent]: ...
```

`ResourcePlane` accepts an optional audit store, emits `runtime_registered`, `node_registered`, `credential_rotated`, `observation_rejected` and `snapshot_conflict`, and never stores credentials, request bodies, model prompts or responses in metadata.

- [ ] **Step 4: 验证 GREEN**

Run: `pytest -q tests/components/resource/test_audit_store.py tests/components/resource/test_store_contract.py`

Expected: PASS.

- [ ] **Step 5: 提交**

```text
feat(resource): audit lifecycle events
```

### Task 2: 安全的内置工具合同

**Files:** Create `apps/agentOS/src/components/marketplace/builtins/__init__.py`, `contracts.py`, `apps/agentOS/tests/components/marketplace/test_builtin_tools.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_convert_request_rejects_path_escape_and_unknown_format(tmp_path):
    with pytest.raises(ValidationError):
        ConvertRequest(sourcePath="../secret.txt", targetFormat="exe")
```

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/components/marketplace/test_builtin_tools.py::test_convert_request_rejects_path_escape_and_unknown_format`

Expected: FAIL because the built-in tool contract module is absent.

- [ ] **Step 3: 实现最小合同**

```python
class ConvertRequest(BaseModel):
    source_path: SafeRelativePath = Field(alias="sourcePath")
    target_format: Literal["txt", "md", "html", "csv", "json", "docx", "xlsx", "pdf"] = Field(alias="targetFormat")

class PdfParseRequest(BaseModel):
    source_path: SafeRelativePath = Field(alias="sourcePath")
    first_page: int = Field(default=1, alias="firstPage", ge=1)
    last_page: int | None = Field(default=None, alias="lastPage", ge=1)
```

The common `SafeRelativePath` rejects absolute paths, `..`, backslashes and empty values. Contracts cap page ranges and never accept executable paths, command strings, URLs or output paths supplied by callers.

- [ ] **Step 4: 验证 GREEN**

Run: `pytest -q tests/components/marketplace/test_builtin_tools.py::test_convert_request_rejects_path_escape_and_unknown_format`

Expected: PASS.

- [ ] **Step 5: 提交**

```text
feat(marketplace): define secure local tool contracts
```

### Task 3: PDF 解析器与格式转换器

**Files:** Create `apps/agentOS/src/components/marketplace/builtins/pdf_parser.py`, `file_converter.py`; Modify `apps/agentOS/tests/components/marketplace/test_builtin_tools.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_pdf_parser_returns_text_and_page_metadata(tmp_path):
    source = write_text_pdf(tmp_path / "input.pdf", "agentos")
    result = PdfParser(workspace=tmp_path).parse(PdfParseRequest(sourcePath=source.name))
    assert result.pages == 1
    assert result.text == "agentos"

def test_converter_writes_only_to_task_output_directory(tmp_path):
    (tmp_path / "input.md").write_text("# Title", encoding="utf-8")
    result = FileConverter(workspace=tmp_path, output_root=tmp_path / "out").convert(
        ConvertRequest(sourcePath="input.md", targetFormat="html")
    )
    assert result.output_path == "out/input.html"
    assert (tmp_path / result.output_path).is_file()
    assert (tmp_path / "input.md").read_text(encoding="utf-8") == "# Title"
```

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/components/marketplace/test_builtin_tools.py -k "pdf_parser_returns or converter_writes"`

Expected: FAIL because parser and converter implementations are absent.

- [ ] **Step 3: 实现最小工具逻辑**

`PdfParser` validates the `%PDF-` signature, opens with `PyPDF2.PdfReader(strict=True)`, caps pages and returned text, and raises `ToolExecutionError("OCR_NOT_AVAILABLE")` for textless pages. `FileConverter` resolves the source under `workspace`, creates a UUID task directory under `output_root`, and implements only declared pairs:

```text
txt <-> md <-> html
csv <-> json
docx -> txt | md | html
xlsx -> csv | json
pdf -> txt | md
```

Unsupported pairs raise `ToolExecutionError("FORMAT_NOT_SUPPORTED")`. HTML conversion escapes text; CSV parsing uses `csv`; JSON is parsed and re-serialized; no shell, Pandoc, LibreOffice, macro, formula execution or network access is used in this initial runtime. Those engines are future platform bundle variants, not fallback commands.

- [ ] **Step 4: 验证 GREEN**

Run: `pytest -q tests/components/marketplace/test_builtin_tools.py`

Expected: PASS.

- [ ] **Step 5: 提交**

```text
feat(marketplace): add local PDF and conversion tools
```

### Task 4: 受控 HTTP 工具服务与可安装目录制品

**Files:** Create `apps/agentOS/src/components/marketplace/builtins/server.py`, `catalog.py`, `apps/agentOS/tests/components/marketplace/test_builtin_catalog.py`; Modify `apps/agentOS/src/components/marketplace/infrastructure.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_builtin_catalog_builds_hashed_zip_packages_for_two_tools(tmp_path):
    items = build_builtin_catalog(tmp_path)
    assert {item.catalog_id for item in items} == {"tool.pdf-parser", "tool.file-converter"}
    for item in items:
        assert validate_package(tmp_path / "packages", item).is_file()
        assert item.runtime["kind"] == "tool_service"
        assert item.runtime["adapter"] == "agentos_http"
```

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/components/marketplace/test_builtin_catalog.py::test_builtin_catalog_builds_hashed_zip_packages_for_two_tools`

Expected: FAIL because `build_builtin_catalog` is absent.

- [ ] **Step 3: 实现服务和制品构建**

`server.py` handles exactly `GET /health` and signed `POST /execute`; `/execute` only dispatches `pdf.parse` and `file.convert` into an installation-owned workspace. `catalog.py` builds deterministic ZIP files that contain the Python service launcher and built-in code, writes catalog JSON into `catalog/`, uses a platform-owned launch script selected by `LocalPackageLauncher`, and emits Runtime declarations with loopback endpoints, `tool.invoke`, provider `AgentOS Local Tools`, source type `platform-local`, adapter `agentos_http`.

Extend `LocalPackageLauncher` with an explicit catalog-only `startup.pythonModule` option: it invokes the configured Python executable with `-m <allowlisted bundled module>` using `shell=False`; it rejects this field for user-supplied custom resources. This avoids a `.bat` shell bridge while retaining a controlled executable.

- [ ] **Step 4: 验证 GREEN**

Run: `pytest -q tests/components/marketplace/test_builtin_catalog.py tests/components/marketplace/test_service.py`

Expected: PASS.

- [ ] **Step 5: 提交**

```text
feat(marketplace): package managed local tools
```

### Task 5: 装配、API 投影和商店目录体验

**Files:** Modify `apps/agent/app/execution/wiring.py`, `apps/agent/app/api/agentos_v2.py`, `apps/frontend/src/components/resource-center/MarketplaceCatalogPanel.vue`; Create `apps/frontend/src/components/resource-center/MarketplaceCatalogPanel.spec.ts`; Modify `apps/frontend/src/services/api/agentos/types/marketplace.ts`.

- [ ] **Step 1: 写入失败测试**

```ts
it('shows platform tool capabilities without exposing startup commands', () => {
  const wrapper = mount(MarketplaceCatalogPanel, { props: { items: [toolItem], installations: [], loading: false, busy: false } })
  expect(wrapper.text()).toContain('PDF 解析')
  expect(wrapper.text()).toContain('pdf.parse')
  expect(wrapper.text()).not.toContain('entrypoint')
  expect(wrapper.text()).not.toContain('arguments')
})
```

- [ ] **Step 2: 验证 RED**

Run: `npx vitest run src/components/resource-center/MarketplaceCatalogPanel.spec.ts --reporter=dot`

Expected: FAIL because the item capabilities are not projected/rendered.

- [ ] **Step 3: 实现最小接入**

At wiring, call `ensure_builtin_catalog(catalog_root, package_root)` before `DirectoryCatalog` is created, making the two platform manifests available on a fresh local install. API catalog projection returns public fields only: ID, kind, version, display name, description, size, requirements, category and declared capabilities. Extend the frontend catalog type and render capability chips; keep package path, checksum, runtime endpoint and startup data absent from the API/UI.

- [ ] **Step 4: 验证 GREEN**

Run: `npx vitest run src/components/resource-center/MarketplaceCatalogPanel.spec.ts src/services/api/agentos/api/marketplace.spec.ts --reporter=dot`

Expected: PASS.

- [ ] **Step 5: 提交**

```text
feat(frontend): surface managed local tools
```

### Task 6: 文档、TODO 清理与最终验证

**Files:** Modify `apps/agentOS/src/components/resource/README.md`, `apps/agentOS/src/adapters/resource_model_execution.py`, `docs/superpowers/specs/2026-11-10-local-tool-marketplace-design.md`.

- [ ] **Step 1: 写入失败测试**

```python
def test_model_observation_failure_is_audited():
    observer = FailingObserver()
    adapter = ResourceModelProviderAdapter(..., execution_observer=observer, audit_store=store)
    adapter._observe(success=True, latency_ms=1.0)
    assert store.list()[0].kind == "execution_observation_write_failed"
```

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/adapters/test_resource_model_execution.py -k observation_failure_is_audited`

Expected: FAIL because the adapter does not emit an audit event on observer failure.

- [ ] **Step 3: 实现与更新文档**

Inject a narrow audit reporter into `ResourceModelProviderAdapter`, emit `execution_observation_write_failed` with runtime ID and error class only, remove the completed observability TODOs, and update README with the PDF/format tool capability contract. Keep all distributed/KMS/policy TODOs intact and state their prerequisites.

- [ ] **Step 4: 验证 GREEN**

Run:

```text
pytest -q tests/components/marketplace tests/components/resource tests/adapters/test_resource_model_execution.py
npx vitest run src/components/resource-center/MarketplaceCatalogPanel.spec.ts src/services/api/agentos/api/marketplace.spec.ts src/views/ResourceMarketplaceView.spec.ts --reporter=dot
npm run build:web
git diff --check
```

Expected: all tests and build pass; no whitespace errors.

- [ ] **Step 5: 提交**

```text
docs(resource): document managed local tools and audit events
```

## 自检

- Task 1 and 6 remove only observability TODOs backed by testable behavior.
- Tasks 2 and 3 enforce format/path/output isolation without arbitrary process execution.
- Task 4 preserves marketplace package validation and launch boundaries.
- Task 5 exposes two platform tools without leaking implementation or credential data.
