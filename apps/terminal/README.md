# 本地交互终端 Host

为 Electron 桌面用户提供 PTY 会话。实际 Shell 运行在独立 Node 进程中，前端使用 xterm，
Electron Main 仅转发经过发送窗口校验的 IPC。模型工具调用和 AgentOS Run 不使用此服务。

安装：在本目录运行 `npm ci`。服务由 Windows N03 的 `persistent.ps1 up/open` 启动，
无需手动提供密钥。默认端口 18766，仅监听回环地址；`GET /health` 可匿名探测，
其余接口需要专用 Bearer 与桌面所有者标识。服务配置与日志存放在 N03 home 中。

`npm test` 包含环境变量隔离、所有者隔离、HTTP 鉴权及真实 Windows ConPTY 交互验证。
本机使用 Node 24.19.0、node-pty 1.1.0、PowerShell 7.6.9 验证。
Shell 以当前 Windows 用户权限运行；只向 Shell 传递系统、用户目录及 PATH 等必要变量。
支持已安装的 PowerShell 7、Windows PowerShell、CMD、Git Bash，不允许网页指定任意可执行文件。
用户进入 Shell 后可执行本机已安装的程序。

面板隐藏、切页和渲染进程刷新保留会话；关闭标签或正常退出桌面会回收所属 PTY。
当前实现不提供跨桌面重启恢复、SSH 会话管理或 AI 自动操作终端。
每个服务最多 12 个会话，每个会话保留最近约 1 MiB 原始输出；显示截断提示。
Windows 系统 ConPTY 关闭时，node-pty 的辅助进程可能记录 `AttachConsole failed`；
真实进程回收测试仍须通过。未启用会导致本机测试进程挂起的 `useConptyDll` 替代路径。
