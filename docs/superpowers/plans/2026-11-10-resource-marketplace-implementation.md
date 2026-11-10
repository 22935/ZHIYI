# 资源商店与资源管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立受控本地资源目录、安装任务和资源概览、资源管理、资源商店页面，使通过健康检查的本地安装服务自动成为可调度资源。

**Architecture:** `components/marketplace` 是安装控制面，维护目录、任务和启动流程；`components/resource` 只保存已启动 Runtime 的资源事实、健康和调度。FastAPI 暴露商店操作，Vue 分别呈现概览、端边云管理和商店。

**Tech Stack:** Python 3.11、Pydantic、FastAPI、SQLite、pytest、Vue 3、TypeScript、Vitest、Element Plus。

---

## 文件结构

- `apps/agentOS/src/components/marketplace/contracts.py`：Catalog、Job 和自定义资源合同。
- `apps/agentOS/src/components/marketplace/ports.py`：目录、任务仓储和本地启动器端口。
- `apps/agentOS/src/components/marketplace/infrastructure.py`：内存仓储与受控包路径校验。
- `apps/agentOS/src/components/marketplace/application/service.py`：安装、停止和卸载状态机。
- `apps/agent/app/execution/wiring.py`、`apps/agent/app/api/agentos_v2.py`：组合与 HTTP API。
- `apps/frontend/src/services/api/agentos/types/marketplace.ts`、`api/marketplace.ts`：前端 API。
- `apps/frontend/src/views/ResourceOverviewView.vue`、`ResourceManagementView.vue`、`ResourceMarketplaceView.vue`：用户界面。

### Task 1: 建立商店合同和状态转换

**Files:** Create `apps/agentOS/src/components/marketplace/contracts.py`, `apps/agentOS/src/components/marketplace/__init__.py`; Test `apps/agentOS/tests/components/marketplace/test_contracts.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_catalog_item_rejects_package_escape_and_invalid_checksum():
    with pytest.raises(ValidationError):
        CatalogItem(catalogId="model.demo", kind="model_server", version="1.0.0", packagePath="../escape", sha256="bad", runtime={})

def test_job_only_advances_through_installation_lifecycle():
    job = InstallationJob.new("job-1", "model.demo", "tenant-a")
    assert job.advance(InstallationStatus.INSTALLING).status is InstallationStatus.INSTALLING
    assert job.advance(InstallationStatus.REGISTERING).status is InstallationStatus.REGISTERING
    with pytest.raises(ValueError):
        job.advance(InstallationStatus.QUEUED)
```

- [ ] **Step 2: 验证 RED**

Run `pytest -q tests/components/marketplace/test_contracts.py`. Expected: FAIL，因为模块尚不存在。

- [ ] **Step 3: 实现最小合同**

```python
class InstallationStatus(str, Enum):
    QUEUED = "queued"; INSTALLING = "installing"; REGISTERING = "registering"
    RUNNING = "running"; FAILED = "failed"; STOPPED = "stopped"
    UNINSTALLING = "uninstalling"; REMOVED = "removed"

_ALLOWED = {
    InstallationStatus.QUEUED: {InstallationStatus.INSTALLING, InstallationStatus.FAILED},
    InstallationStatus.INSTALLING: {InstallationStatus.REGISTERING, InstallationStatus.FAILED},
    InstallationStatus.REGISTERING: {InstallationStatus.RUNNING, InstallationStatus.FAILED},
    InstallationStatus.RUNNING: {InstallationStatus.STOPPED, InstallationStatus.UNINSTALLING},
    InstallationStatus.STOPPED: {InstallationStatus.UNINSTALLING},
    InstallationStatus.UNINSTALLING: {InstallationStatus.REMOVED, InstallationStatus.FAILED},
}
```

`CatalogItem.packagePath` 必须为无 `..` 的相对 POSIX 路径；`sha256` 必须为 64 位十六进制。Job 仅保存 ID、tenant、状态、Runtime ID、时间和无敏感错误摘要。

- [ ] **Step 4: 验证 GREEN 并提交**

Run `pytest -q tests/components/marketplace/test_contracts.py`. Expected: PASS。

Commit: `feat(marketplace): define catalog and installation contracts`，仅包含 marketplace 合同和测试。

### Task 2: 实现受控安装、登记、健康门槛和回滚

**Files:** Create `apps/agentOS/src/components/marketplace/ports.py`, `infrastructure.py`, `application/__init__.py`, `application/service.py`; Test `apps/agentOS/tests/components/marketplace/test_service.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_install_registers_healthy_local_model_runtime(tmp_path):
    plane = ResourcePlane()
    service = MarketplaceService(catalog=InMemoryCatalog([catalog_item()]), jobs=InMemoryInstallationJobs(), package_root=tmp_path, launcher=FakeLauncher(healthy=True), plane=plane)
    (tmp_path / "models").mkdir(); (tmp_path / "models" / "demo.bundle").write_bytes(b"bundle")
    job = service.install(catalog_id="model.demo", owner_scope="tenant-a")
    assert job.status is InstallationStatus.RUNNING
    assert plane.runtime(job.runtime_id).kind is RuntimeKind.MODEL_SERVER

def test_bad_checksum_fails_without_a_schedulable_runtime(tmp_path):
    job = service_with_bad_checksum(tmp_path).install(catalog_id="model.demo", owner_scope="tenant-a")
    assert job.status is InstallationStatus.FAILED
    with pytest.raises(KeyError): plane.runtime("runtime:market:demo")
```

- [ ] **Step 2: 验证 RED**

Run `pytest -q tests/components/marketplace/test_service.py`. Expected: FAIL，因为 `MarketplaceService` 不存在。

- [ ] **Step 3: 实现端口和服务**

```python
class LocalLauncher(Protocol):
    def start(self, item: CatalogItem, *, owner_scope: str) -> RuntimeProfile: ...
    def stop(self, runtime_id: str) -> None: ...
    def healthy(self, runtime_id: str) -> bool: ...

def _package_file(self, item: CatalogItem) -> Path:
    candidate = (self.package_root / item.package_path).resolve()
    if self.package_root not in candidate.parents:
        raise ValueError("catalog package escapes platform root")
    return candidate
```

`MarketplaceService.install()` 必须持久化 `queued -> installing -> registering -> running`。先验证文件、SHA-256、硬件和 Runtime 声明，再调用受控 launcher、`ResourcePlane.ensure_node()`、`register_runtime()` 和健康检查。任一步失败必须 stop 已启动服务、撤销 Runtime，并写入 `failed`；不接受 URL 或命令字符串。

- [ ] **Step 4: 验证 GREEN 并提交**

Run `pytest -q tests/components/marketplace/test_service.py tests/components/resource/test_local_runtime.py`. Expected: PASS。

Commit: `feat(marketplace): install controlled local resources`，仅包含 marketplace 服务与测试。

### Task 3: 增加停止、卸载和自定义本地服务

**Files:** Modify `apps/agentOS/src/components/marketplace/contracts.py`, `application/service.py`; Test `apps/agentOS/tests/components/marketplace/test_service.py`.

- [ ] **Step 1: 写入失败测试**

```python
def test_custom_local_service_has_no_shell_command_field():
    with pytest.raises(ValidationError):
        CustomResourceRequest(displayName="Local", kind="model_server", endpoint={"protocol": "http", "address": "http://127.0.0.1:11434"}, capabilities=["model.generate"], command="bad")

def test_uninstall_stops_runtime_before_removing_catalog_registration():
    job = running_job(service)
    removed = service.uninstall(job.job_id)
    assert removed.status is InstallationStatus.REMOVED
    assert launcher.stopped == [job.runtime_id]
    with pytest.raises(KeyError): plane.runtime(job.runtime_id)
```

- [ ] **Step 2: 验证 RED**

Run `pytest -q tests/components/marketplace/test_service.py -k "custom or uninstall"`. Expected: FAIL。

- [ ] **Step 3: 实现严格边界**

```python
class CustomResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    display_name: str = Field(alias="displayName", min_length=1, max_length=120)
    kind: RuntimeKind
    endpoint: ResourceEndpoint
    capabilities: list[str] = Field(min_length=1)
    model_ids: list[str] = Field(default_factory=list, alias="modelIds")
```

自定义服务仅允许 `127.0.0.1`、`localhost` 和 IPv6 回环地址，并用 `sourceType="custom-local"` 登记。卸载必须 `uninstalling -> removed`：先 stop、再删除模型端点和 Runtime；失败保留 Job 为 `failed`。

- [ ] **Step 4: 验证 GREEN 并提交**

Run `pytest -q tests/components/marketplace/test_service.py`. Expected: PASS。

Commit: `feat(marketplace): manage local service lifecycle`，仅包含生命周期实现和测试。

### Task 4: 接入运行时和 FastAPI

**Files:** Modify `apps/agent/app/execution/wiring.py`, `apps/agent/app/api/agentos_v2.py`; Test `apps/agent/tests/test_agentos_v2_api.py`.

- [ ] **Step 1: 写入失败 API 测试**

```python
async def test_marketplace_install_returns_job_and_resource_projection(tmp_path):
    runtime = _runtime(tmp_path); app = FastAPI(); app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    token = _operator_context()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/agentos/v2/marketplace/catalog")).status_code == 200
            installed = await client.post("/agentos/v2/marketplace/installations", json={"catalogId": "model.demo"})
    finally:
        _trusted_user_context.reset(token)
    assert installed.status_code == 201
    assert installed.json()["status"] == "running"
```

- [ ] **Step 2: 验证 RED**

Run `pytest -q tests/test_agentos_v2_api.py -k marketplace`. Expected: FAIL with 404。

- [ ] **Step 3: 实现组合和路由**

```python
@router.get("/marketplace/catalog")
async def list_marketplace_catalog():
    return {"items": [item.model_dump(by_alias=True, mode="json") for item in marketplace.list_catalog()]}

@router.post("/marketplace/installations", status_code=status.HTTP_201_CREATED)
async def install_marketplace_item(request: MarketplaceInstallRequest):
    actor = current_trusted_user()
    require_resource_operator(str(actor.tenant_id or ""))
    return marketplace.install(request.catalog_id, owner_scope=str(actor.tenant_id or "")).model_dump(by_alias=True, mode="json")
```

提供 `GET /marketplace/catalog`、`GET /marketplace/installations`、`POST /marketplace/installations`、`POST /marketplace/custom-resources`、`POST /marketplace/installations/{job_id}/stop`、`DELETE /marketplace/installations/{job_id}`。所有命令复用现有可信用户和 tenant 检查，响应不得包含启动命令、包内容或凭据。

- [ ] **Step 4: 验证 GREEN 并提交**

Run `pytest -q tests/test_agentos_v2_api.py -k "marketplace or resource" tests/components/marketplace tests/components/resource`. Expected: PASS。

Commit: `feat(api): expose local resource marketplace`，仅包含 wiring、路由和 API 测试。

### Task 5: 前端 API、资源页面拆分和资源商店

**Files:** Create `apps/frontend/src/services/api/agentos/types/marketplace.ts`, `api/marketplace.ts`, `views/ResourceOverviewView.vue`, `ResourceManagementView.vue`, `ResourceMarketplaceView.vue`, `components/resource-center/MarketplaceCatalogPanel.vue`, `MarketplaceInstalledPanel.vue`, `CustomResourceDialog.vue`; Modify `types/index.ts`, `index.ts`, `router/index.ts`, `views/ResourceCenterView.vue`; Test `marketplace.spec.ts`, `ResourceManagementView.spec.ts`, `ResourceMarketplaceView.spec.ts`.

- [ ] **Step 1: 写入失败 API 和页面测试**

```ts
it('posts an installation instead of registering a browser-side resource', async () => {
  await createMarketplaceApi().install({ catalogId: 'model.demo' })
  expect(agentosRequest.post).toHaveBeenCalledWith('/marketplace/installations', { catalogId: 'model.demo' })
})

it('opens management and marketplace from overview', async () => {
  const wrapper = mount(ResourceOverviewView, { global: { plugins: [router, createPinia()] } })
  await wrapper.get('[data-testid="open-resource-management"]').trigger('click')
  expect(router.currentRoute.value.path).toBe('/agentos/resources/manage')
  await wrapper.get('[data-testid="open-resource-marketplace"]').trigger('click')
  expect(router.currentRoute.value.path).toBe('/agentos/resources/store')
})

it('shows Device Edge Cloud lanes and no command field', async () => {
  expect(mount(ResourceManagementView, { global: { stubs } }).text()).toContain('边缘节点')
  expect(mount(CustomResourceDialog, { global: { stubs } }).find('[name="command"]').exists()).toBe(false)
})
```

- [ ] **Step 2: 验证 RED**

Run `npx vitest run src/services/api/agentos/api/marketplace.spec.ts src/views/ResourceManagementView.spec.ts src/views/ResourceMarketplaceView.spec.ts --reporter=dot`. Expected: FAIL，因为 API 和新页面不存在。

- [ ] **Step 3: 实现 API、路由和界面**

```ts
export type InstallationStatus = 'queued' | 'installing' | 'registering' | 'running' | 'failed' | 'stopped' | 'uninstalling' | 'removed'
export interface MarketplaceInstallation { jobId: string; catalogId?: string | null; status: InstallationStatus; runtimeId?: string | null; errorSummary?: string | null }
export const createMarketplaceApi = () => ({
  async listCatalog() { return (await agentosRequest.get('/marketplace/catalog')).data },
  async install(payload: { catalogId: string }) { return (await agentosRequest.post('/marketplace/installations', payload)).data },
})
```

`/agentos/resources` 重定向到 `/agentos/resources/overview`。概览只展示真实资源摘要和“资源管理”“资源商店”入口；管理页复用 `ResourceTopologyPanel`、详情抽屉和 Node 启停，固定以 Device/Edge/Cloud 三层呈现；商店展示目录、已安装任务和自定义资源表单。目录项是可安装物，不作为运行资源展示。

商店仅在存在 `queued/installing/registering/uninstalling` Job 时每 3 秒轮询，并在组件卸载时清理 timer/request。自定义表单只提交显示名、资源类型、回环地址、能力、模型 ID、adapter。视觉沿用现有主题变量和 1400px 宽度：概览紧凑，管理层用细线和颜色标识，不嵌套卡片；390px 宽度变为单列且文本不溢出。

- [ ] **Step 4: 验证 GREEN 并提交**

Run `npx vitest run src/services/api/agentos/api/marketplace.spec.ts src/views/ResourceCenterView.spec.ts src/views/ResourceManagementView.spec.ts src/views/ResourceMarketplaceView.spec.ts src/components/resource-center/ResourcePlaneAdaptation.spec.ts --reporter=dot`. Expected: PASS。

Commit: `feat(frontend): add resource marketplace and management views`，只加入本任务的前端文件，不覆盖现存未提交的 `MemoryView.vue`、`UserView.vue` 或 `ResourceCenterView.vue` 用户变更。

### Task 6: 文档与最终验证

**Files:** Modify `apps/agentOS/src/components/resource/README.md`, `docs/superpowers/specs/2026-11-10-resource-marketplace-design.md`.

- [ ] **Step 1: 更新生命周期文档**

添加以下链路，并明确目录项、安装中 Job、失败 Job 都不是调度候选：

```text
CatalogItem -> InstallationJob -> checksum validation -> LocalLauncher
-> ResourcePlane Runtime registration -> health check -> ResourceBinder candidate
```

- [ ] **Step 2: 执行后端和 API 回归**

Run `pytest -q tests/components/marketplace tests/components/resource tests/components/scheduler`. Expected: PASS。

Run `pytest -q tests/test_agentos_v2_api.py -k "marketplace or resource"`. Expected: PASS。

- [ ] **Step 3: 执行前端构建和视觉验证**

Run `npm run build:web`. Expected: build succeeds without TypeScript errors.

Use Playwright at `1440x960` and `390x844` for `/agentos/resources/overview`, `/agentos/resources/manage`, `/agentos/resources/store`; check no overlap, readable state text, single-column mobile lanes, and working install/custom-resource controls.

- [ ] **Step 4: 最终检查并提交**

Run `git diff --check`. Expected: no whitespace errors.

Commit: `docs(resource): document marketplace scheduling boundary`，只包含本任务的 README 和规格文档更新。

## 自检

- 商店与资源平面边界：Task 1-4。
- 受控路径、校验、健康门槛、回滚和无 shell 自定义配置：Task 2-4。
- 概览、端边云管理和商店三个用户路径：Task 5。
- 文档、后端/API/前端回归与桌面/移动视觉检查：Task 6。
