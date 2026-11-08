import type { WorkspaceFileListing, WorkspaceFilePayload } from '@/services/api/agentos/types/workspace'
/**
 * Electron 桥合同：Main Process 经安全 Preload（contextBridge）暴露的最小白名单面。
 * Renderer 只依赖本类型与 getElectronBridge()，永不 import 'electron'，
 * 保证 Web 构建与测试环境永不解析 Node/Electron 模块。
 */
export interface KinlinOpenFileResult {
  name: string
  path: string
}

export interface KinlinAppInfo {
  version: string
  platform: string
  packaged: boolean
}

export interface TerminalProfile { id: string; name: string }
export interface WorkspaceSearchMatch {
  path: string
  line: number
  text: string
}
export interface WorkspaceSearchResult {
  matches: WorkspaceSearchMatch[]
  truncated: boolean
  engine: 'ripgrep' | 'node'
}

export interface WorkspaceDiagnosticItem {
  path: string
  line: number
  column: number
  severity: 'error' | 'warning' | 'info'
  message: string
  source: string
  code: string
}

export interface WorkspaceDiagnosticsResult {
  diagnostics: WorkspaceDiagnosticItem[]
  engine: 'tsc' | 'ruff' | 'none'
  durationMs: number
  truncated: boolean
  message?: string
}

export interface GitFileChange {
  path: string
  index: string
  worktree: string
}

export interface GitStatusResult {
  branch: string
  ahead: number
  behind: number
  files: GitFileChange[]
}

export interface LspDiagnosticItem {
  path: string
  line: number
  column: number
  severity: 'error' | 'warning' | 'info'
  message: string
  source: string
}

export interface LspLocationItem {
  path: string
  line: number
  column: number
}

export interface LspBridge {
  open(root: string, relativePath: string, text: string): Promise<{ languageId: string | null }>
  change(root: string, relativePath: string, text: string): Promise<void>
  close(root: string, relativePath: string): Promise<void>
  diagnostics(root: string): Promise<LspDiagnosticItem[]>
  definition(root: string, relativePath: string, line: number, column: number): Promise<LspLocationItem[]>
}
export interface TerminalSession {
  id: string; profileId: string; profileName: string; cwd: string; pid: number
  state: 'running' | 'exited'; exitCode: number | null; cols: number; rows: number; createdAt: string
}
export interface TerminalBridge {
  profiles(): Promise<{ profiles: TerminalProfile[] }>
  list(): Promise<{ sessions: TerminalSession[] }>
  create(options: { profileId?: string; cwd?: string; cols?: number; rows?: number }): Promise<TerminalSession>
  read(id: string, after: number): Promise<{ session: TerminalSession; cursor: number; truncated: boolean; chunks: {sequence: number; data: string}[] }>
  write(id: string, data: string): Promise<unknown>
  resize(id: string, cols: number, rows: number): Promise<unknown>
  close(id: string): Promise<unknown>
}

export interface KinlinDesktopBridge {
  /** Main 同步下发的后端 origin（product 模式下启动器可能改端口）。Web 构建为空串。 */
  apiOrigin?: string
  terminal?: TerminalBridge
  lsp?: LspBridge
  window: {
    minimize(): void
    toggleMaximize(): void
    close(): void
    isMaximized(): Promise<boolean>
    isFullscreen(): Promise<boolean>
    setFullscreen(fullscreen: boolean): Promise<void>
    /** 订阅真实窗口最大化状态（含 Win+↑、Snap、拖边等系统路径）；返回取消订阅函数。 */
    onMaximizeChanged(listener: (maximized: boolean) => void): () => void
  }
  /** 原生页面缩放由 preload 的 webFrame 直接落地，不走 Main IPC。 */
  zoom: {
    setZoomFactor(factor: number): void
  }
  dialog: {
    openFile(extensions?: string[]): Promise<KinlinOpenFileResult | null>
    openDirectory(): Promise<string | null>
  }
  workspace?: {
    choose(): Promise<{id: string; root: string} | null>
    current(): Promise<{id: string; root: string} | null>
    list(id: string, relative: string): Promise<WorkspaceFileListing>
    read(id: string, relative: string): Promise<{workspaceRoot: string; path: string} & WorkspaceFilePayload>
    save(id: string, relative: string, content: string, version: string): Promise<{path: string; version: string}>
    search(root: string, options: { query: string; caseSensitive?: boolean; maxResults?: number }): Promise<WorkspaceSearchResult>
    diagnostics(root: string): Promise<WorkspaceDiagnosticsResult>
    gitStatus(root: string): Promise<GitStatusResult>
    gitDiff(root: string, path: string, staged: boolean): Promise<string>
    gitShow(root: string, path: string, ref?: string): Promise<string | null>
    gitStage(root: string, paths: string[]): Promise<void>
    gitUnstage(root: string, paths: string[]): Promise<void>
    gitCommit(root: string, message: string): Promise<{ committed: boolean; output: string }>
    gitInit(root: string): Promise<void>
  }
  notify(title: string, body?: string): void
  openExternal(url: string): Promise<void>
  appInfo(): Promise<KinlinAppInfo>
  /**
   * 虚拟伙伴桌面能力（可选）：旧版 preload 没有这一节时前端自动降级。
   * 托盘菜单动作由 preload 做固定白名单收窄后才回调。
   */
  companion?: {
    publishState(snapshot: {
      state: string
      label: string
      level: number
      affinity: number
      quiet: boolean
      /** 可选：自定义名字与语音态，老版本 Main 会忽略。 */
      name?: string
      voice?: 'idle' | 'listening' | 'speaking'
    }): Promise<void>
    notifyIfBackground(title: string, body: string): Promise<void>
    onTrayAction(listener: (action: string) => void): () => void
  }
}

declare global {
  interface Window {
    kinlinDesktop?: KinlinDesktopBridge
  }
}

/** 桥缺失（非 Electron 宿主、Preload 未注入）时返回 null，调用方各自静默降级。 */
export function getElectronBridge(): KinlinDesktopBridge | null {
  const bridge = (window as Window & { kinlinDesktop?: KinlinDesktopBridge }).kinlinDesktop
  return bridge && typeof bridge === 'object' ? bridge : null
}
