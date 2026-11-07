"""知弈 AgentOS 内部发行版启动器（product 模式）。

与 N03 开发栈的区别（刻意为之）：
1. 二进制全部来自随包 runtime\\，不碰 PATH 上的 Node / Python / PostgreSQL；
2. **不启动 Vite**：桌面壳直接用 asar 产物（kinlin-app://shell）；
3. 端口被占用时**只报错不杀进程**；
4. 首次启动建立本机身份，保留已有 Home 的历史身份；
5. 不注入任何模型 Key：用户在 Settings 里自配，重启后生效。

复用 N03 的成熟部件：DPAPI 凭据、端口偏移、日志目录、schema 准备、workspace grant、
进程身份校验与优雅停止（native_runtime / desktop_runtime / terminal_service）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

# 产品根 = ops/scripts/release/product_runtime.py 的上三层
PRODUCT_ROOT = Path(__file__).resolve().parents[3]

# native_runtime 的 ROOT 必须在 import 其它模块之前改掉：
# persistent_runtime / desktop_shell 都在 import 时用它算路径。
sys.path.insert(0, str(PRODUCT_ROOT / "ops/scripts/infra/windows/native"))
import native_runtime as native  # noqa: E402

native.ROOT = PRODUCT_ROOT

import persistent_runtime as persistent  # noqa: E402
import terminal_service  # noqa: E402
import desktop_runtime as desktop  # noqa: E402

persistent.ROOT = PRODUCT_ROOT

FORMAT = persistent.FORMAT
DEFAULT_HOME = PRODUCT_ROOT / "data-home"
SHELL_EXE_NAME = "Zhiyi AgentOS Electron.exe"

# 随包二进制：全部相对产品根解析，装配脚本保证存在。
def runtime_paths() -> dict[str, Path]:
    runtime = PRODUCT_ROOT / "runtime"
    return {
        "python": runtime / "python/python.exe",
        "node": runtime / "node/node.exe",
        "postgres_bin": runtime / "pgsql/bin",
        "memurai": runtime / "memurai/memurai.exe",
        "shell": PRODUCT_ROOT / "app" / SHELL_EXE_NAME,
    }


PATHS = runtime_paths()


def fail(message: str) -> None:
    raise RuntimeError(message)


# ---------------------------------------------------------------- 环境与路径
def prepare_environment() -> None:
    """把随包二进制放到 PATH 最前面。

    native_runtime / terminal_service 内部用 shutil.which('node') 解析解释器，
    这里统一改 PATH 比逐个改它们的调用点更稳，也避免误用用户机器上的同名程序。
    """
    front = [PATHS["node"].parent, PATHS["postgres_bin"]]
    parts = [str(p) for p in front if p.is_dir()]
    os.environ["PATH"] = os.pathsep.join(parts + [os.environ.get("PATH", "")])
    # 本机（及部分开发机）会把 Electron 二进制当 node 用；产品壳必须排除该变量，
    # 否则打包的 exe 会退化成 Node 进程并静默退出。
    os.environ.pop("ELECTRON_RUN_AS_NODE", None)
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("PYTHONUTF8", "1")


def home_for(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_HOME


def validate_home(home: Path) -> None:
    if os.name != "nt":
        fail("发行版只支持 Windows 11")
    if not home.is_absolute():
        fail("home 必须是绝对路径")
    for part in [home, *home.parents]:
        if part.exists() and (part.is_symlink() or part.is_junction()):
            fail(f"home 不能经过重解析目录: {part}")


def ensure_ascii_paths(root: Path, home: Path) -> None:
    """PostgreSQL 在 Windows 上不支持非 ASCII 路径（程序目录和数据目录都不行）。

    实测：路径含中文时 initdb 直接以 `invalid byte sequence for encoding "UTF8"` 失败；
    纯 ASCII 但带空格则正常。这里提前给出可执行的提示，而不是让用户看 initdb 的报错。
    """
    for label, path in (("程序目录", root), ("数据目录", home)):
        try:
            str(path).encode("ascii")
        except UnicodeEncodeError:
            fail(
                f"{label}包含中文或其它非 ASCII 字符：{path}\n"
                "PostgreSQL 不支持这种路径。请把发行包解压到纯英文目录"
                "（例如 D:\\ZhiyiAgentOS，可以带空格），再重新启动。"
            )


def ensure_layout() -> None:
    missing = [name for name, path in PATHS.items() if not path.exists()]
    if missing:
        fail(f"随包运行时缺失 {missing}；请重新解压完整发行包")


# ---------------------------------------------------------------- 端口
def port_owner(port: int) -> str:
    try:
        import psutil

        for connection in psutil.net_connections(kind="tcp"):
            if connection.laddr and connection.laddr.port == port and connection.status == "LISTEN":
                try:
                    process = psutil.Process(connection.pid)
                    return f"PID {connection.pid} ({process.name()})"
                except Exception:
                    return f"PID {connection.pid}"
    except Exception:
        pass
    return "未知进程"


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def occupied_ports(info: dict) -> list[tuple[str, int]]:
    """产品语义：占用就报错并给出 PID，绝不接管（那是开发栈的行为）。

    只检查产品真正会绑定的端口；frontend/debug 是 N03 开发栈专用的，产品不用。
    """
    used = ("postgres", "redis", "ai", "host", "backend", "terminal")
    ports = persistent.ports(info)
    return [(name, ports[name]) for name in used if not port_free(ports[name])]


def pick_port_offset() -> int:
    """挑一个整组端口都空闲的偏移，供 init 一次性固定下来。"""
    used = ("postgres", "redis", "ai", "host", "backend", "terminal")
    for offset in range(0, 40):
        ports = persistent.ports({"portOffset": offset})
        if all(port_free(ports[name]) for name in used):
            return offset
    fail("找不到整组空闲端口；请关闭占用 15432/16379/18761/18765/18080 等端口的程序后重试")
    return 0


# ---------------------------------------------------------------- 初始化
def protect(home: Path) -> None:
    persistent.protect(home)


def initialize(home: Path) -> dict:
    if (home / "environment.json").exists():
        return {"status": "READY", "initializedNow": False, "home": str(home)}
    if home.exists() and any(home.iterdir()):
        fail("home 目录非空且不像知弈环境；请换一个目录或先清空")

    guard = PATHS["postgres_bin"]
    for name in ("postgres.exe", "initdb.exe", "pg_ctl.exe", "psql.exe"):
        if not (guard / name).is_file():
            fail(f"随包 PostgreSQL 缺少 {name}")

    home.mkdir(parents=True, exist_ok=True)
    protect(home)
    workspace = home / "workspace"
    for path in (home / "temp", home / "logs", home / "redis", workspace):
        path.mkdir(exist_ok=True)

    # 不预置模型 Key：用户在产品内配置。deepseek 保留空串是因为
    # persistent_runtime.env_for() 会无条件读取该键，空串等价于“未配置”。
    creds = {name: secrets.token_hex(32)
             for name in ("pgadmin", "db", "redis", "token", "hmac")}
    creds.update(key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), deepseek="")
    (home / "credentials.dpapi").write_bytes(native.dpapi(json.dumps(creds).encode()))

    offset = pick_port_offset()
    info = {
        "format": FORMAT,
        "edition": "internal",
        "home": str(home),
        "workspace": str(workspace),
        "postgresBin": str(PATHS["postgres_bin"]),
        "memurai": str(PATHS["memurai"]),
        "database": "zhiyi",
        "databaseRole": "zhiyi_app",
        "redisDatabases": {"backend": 0, "coordination": 1, "providerState": 2},
        "created": datetime.now(timezone.utc).isoformat(),
        "redisLicense": "Memurai Developer; development/testing only; 10-day maximum uptime",
        "initialized": False,
        "portOffset": offset,
        "backend": "hands",
        "backendEntry": str(PRODUCT_ROOT / "apps/backend-ts/dist/main.js"),
        "authMode": "local",
    }
    native.write_json(home / "environment.json", info)
    persistent.save(home, persistent.state_for(home))
    return {"status": "READY", "initializedNow": True, "home": str(home),
            "workspace": str(workspace), "portOffset": offset}


# ---------------------------------------------------------------- HTTP
def api_base(info: dict) -> str:
    return f"http://127.0.0.1:{persistent.ports(info)['backend']}"


def start_service(home: Path, session: str, state: dict, name: str, command: list[str], env: dict):
    record = native.spawn(home, f"logs/{session}/{name}", command, env)
    state["processes"][name] = record
    persistent.save(home, state)
    return record


def start_postgres(home: Path, info: dict, creds: dict, session: str, state: dict) -> None:
    pgdata = home / "postgres"
    password_file = home / "temp/pg-init-password"
    logdir = home / "logs" / session
    logdir.mkdir(parents=True, exist_ok=True)
    if not (pgdata / "PG_VERSION").exists():
        password_file.write_text(creds["pgadmin"], encoding="utf-8")
        try:
            with (logdir / "initdb.log").open("ab") as log:
                subprocess.run([str(PATHS["postgres_bin"] / "initdb.exe"), "-D", str(pgdata),
                                "-U", "zhiyi_admin", "--encoding=UTF8", "--locale=C",
                                "--auth=scram-sha-256", "--pwfile=" + str(password_file)],
                               stdout=log, stderr=log, check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "PostgreSQL 初始化失败；日志见 data-home\\logs\\<会话>\\initdb.log。"
                "最常见原因是安装路径或数据目录包含中文（PostgreSQL 不支持非 ASCII 路径）。"
            ) from error
        password_file.unlink(missing_ok=True)
        with (pgdata / "postgresql.conf").open("a", encoding="utf-8") as file:
            file.write(f"\nlisten_addresses='127.0.0.1'\nport={persistent.ports(info)['postgres']}\n"
                       "password_encryption='scram-sha-256'\n")
    record = start_service(home, session, state, "postgres",
                           [str(PATHS["postgres_bin"] / "postgres.exe"), "-D", str(pgdata)],
                           persistent.env_for(home, info, creds))

    def ready() -> bool:
        try:
            return persistent.sql(info, creds, "SELECT 1;") == "1"
        except Exception:
            return False

    desktop.wait_until(ready, record, 90)


def start_redis(home: Path, info: dict, creds: dict, session: str, state: dict) -> None:
    config = (f"bind 127.0.0.1\nprotected-mode yes\nport {persistent.ports(info)['redis']}\n"
              f'dir "{(home / "redis").as_posix()}"\nappendonly yes\nappendfsync everysec\nsave 60 1\n'
              "maxmemory-policy noeviction\n")
    (home / "redis/settings.conf").write_text(config, encoding="utf-8")
    auth = home / "temp/redis-auth.conf"
    auth.write_text(config + "requirepass " + creds["redis"] + "\n", encoding="utf-8")
    try:
        record = start_service(home, session, state, "redis",
                               [str(PATHS["memurai"]), str(auth)],
                               persistent.env_for(home, info, creds))
        client = persistent.redis_client(creds, port=persistent.ports(info)["redis"])
        desktop.wait_until(lambda: client.ping(), record, 60)
        client.close()
    finally:
        auth.unlink(missing_ok=True)


def start_hands(home: Path, info: dict, creds: dict, session: str, state: dict, env: dict) -> None:
    grants = home / "hands-grants.json"
    keys = home / "temp/hands-keys.json"
    native.write_json(keys, {"credentials": [{"credentialId": "n01a-credential", "secret": creds["hmac"]}]})
    config = home / "hands-service.json"
    native.write_json(config, {
        "workspaceRoot": info["workspace"], "credentialsFile": str(keys), "grantsFile": str(grants),
        "dataDir": str(home / "hands-ledger"), "host": "127.0.0.1",
        "port": persistent.ports(info)["host"], "confinement": "none", "dynamicWorkspaces": True})
    node_env = dict(env, TSX_TSCONFIG_PATH=str(PRODUCT_ROOT / "apps/hands/tsconfig.json"))
    try:
        record = start_service(home, session, state, "host", [
            str(PATHS["node"]),
            str(PRODUCT_ROOT / "apps/hands/node_modules/tsx/dist/cli.mjs"),
            "--tsconfig", str(PRODUCT_ROOT / "apps/hands/tsconfig.json"),
            str(PRODUCT_ROOT / "apps/hands/hands/service-main.ts"),
            "--config", str(config)], node_env)
        desktop.wait_until(lambda: native.health(persistent.ports(info)["host"], "/v1/health").get("ok"),
                           record, 90)
    finally:
        keys.unlink(missing_ok=True)


def shell_environment(home: Path, info: dict, creds: dict) -> dict:
    """只给壳它真正需要的：OS 目录、API origin、终端凭据。绝不注入模型 Key。"""
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "USERPROFILE", "APPDATA",
               "LOCALAPPDATA", "PROGRAMDATA", "TEMP", "TMP", "NO_PROXY", "USERNAME", "USERDOMAIN",
               "HOMEDRIVE", "HOMEPATH"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update({
        "KINLIN_API_ORIGIN": api_base(info),
        "KINLIN_APP_VERSION": native.read_json(PRODUCT_ROOT / "product.json").get("version", "")
        if (PRODUCT_ROOT / "product.json").exists() else "",
    })
    env.update(terminal_service.desktop_environment(home, info, creds))
    return env


def start_shell(home: Path, info: dict, creds: dict, session: str, state: dict) -> dict:
    env = shell_environment(home, info, creds)
    command = [str(PATHS["shell"]), f"--user-data-dir={home / 'electron'}"]
    # 支持/排障用：需要 CDP 取证时由外部设置 KINLIN_DEBUG_PORT，默认不开放调试端口。
    debug_port = (os.environ.get("KINLIN_DEBUG_PORT") or "").strip()
    if debug_port.isdigit():
        command.append(f"--remote-debugging-port={int(debug_port)}")
    record = desktop.spawn_app(home, f"logs/{session}/desktop", command, env, PRODUCT_ROOT / "app")
    state["processes"]["desktop"] = record
    persistent.save(home, state)
    # 打包壳没有 CDP 端口；以“进程存活 + 出现窗口”为就绪判据。
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if native.owned(record) is None:
            fail("桌面壳启动后立即退出；查看 data-home/logs/<会话>/desktop.log")
        windows = desktop.show_desktop(record, ("Chrome_WidgetWin_1",))
        if windows:
            state["desktopWindows"] = windows
            persistent.save(home, state)
            return windows
        time.sleep(1)
    fail("桌面壳进程在运行但没有出现窗口；查看 data-home/logs/<会话>/desktop.log")


def up(home: Path, *, window: bool = True) -> dict:
    info, creds, state = persistent.manifest(home), native.credentials(home), persistent.state_for(home)
    if any(persistent.alive(record) for record in state["processes"].values()):
        fail("当前 home 还有进程在跑；先执行 down 或 restart")

    blocked = occupied_ports(info)
    if blocked:
        detail = "; ".join(f"{name}={port} 被 {port_owner(port)} 占用" for name, port in blocked)
        fail(f"端口被占用，启动中止（不会杀掉占用进程）：{detail}")

    session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(2)
    (home / "logs" / session).mkdir(parents=True, exist_ok=True)
    state.update(processes={}, session=session)
    persistent.save(home, state)
    env = persistent.env_for(home, info, creds)

    try:
        start_postgres(home, info, creds, session, state)
        if not info["initialized"]:
            if not persistent.sql(info, creds, "SELECT 1 FROM pg_roles WHERE rolname='zhiyi_app';"):
                persistent.sql(info, creds, "CREATE ROLE zhiyi_app LOGIN NOSUPERUSER NOCREATEDB "
                                            "NOCREATEROLE NOREPLICATION PASSWORD "
                                            f"'{creds['db']}';")
            if not persistent.sql(info, creds, "SELECT 1 FROM pg_database WHERE datname='zhiyi';"):
                persistent.sql(info, creds, "CREATE DATABASE zhiyi OWNER zhiyi_app;")
        if not info["initialized"]:
            info["initialized"] = True
            native.write_json(home / "environment.next.json", info)
            (home / "environment.next.json").replace(home / "environment.json")
        backend_env = persistent.prepare_platform(home, info, creds)
        backend_env.pop("ZHIYI_BACKEND_TS_DEV_ORIGIN", None)
        backend = start_service(home, session, state, "backend", [
            str(PATHS["node"]), str(PRODUCT_ROOT / "apps/backend-ts/dist/main.js")], backend_env)
        desktop.wait_until(
            lambda: native.health(persistent.ports(info)["backend"], "/health/ready").get("status") == "UP",
            backend, 90)
        start_redis(home, info, creds, session, state)
        persistent.schema(home, env, not (home / "data").exists())
        persistent.prepare_workspace_grants(home, info, env)
        terminal_service.start(home, info, creds, state)
        start_hands(home, info, creds, session, state, env)
        ai = start_service(home, session, state, "ai", [
            str(PATHS["python"]), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(persistent.ports(info)["ai"]), "--workers", "1"], env)
        desktop.wait_until(
            lambda: native.health(persistent.ports(info)["ai"], "/health/ready").get("status") == "UP",
            ai, 240)

        windows = start_shell(home, info, creds, session, state) if window else []
        if not info["initialized"]:
            info["initialized"] = True
            temporary = home / "environment.next.json"
            native.write_json(temporary, info)
            temporary.replace(home / "environment.json")
    except BaseException:
        # 失败即回收本次拉起的进程，避免留下半栈。
        for record in reversed(list(state["processes"].values())):
            try:
                native.stop(record)
            except Exception:
                pass
        raise

    return {"status": "UP", "home": str(home), "api": api_base(info), "session": session,
            "ports": persistent.ports(info), "desktopWindows": windows,
            "note": "首次使用请在 Settings 配置模型 API Key，保存后执行 restart 生效"}


def down(home: Path) -> dict:
    return persistent.down(home)


def status(home: Path) -> dict:
    return persistent.status(home)


def restart(home: Path, *, window: bool = True) -> dict:
    down(home)
    time.sleep(1)
    return up(home, window=window)


def open_window(home: Path) -> dict:
    """重新打开窗口：服务都在跑就只拉起壳，否则整栈启动。"""
    info, creds, state = persistent.manifest(home), native.credentials(home), persistent.state_for(home)
    alive = {name: record for name, record in state["processes"].items() if persistent.alive(record)}
    if not alive:
        return up(home, window=True)
    shell = alive.get("desktop")
    if shell:
        windows = desktop.show_desktop(shell, ("Chrome_WidgetWin_1",))
        if windows:
            return {"status": "UP", "desktopWindows": windows}
    session = state.get("session") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    windows = start_shell(home, info, creds, session, state)
    return {"status": "UP", "desktopWindows": windows}


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知弈 AgentOS 内部发行版启动器")
    parser.add_argument("action", choices=["init", "up", "down", "restart", "status", "open"])
    parser.add_argument("--home", default=None)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        prepare_environment()
        ensure_layout()
        home = home_for(args.home)
        validate_home(home)
        ensure_ascii_paths(PRODUCT_ROOT, home)

        if args.action == "init":
            result = initialize(home)
        elif args.action in {"up", "restart"}:
            # 便携包只有 start.cmd 一个入口：首次启动自动初始化，用户不需要先敲 init。
            if not (home / "environment.json").exists():
                print(f"[product] 首次启动，初始化本地数据目录：{home}", flush=True)
                initialize(home)
            if args.action == "restart":
                result = restart(home, window=not args.no_window)
            else:
                state = persistent.state_for(home)
                running = any(persistent.alive(record) for record in state["processes"].values())
                # 关窗后服务仍在跑：start.cmd 的语义是"确保在跑并显示窗口"，
                # 而不是报错让用户猜该敲哪条命令。
                result = open_window(home) if running else up(home, window=not args.no_window)
        elif args.action == "down":
            if not (home / "environment.json").exists():
                result = {"status": "PASS", "home": str(home), "message": "尚未初始化，无需停止"}
            else:
                result = down(home)
        elif args.action == "open":
            result = open_window(home)
        else:
            result = status(home)
    except Exception as error:  # noqa: BLE001 - 顶层统一给人看的错误
        if args.json:
            print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        else:
            print(f"[product] 失败: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") in {"UP", "READY", "PASS"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
