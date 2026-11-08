import { contextBridge, ipcRenderer, webFrame } from 'electron'
import { IPC } from './lib/ipc-contract'
import { isTrayAction } from './lib/companion-tray'
import { clampNumber } from './lib/validation'

/**
 * 安全 Preload：沙箱模式下唯一可用面是 contextBridge/ipcRenderer/webFrame。
 * 这里只做三件事：
 * 1. 以白名单通道（lib/ipc-contract.ts）invoke Main，不在 Renderer 暴露 ipcRenderer 本体；
 * 2. 把缩放落到 webFrame（无 IPC 往返，Main 不参与缩放）；
 * 3. 对事件回执做类型收窄后才交给页面。
 * 通道名单与参数校验的权威在 Main；Renderer 侧类型合同见
 * apps/frontend/src/platform/electron/bridge.ts（手工保持同构）。
 */

const invoke = (channel: string, ...args: unknown[]): Promise<unknown> => ipcRenderer.invoke(channel, ...args)

// 构建期写死的后端地址在 product 模式下可能被启动器换端口；以 Main 同步下发的为准。
const apiOrigin = ((): string => {
  try {
    const value = ipcRenderer.sendSync(IPC.appApiOrigin)
    return typeof value === 'string' ? value : ''
  } catch {
    return ''
  }
})()

const bridge = {
  apiOrigin,
  window: {
    minimize: (): void => {
      void invoke(IPC.windowMinimize).catch(() => undefined)
    },
    toggleMaximize: (): void => {
      void invoke(IPC.windowToggleMaximize).catch(() => undefined)
    },
    close: (): void => {
      void invoke(IPC.windowClose).catch(() => undefined)
    },
    isMaximized: (): Promise<boolean> => invoke(IPC.windowIsMaximized).then(Boolean),
    isFullscreen: (): Promise<boolean> => invoke(IPC.windowIsFullscreen).then(Boolean),
    setFullscreen: (fullscreen: boolean): Promise<void> =>
      invoke(IPC.windowSetFullscreen, Boolean(fullscreen)).then(() => undefined),
    onMaximizeChanged: (listener: (maximized: boolean) => void): (() => void) => {
      const wrapped = (_event: unknown, value: unknown): void => {
        if (typeof value === 'boolean') listener(value)
      }
      ipcRenderer.on(IPC.windowMaximizeChanged, wrapped)
      return () => {
        ipcRenderer.removeListener(IPC.windowMaximizeChanged, wrapped)
      }
    }
  },
  zoom: {
    setZoomFactor: (factor: number): void => {
      const clamped = clampNumber(factor, 0.25, 5)
      if (clamped === null) return
      try {
        webFrame.setZoomFactor(clamped)
      } catch {
        // webFrame 暂不可用时静默放弃，档位状态仍保留。
      }
    }
  },
  dialog: {
    openFile: (extensions?: string[]): Promise<{ name: string; path: string } | null> =>
      invoke(IPC.dialogOpenFile, extensions === undefined ? {} : { extensions }) as Promise<{ name: string; path: string } | null>,
    openDirectory: (): Promise<string | null> => invoke(IPC.dialogOpenDirectory) as Promise<string | null>
  },
  workspace: {
    choose: () => invoke(IPC.workspaceChoose),
    current: () => invoke(IPC.workspaceCurrent),
    list: (id: string, relative: string) => invoke(IPC.workspaceList, id, relative),
    read: (id: string, relative: string) => invoke(IPC.workspaceRead, id, relative),
    save: (id: string, relative: string, content: string, version: string) => invoke(IPC.workspaceSave, id, relative, content, version),
    search: (root: string, options: unknown) => invoke(IPC.workspaceSearch, root, options),
    diagnostics: (root: string) => invoke(IPC.workspaceDiagnostics, root),
    gitStatus: (root: string) => invoke(IPC.workspaceGitStatus, root),
    gitDiff: (root: string, path: string, staged: boolean) => invoke(IPC.workspaceGitDiff, root, path, staged),
    gitShow: (root: string, path: string, ref?: string) => invoke(IPC.workspaceGitShow, root, path, ref),
    gitStage: (root: string, paths: string[]) => invoke(IPC.workspaceGitStage, root, paths),
    gitUnstage: (root: string, paths: string[]) => invoke(IPC.workspaceGitUnstage, root, paths),
    gitCommit: (root: string, message: string) => invoke(IPC.workspaceGitCommit, root, message)
  },
  lsp: {
    open: (root: string, relativePath: string, text: string) => invoke(IPC.lspOpen, root, relativePath, text),
    change: (root: string, relativePath: string, text: string) => invoke(IPC.lspChange, root, relativePath, text),
    close: (root: string, relativePath: string) => invoke(IPC.lspClose, root, relativePath),
    diagnostics: (root: string) => invoke(IPC.lspDiagnostics, root),
    definition: (root: string, relativePath: string, line: number, column: number) =>
      invoke(IPC.lspDefinition, root, relativePath, line, column)
  },
  terminal: {
    profiles: () => invoke(IPC.terminalProfiles),
    list: () => invoke(IPC.terminalList),
    create: (options: unknown) => invoke(IPC.terminalCreate, options),
    read: (id: string, after: number) => invoke(IPC.terminalRead, id, after),
    write: (id: string, data: string) => invoke(IPC.terminalWrite, id, data),
    resize: (id: string, cols: number, rows: number) => invoke(IPC.terminalResize, id, cols, rows),
    close: (id: string) => invoke(IPC.terminalClose, id)
  },
  notify: (title: string, body?: string): void => {
    void invoke(IPC.notify, { title, body }).catch(() => undefined)
  },
  openExternal: (url: string): Promise<void> =>
    invoke(IPC.openExternal, url).then(() => undefined) as Promise<void>,
  appInfo: (): Promise<{ version: string; platform: string; packaged: boolean }> =>
    invoke(IPC.appInfo) as Promise<{ version: string; platform: string; packaged: boolean }>,
  // 虚拟伙伴桌面能力：只经固定通道，托盘事件先做白名单收窄。
  companion: {
    publishState: (snapshot: unknown): Promise<void> =>
      invoke(IPC.companionState, snapshot).then(() => undefined) as Promise<void>,
    notifyIfBackground: (title: string, body: string): Promise<void> =>
      invoke(IPC.companionNotify, { title, body }).then(() => undefined) as Promise<void>,
    onTrayAction: (listener: (action: string) => void): (() => void) => {
      const wrapped = (_event: unknown, value: unknown): void => {
        if (isTrayAction(value)) listener(value)
      }
      ipcRenderer.on(IPC.companionTrayAction, wrapped)
      return () => {
        ipcRenderer.removeListener(IPC.companionTrayAction, wrapped)
      }
    }
  }
}

contextBridge.exposeInMainWorld('kinlinDesktop', bridge)
