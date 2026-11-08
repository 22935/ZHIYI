/**
 * IPC 通道名单一权威：Main Process 注册与 Preload 调用共用，
 * 防止通道名漂移导致白名单失配。Renderer 侧类型合同见
 * apps/frontend/src/platform/electron/bridge.ts（手工保持同构）。
 */
export const IPC = {
  windowMinimize: 'kinlin:window/minimize',
  windowToggleMaximize: 'kinlin:window/toggle-maximize',
  windowClose: 'kinlin:window/close',
  windowIsMaximized: 'kinlin:window/is-maximized',
  windowIsFullscreen: 'kinlin:window/is-fullscreen',
  windowSetFullscreen: 'kinlin:window/set-fullscreen',
  /** Main → Renderer 事件：真实窗口最大化状态变化（含 Win+↑、Snap 等系统路径）。 */
  windowMaximizeChanged: 'kinlin:window/maximize-changed',
  dialogOpenFile: 'kinlin:dialog/open-file',
  dialogOpenDirectory: 'kinlin:dialog/open-directory',
  workspaceChoose: 'kinlin:workspace/choose',
  workspaceCurrent: 'kinlin:workspace/current',
  workspaceList: 'kinlin:workspace/list',
  workspaceRead: 'kinlin:workspace/read',
  workspaceSave: 'kinlin:workspace/save',
  workspaceSearch: 'kinlin:workspace/search',
  workspaceDiagnostics: 'kinlin:workspace/diagnostics',
  workspaceGitStatus: 'kinlin:workspace/git-status',
  workspaceGitDiff: 'kinlin:workspace/git-diff',
  workspaceGitShow: 'kinlin:workspace/git-show',
  workspaceGitStage: 'kinlin:workspace/git-stage',
  workspaceGitUnstage: 'kinlin:workspace/git-unstage',
  workspaceGitCommit: 'kinlin:workspace/git-commit',
  workspaceGitInit: 'kinlin:workspace/git-init',
  lspOpen: 'kinlin:lsp/open',
  lspChange: 'kinlin:lsp/change',
  lspClose: 'kinlin:lsp/close',
  lspDiagnostics: 'kinlin:lsp/diagnostics',
  lspDefinition: 'kinlin:lsp/definition',
  terminalProfiles: 'kinlin:terminal/profiles',
  terminalList: 'kinlin:terminal/list',
  terminalCreate: 'kinlin:terminal/create',
  terminalRead: 'kinlin:terminal/read',
  terminalWrite: 'kinlin:terminal/write',
  terminalResize: 'kinlin:terminal/resize',
  terminalClose: 'kinlin:terminal/close',
  notify: 'kinlin:notify',
  openExternal: 'kinlin:open-external',
  appInfo: 'kinlin:app/info',
  /** 同步读取后端 origin：product 模式下端口可能被启动器改过，不能只信构建期常量。 */
  appApiOrigin: 'kinlin:app/api-origin'
} as const

export type IpcChannel = (typeof IPC)[keyof typeof IPC]
