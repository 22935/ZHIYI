# 知弈 AgentOS 桌面版（Electron）

桌面版基于 Electron（Chromium）作为 Windows 桌面壳，把现有 Vue 前端打包为本地应用，
通过 HTTP、SSE 与 WebSocket 连接本机 Java 后端（原生 N03 栈，默认 18080）。
Electron 是当前唯一桌面宿主；Tauri 2 宿主已随桌面入口切换整体移除，迁移与验收过程见
`docs/开发记录/PR-EL-01 系列报告`。

- 宿主实现与开发/打包/安全基线说明：[electron/README.md](./electron/README.md)
- 日常启动入口（桌面快捷方式）：`ops/scripts/start-local-desktop.ps1`，启动完整 N03 本地环境与 Electron；重复点击聚焦已有窗口，关闭窗口后再次点击仅重开桌面，不重启健康服务
- 开发热更新入口：`ops/scripts/start-desktop-hot.ps1`，需先启动 N03 后端
- 原生持久环境（N03）经 `desktop_shell.py` 拉起同一 Electron 壳；N02 旧桌面入口已退役

桌面壳只负责窗口、原生交互与桌面生命周期；任务执行权威在 AgentOS Runtime 与
知行 Host，桌面端不内嵌执行器或调度器。

桌面图标 `zhiyi AgentOS` 默认复用 `%LOCALAPPDATA%\ZhiyiNative\default` 的账户与数据。
启动过程可能需要一到两分钟；启动失败时窗口保留错误信息。关闭 Electron 窗口后后台服务继续运行，
完整停止请在仓库终端执行 `./ops/scripts/infra/windows/native/persistent.ps1 down`。

`start-desktop-hot.ps1` 保持 UTF-8 BOM 编码，以兼容桌面快捷方式调用的 Windows PowerShell 5.1。

## 内置终端

点击顶部“终端”或按 **Ctrl+反引号（`）**，即可展开底部终端。支持本机已安装的
PowerShell 7、Windows PowerShell、CMD 和 Git Bash，可选择 Shell、新建多个标签、
选择任意本机目录、拖动上沿调整高度。新标签优先使用当前选定工作区；状态栏显示启动目录，
后续 `cd` 以 Shell 提示符为准。收起面板会继续运行，标签上的 × 会终止该会话。
切换页面、刷新页面保留会话与变量；退出整个桌面会关闭本次桌面拥有的终端，重开后创建新会话。

首次安装还需在 `apps/terminal` 执行 `npm ci`，在 `apps/frontend` 执行 `npm ci`。
使用桌面图标启动时 N03 自动拉起终端服务。热更新或构建入口默认连接
`%LOCALAPPDATA%\ZhiyiNative\default`，可用 `KINLIN_NATIVE_HOME` 指定环境。
终端使用当前 Windows 用户权限；Git、Python、Node 等命令是否可用取决于本机安装与 PATH。
该终端供用户直接操作；AI 的工具调用仍走现有 Runtime/Host 流程，本次没有把终端自动授权给模型。

进程归属：Vue xterm → Electron IPC 传输 → 独立本地 PTY 服务；Electron Main 不内嵌执行器。
终端服务监听 `127.0.0.1:18766`（加环境端口偏移），仅 Main 持有专用凭据；Shell 不继承后端密钥。
关闭桌面保留后台服务；执行 N03 `down` 才停止终端服务和整个本地环境。
