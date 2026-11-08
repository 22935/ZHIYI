"""装配知弈 AgentOS 内部发行版（便携包）。

设计要点（均已在本机验证）：
- Python 不是 venv：复制一份 python.org 的 CPython 树（可搬移，sys.prefix 跟随 exe 位置），
  再把 venv 的 site-packages 整包放进 Lib/site-packages（.pth 无绝对路径）。
- TypeScript 后端使用随包 Node.js 24，不依赖 JVM。
- PostgreSQL 只取 bin/lib/share（pgAdmin 4 占原始 828MB 里的 683MB，不打包）。
- 承载并复用仓库现有代码布局：产品根目录仍保留 apps/ 结构，
  这样 native_runtime.ROOT 指向产品根即可复用既有启动逻辑。

用法：
  python ops/scripts/release/assemble_portable.py --out D:\\build\\ZhiyiAgentOS-1.0.0
  python ops/scripts/release/assemble_portable.py --out ... --dry-run
  python ops/scripts/release/assemble_portable.py --out ... --zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
ZHIYI_HOME = LOCALAPPDATA / "ZhiyiNative"
DEFAULT_PYTHON_BASE = Path(os.environ.get("LOCALAPPDATA") or "") / "Programs/Python/Python314"
DEFAULT_SITE_PACKAGES = ZHIYI_HOME / "python/Lib/site-packages"
DEFAULT_DEPENDENCIES = ZHIYI_HOME / "dependencies"
# 这些目录在复制时排除：开发产物、测试、文档、依赖缓存、数据与凭据。
COMMON_EXCLUDE_DIRS = [
    ".git", ".github", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules",
    "dist-electron", "tests", "test", "docs", "doc", "evals", "drafts", "tmp",
    ".mypy_cache", ".idea", ".vscode",
]
COMMON_EXCLUDE_FILES = ["*.pyc", "*.pyo", "*.log", "*.md", ".DS_Store"]


def log(message: str) -> None:
    print(f"[assemble] {message}", flush=True)


def size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / 1048576
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total / 1048576


def robocopy(source: Path, destination: Path, *, exclude_dirs=(), exclude_files=(), extra=()) -> None:
    """robocopy 比 shutil.copytree 快一个数量级，批量复制几十万小文件时尤其明显。"""
    if not source.exists():
        raise SystemExit(f"缺少源目录: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    command = ["robocopy", str(source), str(destination), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/R:1", "/W:1"]
    command += list(extra)
    if exclude_dirs:
        command += ["/XD"] + [str(source / name) for name in exclude_dirs]
    if exclude_files:
        command += ["/XF"] + list(exclude_files)
    result = subprocess.run(command, capture_output=True, text=True)
    # robocopy: 0-7 是成功/部分成功，>=8 才是失败
    if result.returncode >= 8:
        raise SystemExit(f"robocopy 失败({result.returncode}): {source} -> {destination}\n{result.stdout[-2000:]}")


def copy_python(base: Path, site_packages: Path, target: Path) -> None:
    log(f"Python: 复制解释器 {base} -> {target}")
    python_target = target / "runtime/python"
    if python_target.exists():
        shutil.rmtree(python_target)
    python_target.mkdir(parents=True)

    keep = ["python.exe", "pythonw.exe", "python314.dll", "python3.dll",
            "vcruntime140.dll", "vcruntime140_1.dll", "DLLs", "tcl", "Lib", "libs"]
    missing = [name for name in keep if not (base / name).exists()]
    if missing:
        raise SystemExit(f"Python 基础安装缺少必需项: {missing}")
    for name in keep:
        source = base / name
        if source.is_dir():
            robocopy(source, python_target / name,
                     exclude_dirs=("site-packages", "test", "idlelib", "tkinter/test", "unittest/test"),
                     exclude_files=("*.pyc",))
        else:
            shutil.copy2(source, python_target / name)

    log(f"Python: 复制 site-packages {site_packages} ({size_mb(site_packages):.0f} MB)")
    destination = python_target / "Lib/site-packages"
    destination.mkdir(parents=True, exist_ok=True)
    robocopy(site_packages, destination, exclude_files=("*.pyc", "*.pyo"))


def copy_postgres(dependencies: Path, target: Path) -> None:
    source = dependencies / "postgresql-15.19/pgsql"
    log(f"PostgreSQL: 复制 bin/lib/share（跳过 pgAdmin 4 / StackBuilder / doc）")
    destination = target / "runtime/pgsql"
    for name in ("bin", "lib", "share"):
        robocopy(source / name, destination / name, exclude_dirs=("pgAdmin 4", "__pycache__"))
    postgres = destination / "bin/postgres.exe"
    if not postgres.is_file():
        raise SystemExit("PostgreSQL 复制后缺少 bin/postgres.exe")


def copy_memurai(dependencies: Path, target: Path) -> None:
    source = dependencies / "memurai-4.1.2"
    log("Memurai: 复制可执行文件")
    destination = target / "runtime/memurai"
    robocopy(source, destination, exclude_files=("*.pdb", "*.cab", "*.msi"))
    if not (destination / "memurai.exe").is_file():
        raise SystemExit("Memurai 复制后缺少 memurai.exe")


def copy_node(node_exe: Path, target: Path) -> None:
    log(f"Node: 复制 {node_exe}（{node_exe.stat().st_size / 1048576:.0f} MB）")
    destination = target / "runtime/node"
    destination.mkdir(parents=True, exist_ok=True)
    version = subprocess.check_output([str(node_exe), "-v"], text=True).strip()
    if not version.startswith("v24."):
        raise SystemExit("发行版需要 Node.js 24 LTS")
    shutil.copy2(node_exe, destination / "node.exe")
    for name in ("LICENSE", "LICENSE.txt", "nodevars.bat"):
        candidate = node_exe.parent / name
        if candidate.is_file():
            shutil.copy2(candidate, destination / name)


def copy_shell(win_unpacked: Path, target: Path) -> None:
    log(f"桌面壳: 复制 win-unpacked（{size_mb(win_unpacked):.0f} MB）")
    destination = target / "app"
    robocopy(win_unpacked, destination, exclude_files=("*.pdb",))


def copy_backend(source: Path, target: Path) -> None:
    if not (source / "dist/main.js").is_file():
        raise SystemExit("先在 apps/backend-ts 执行 npm ci && npm run build")
    destination = target / "apps/backend-ts"
    robocopy(source / "dist", destination / "dist")
    robocopy(source / "migrations", destination / "migrations")
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(source / name, destination / name)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("装配构建机需要 npm")
    subprocess.run([npm, "ci", "--omit=dev", "--no-audit", "--no-fund"],
                   cwd=destination, check=True)


def relink_junctions(source_root: Path, destination_root: Path) -> int:
    """把 pnpm 的 junction 结构在目标目录里重建。

    robocopy 遇到 junction 会把目标内容整份复制过来（内容重复、且 tsx 这类包
    会因为“真实路径”落在 node_modules/<pkg> 而找不到兄弟依赖 esbuild）。
    这里只保留一份真实内容，其余用 mklink /J 指回 .pnpm 里的同一位置。
    """
    if not source_root.exists() or not destination_root.exists():
        return 0
    links: list[tuple[Path, Path]] = []
    for root, dirs, _files in os.walk(source_root, followlinks=False):
        for name in dirs:
            candidate = Path(root) / name
            if candidate.is_junction() or candidate.is_symlink():
                links.append((candidate, Path(root)))
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_junction()
                   and not (Path(root) / d).is_symlink()]
    rebuilt = 0
    for candidate, _parent in links:
        try:
            target = Path(os.path.realpath(candidate))
            relative = target.relative_to(source_root.resolve())
        except (OSError, ValueError):
            continue  # 指向仓库外的链接（全局 store 等）不随包搬
        destination = destination_root / candidate.relative_to(source_root)
        destination_target = destination_root / relative
        if not destination_target.exists():
            continue
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_junction():
                shutil.rmtree(destination, ignore_errors=True)
            else:
                destination.unlink(missing_ok=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(destination), str(destination_target)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            rebuilt += 1
    return rebuilt


CRT_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
CRT_TARGETS = ("runtime/pgsql/bin", "runtime/node", "runtime/memurai")


def stage_crt_runtime(target: Path) -> None:
    """把 VC++ 运行库放到 exe 旁边。

    Windows 的 DLL 搜索会先看 exe 所在目录，因此 app-local 部署可以覆盖
    “目标机没装 VC++ 运行时”的情况；ucrtbase 属于系统组件，不复制。
    """
    system32 = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
    staged = 0
    for relative in CRT_TARGETS:
        directory = target / relative
        if not directory.is_dir():
            continue
        for name in CRT_DLLS:
            source = system32 / name
            if source.is_file():
                shutil.copy2(source, directory / name)
                staged += 1
    log(f"VC++ 运行库: 随包 {staged} 个 DLL（app-local）")


def install_hands_dependencies(destination: Path) -> None:
    """用 npm 装一份扁平 node_modules，取代 pnpm 的 junction 布局。

    pnpm 的 node_modules 靠 junction 指向 .pnpm；复制到产品目录后要么被 robocopy
    展开（体积翻倍且 tsx 找不到兄弟依赖 esbuild），要么在 zip 里丢失链接语义。
    扁平安装既小（17MB vs 82MB）又能直接压缩。
    """
    package_path = destination / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    development = package.pop("devDependencies", {}) or {}
    dependencies = dict(package.get("dependencies") or {})
    if "tsx" in development:  # 运行时用它执行 *.ts 入口
        dependencies["tsx"] = development["tsx"]
    package["dependencies"] = dependencies
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("装配需要 npm（仅构建机需要，产品运行时不依赖）")
    log("hands: npm 扁平安装运行时依赖")
    result = subprocess.run([npm, "install", "--omit=dev", "--no-audit", "--no-fund", "--loglevel=error"],
                            cwd=destination, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"hands npm install 失败: {result.stderr[-1500:]}")
    tsx = destination / "node_modules/tsx/dist/cli.mjs"
    if not tsx.is_file():
        raise SystemExit("hands 安装后缺少 tsx 入口")


def copy_application_code(target: Path) -> None:
    """按产品根保留 apps/ 布局，供 native_runtime.ROOT 指过来复用启动逻辑。"""
    log("应用代码: 复制 apps/ 需要的子目录（不含前端 node_modules / 测试 / 文档）")
    skip = ("dist", "dist-electron", "tests", "test", "docs", "tmp", "drafts", "reports")

    def copy_app(name: str, *, keep_node_modules: bool = False) -> None:
        source = REPO / "apps" / name
        exclude = skip if keep_node_modules else skip + ("node_modules",)
        robocopy(source, target / "apps" / name, exclude_dirs=exclude)

    # hands 已并入 agentOS（apps/agentOS/src/hands），随 agentOS 一并复制；
    # 其 node_modules 仍在此处按需扁平安装。terminal 本身就是 npm 布局。
    copy_app("agent")
    copy_app("agentOS")
    copy_app("terminal", keep_node_modules=True)

    # app/data、data/ 是开发机上的运行数据，运行时用的是 home\data，没必要随包分发。
    for relative in ("apps/agent/app/data", "apps/agent/data"):
        stale = target / relative
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)
            log(f"应用代码: 排除开发运行数据 {relative}")

    install_hands_dependencies(target / "apps/agentOS/src/hands")

    rebuilt = relink_junctions(REPO / "apps/terminal/node_modules",
                              target / "apps/terminal/node_modules")
    if rebuilt:
        log(f"terminal-host: 重建 {rebuilt} 个 junction")

    # 前端只需要打包壳里的 asar；源码不随包（避免把 480MB node_modules 带出去）
    log("前端源码: 跳过（壳已含 asar 产物）")

    scripts_target = target / "scripts"
    scripts_target.mkdir(parents=True, exist_ok=True)
    for name in ("prepare_agentos_runtime.py", "upgrade_agentos_c2_schema.py",
                 "upgrade_agentos_dispatch_schema.py"):
        candidate = REPO / "scripts" / name
        if candidate.is_file():
            shutil.copy2(candidate, scripts_target / name)


def copy_launcher(target: Path) -> None:
    log("启动器: 复制 native 运行时模块与 release 启动器")
    source = REPO / "ops/scripts/infra/windows/native"
    destination = target / "ops/scripts/infra/windows/native"
    robocopy(source, destination, exclude_dirs=("__pycache__", "tests"),
             exclude_files=("README*.md", "audit_secrets.py", "migrate_from_docker.py"))

    release_source = REPO / "ops/scripts/release"
    release_target = target / "ops/scripts/release"
    release_target.mkdir(parents=True, exist_ok=True)
    for name in ("product_runtime.py", "assemble_portable.py"):
        candidate = release_source / name
        if candidate.is_file():
            shutil.copy2(candidate, release_target / name)
    for name in ("__init__.py",):
        (release_target / name).write_text("", encoding="utf-8")


ENTRY_TEMPLATE = """@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set ELECTRON_RUN_AS_NODE=
"%~dp0runtime\\python\\python.exe" "%~dp0ops\\scripts\\release\\product_runtime.py" {action} %*
if errorlevel 1 (
  echo.
  echo [Zhiyi] {action} failed. See data-home\\logs for details.
  pause
)
"""

README_TEMPLATE = """# 知弈 AgentOS（内部版 {version}）

解压即用，不安装系统服务、不写注册表、不改系统 PATH。

## 使用

1. **解压到纯英文路径**（可以带空格，例如 `D:\\ZhiyiAgentOS 1.0`）。中文路径会让 PostgreSQL 初始化失败——它不支持非 ASCII 路径，启动器会直接提示而不是给出难懂的报错。
2. 双击 `start.cmd`：首次会初始化本地数据目录 `data-home\\`，然后拉起全部服务并打开窗口。
3. 首次进入后到 **设置 → 模型供应商** 填你自己的 API Key 并激活。
4. 回到桌面运行 `restart.cmd`（或 `stop.cmd` 后 `start.cmd`），让新配置对规划与执行链路生效。
5. 之后每次直接 `start.cmd`；数据、本机身份与配置都保留在 `data-home\\`。

| 文件 | 作用 |
| :-- | :-- |
| `start.cmd` | 启动全部服务并打开窗口 |
| `stop.cmd` | 停止全部服务（保留数据） |
| `restart.cmd` | 重启（配置 API Key 后用它生效） |
| `status.cmd` | 查看服务与端口状态 |

## 已知限制

- **路径必须是纯 ASCII**：PostgreSQL 不支持中文/非 ASCII 路径（程序目录与数据目录都算），
  含中文时启动器会直接报错并提示换路径，而不是抛出 initdb 的原始错误。
- **免登录**：首启建立本机身份，已有数据沿用历史 owner；
  界面不提供注册/登录。换机器或换 Windows 用户需要重新初始化 `data-home\\`。
- **Memurai（Redis 兼容层）为 Developer 版**：仅限开发测试用途，连续运行最长 10 天；
  长时间使用请按需重启。本发行版仅供内部使用，不得对外分发。
- **未签名**：Windows 可能提示"未知发布者"，选择"仍要运行"即可。
- **端口**：默认 15432/16379/18761/18765/18080/18766；若被占用，启动器会整体偏移到空闲端口组。
  被占用时启动器**只报错不杀进程**，请自行关闭占用程序或重新 `init` 换偏移。
- **数据目录**：`data-home\\`（含 PostgreSQL cluster、SQLite、workspace、日志）。
  删除整个解压目录即等于彻底卸载（数据一并删除）。
- 模型 Key 保存在 `data-home\\data\\llm_profiles.json`（仅当前 Windows 用户可读）。
"""


def write_entrypoints(target: Path, version: str) -> None:
    log("入口: 写 start/stop/restart/status 与内部版说明")
    actions = [("start.cmd", "up"), ("stop.cmd", "down"),
               ("restart.cmd", "restart"), ("status.cmd", "status")]
    for name, action in actions:
        # cmd 文件保持纯 ASCII：中文 Windows 默认 936 代码页，写中文会随 chcp 变化乱码。
        (target / name).write_bytes(ENTRY_TEMPLATE.format(action=action)
                                    .replace("\n", "\r\n").encode("ascii"))
    (target / "README-internal.md").write_text(README_TEMPLATE.format(version=version), encoding="utf-8")


# 资源管理器内置解压会按本地代码页解释 zip 里的文件名，中文名会变成乱码；
# 因此发行包内一律要求 ASCII 文件名，已知的中文资料在装配时改名。
ASCII_RENAME = {
    "README-内部版.md": "README-internal.md",
    "教师-教育知识库.md": "education-knowledge.md",
    "律师-法律知识库.md": "legal-knowledge.md",
    "程序员-技术知识库.md": "programmer-knowledge.md",
    "作家-文学知识库.md": "writer-knowledge.md",
}


def normalize_ascii_names(target: Path) -> None:
    """把残留的中文文件名改成 ASCII；改不了就直接失败，避免交付里出现乱码文件。"""
    renamed = 0
    refused: list[str] = []
    for root, _dirs, files in os.walk(target):
        for name in files:
            if name.isascii():
                continue
            mapped = ASCII_RENAME.get(name)
            source = Path(root) / name
            if mapped is None:
                refused.append(str(source.relative_to(target)))
                continue
            source.rename(source.with_name(mapped))
            renamed += 1
    if refused:
        raise SystemExit(f"发行包内存在未登记的非 ASCII 文件名，请先改名或加入 ASCII_RENAME: {refused[:5]}")
    if renamed:
        log(f"文件名: 规范化 {renamed} 个非 ASCII 名字")


def write_product_manifest(target: Path, version: str) -> None:
    manifest = {
        "product": "知弈 AgentOS",
        "edition": "internal",
        "version": version,
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "layout": {
            "shell": "app/",
            "runtime": "runtime/{python,node,pgsql,memurai}",
            "application": "apps/",
            "launcher": "ops/scripts/infra/windows/native/",
        },
        "versions": {
            "python": subprocess.run([str(target / "runtime/python/python.exe"), "-V"],
                                     capture_output=True, text=True).stdout.strip(),
            "node": subprocess.run([str(target / "runtime/node/node.exe"), "-v"],
                                   capture_output=True, text=True).stdout.strip(),
            "postgres": next((p.name for p in (target / "runtime/pgsql/share").glob("*.txt")), ""),
        },
    }
    (target / "product.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"product.json 已写入（version={version}）")


def count_reparse_points(root: Path) -> int:
    total = 0
    for current, dirs, _files in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(current) / name
            if path.is_junction() or path.is_symlink():
                total += 1
    return total


def make_archive(target: Path) -> Path:
    """打成 zip：优先用 7-Zip（多线程、体积更小），没有则退回标准库。"""
    # 不能用 with_suffix：目录名里的 ".0" 会被当成扩展名，把版本号吞掉。
    archive = target.parent / f"{target.name}.zip"
    links = count_reparse_points(target)
    if links:
        log(f"警告: 目录里仍有 {links} 个重解析点，解压后可能丢失链接语义")
    seven = Path("C:/Program Files/7-Zip/7z.exe")
    log(f"压缩 -> {archive}")
    if seven.is_file():
        result = subprocess.run([str(seven), "a", "-tzip", "-mx=5", "-mmt=on", "-bd", "-y",
                                 str(archive), target.name],
                                cwd=target.parent, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"7z 压缩失败: {result.stderr[-1500:]}")
    else:
        shutil.make_archive(str(target), "zip", root_dir=target.parent, base_dir=target.name)
    log(f"压缩完成: {archive} ({archive.stat().st_size / 1048576:.0f} MB)")
    return archive


def write_checksums(target: Path) -> None:
    log("校验和: 计算逐文件 SHA-256（大目录，稍等）")
    entries: list[dict[str, object]] = []
    for root, _dirs, files in os.walk(target):
        for name in files:
            path = Path(root) / name
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            entries.append({"path": str(path.relative_to(target)).replace("\\", "/"),
                            "size": path.stat().st_size, "sha256": digest})
    payload = {"files": entries, "count": len(entries)}
    (target / "checksums.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log(f"校验和完成: {len(entries)} 个文件")


def validate(target: Path) -> list[str]:
    required = [
        "app/Zhiyi AgentOS Electron.exe",
        "runtime/python/python.exe",
        "runtime/python/Lib/site-packages/fastapi/__init__.py",
        "runtime/node/node.exe",
        "runtime/pgsql/bin/postgres.exe",
        "runtime/pgsql/bin/initdb.exe",
        "runtime/memurai/memurai.exe",
        "apps/backend-ts/dist/main.js",
        "apps/backend-ts/node_modules/fastify/package.json",
        "apps/backend-ts/migrations/V13__drop_user_feedback.sql",
        "apps/agent/app/main.py",
        "apps/agentOS/src/runtime/workflow_runtime.py",
        "apps/agentOS/src/hands/node_modules/tsx/dist/cli.mjs",
        "apps/terminal/node_modules/node-pty/package.json",
        "scripts/prepare_agentos_runtime.py",
        "ops/scripts/infra/windows/native/persistent_runtime.py",
    ]
    return [name for name in required if not (target / name).exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description="装配内部发行版便携包")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--python-base", type=Path, default=DEFAULT_PYTHON_BASE)
    parser.add_argument("--site-packages", type=Path, default=DEFAULT_SITE_PACKAGES)
    parser.add_argument("--dependencies", type=Path, default=DEFAULT_DEPENDENCIES)
    parser.add_argument("--node-exe", type=Path, default=Path(shutil.which("node") or ""))
    parser.add_argument("--win-unpacked", type=Path,
                        default=REPO / "apps/desktop/electron/release/win-unpacked")
    parser.add_argument("--backend", type=Path, default=REPO / "apps/backend-ts")
    parser.add_argument("--checksums", action="store_true", help="额外生成逐文件 SHA-256（较慢）")
    parser.add_argument("--zip", action="store_true", help="装配后压缩为 zip")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = args.out.resolve()
    sources = {
        "python-base": args.python_base, "site-packages": args.site_packages,
        "dependencies": args.dependencies, "node": args.node_exe,
        "shell": args.win_unpacked, "backend": args.backend / "dist/main.js",
    }
    log(f"产品根: {target}")
    for name, path in sources.items():
        state = "OK" if path and Path(path).exists() else "缺失"
        log(f"  源[{name}] {path}  [{state}]")
    missing = [name for name, path in sources.items() if not path or not Path(path).exists()]
    if missing:
        raise SystemExit(f"缺少装配源: {missing}")
    if args.dry_run:
        log("dry-run：只检查源，不写盘")
        return 0

    if target.exists():
        log("目标目录已存在，清空后重建")
        shutil.rmtree(target)
    target.mkdir(parents=True)

    started = time.time()
    copy_python(args.python_base, args.site_packages, target)
    copy_postgres(args.dependencies, target)
    copy_memurai(args.dependencies, target)
    copy_node(args.node_exe, target)
    copy_shell(args.win_unpacked, target)
    copy_backend(args.backend, target)
    stage_crt_runtime(target)
    copy_application_code(target)
    copy_launcher(target)
    write_entrypoints(target, args.version)
    normalize_ascii_names(target)
    write_product_manifest(target, args.version)

    missing_files = validate(target)
    if missing_files:
        raise SystemExit(f"装配后缺少必需文件: {missing_files}")
    log(f"装配完成，总大小 {size_mb(target):.0f} MB，用时 {time.time() - started:.0f}s")

    if args.checksums:
        write_checksums(target)
    if args.zip:
        make_archive(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
