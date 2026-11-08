import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  Notification,
  screen,
  session,
  shell,
  Tray
} from 'electron'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import * as path from 'node:path'
import { IPC } from './lib/ipc-contract'
import { TerminalClient } from './lib/terminal-client'
import { WorkspaceFiles } from './lib/workspace-files'
import { normalizeSearchOptions, searchWorkspace, validateSearchRoot } from './lib/workspace-search'
import { runDiagnostics, validateDiagnosticsRoot } from './lib/workspace-diagnostics'
import { LspHost } from './lib/lsp-host'
import { gitCommit, gitDiff, gitShow, gitStage, gitStatus, gitUnstage, validateGitRoot } from './lib/workspace-git'
import { APP_INDEX_URL, APP_SCHEME, APP_HOST, handleAppProtocol, registerAppScheme } from './lib/protocol'
import { createFileLogger, type FileLogger } from './lib/logging'
import {
  DEFAULT_COMPANION_SNAPSHOT,
  formatTrayTooltip,
  isTrayAction,
  parseCompanionSnapshot,
  parseNotification,
  shouldDeliverNotification,
  trayMenuDescriptor,
  type CompanionSnapshot
} from './lib/companion-tray'
import {
  fitsAnyDisplay,
  parseBoolean,
  parseBoundedText,
  parseExtensions,
  parseHttpUrl
} from './lib/validation'
import {
  DEFAULT_WINDOW_STATE,
  dropStalePosition,
  parseWindowState,
  serializeWindowState,
  type WindowState
} from './lib/window-state'

/**
 * 知弈 AgentOS Electron Desktop Host。
 *
 * 边界约束（架构门禁另测）：
 * - 本进程只负责窗口、原生交互与桌面生命周期；
 * - 不内嵌执行器、Scheduler，不直接调用模型生成执行决策；
 * - 任务执行权威在 AgentOS Runtime / 知行 Host，经既有 HTTP/WS 边界接入；
 * - 手动文件编辑由原生目录选择器授权；Agent 执行的目录权限仍由 Host Grant 决定。
 */

const DEV_DEFAULT_SERVER = 'http://127.0.0.1:15100'
// 原生运行形态没有 Docker 网关：打包壳直连本机 TypeScript 后端。
const DEFAULT_API_ORIGIN = 'http://127.0.0.1:18080'

function parseArgValue(flag: string): string | undefined {
  const prefix = `${flag}=`
  for (const arg of process.argv) {
    if (arg.startsWith(prefix)) return arg.slice(prefix.length)
  }
  return undefined
}

const devServerUrl = parseArgValue('--dev-server')
const isolatedUserData = parseArgValue('--user-data-dir')
if (isolatedUserData) {
  if (!path.isAbsolute(isolatedUserData)) throw new Error('--user-data-dir must be absolute')
  mkdirSync(isolatedUserData, { recursive: true })
  app.setPath('userData', isolatedUserData)
}
const openDevtools = process.argv.includes('--devtools')
// 与 webPreferences.devTools 同源：仅开发/调试形态允许打开开发者工具（F12 依此放行）。
const devToolsEnabled = !app.isPackaged || Boolean(devServerUrl)
const apiOrigin = (() => {
  const configured = parseHttpUrl(process.env.KINLIN_API_ORIGIN)
  return configured ? configured.origin : DEFAULT_API_ORIGIN
})()

registerAppScheme() // 必须发生在 app ready 之前
let mainWindow: BrowserWindow | null = null
let lspHost: LspHost | null = null
let logger: FileLogger | null = null
/** 托盘必须被强引用，否则被 GC 后图标会消失。 */
let companionTray: Tray | null = null
let companionSnapshot: CompanionSnapshot = DEFAULT_COMPANION_SNAPSHOT
const terminalClient = new TerminalClient()

const stateFilePath = (): string => path.join(app.getPath('userData'), 'window-state.json')

function loadWindowState(): WindowState {
  const raw = (() => {
    try {
      return readFileSync(stateFilePath(), 'utf8')
    } catch {
      return null
    }
  })()
  const parsed = parseWindowState(raw, DEFAULT_WINDOW_STATE)
  return dropStalePosition(parsed, (bounds) => fitsAnyDisplay(bounds, screen.getAllDisplays().map((d) => d.bounds)))
}

function persistWindowState(win: BrowserWindow): void {
  if (!logger) return
  try {
    const payload = serializeWindowState(win.getNormalBounds(), win.isMaximized(), win.isFullScreen())
    writeFileSync(stateFilePath(), payload, 'utf8')
  } catch (error) {
    logger.warn('window state persist failed', { error: String(error) })
  }
}

function rendererDir(): string {
  // dist/main.js 与 renderer/ 在同一 asar（或仓库 electron 目录）内。
  return path.resolve(__dirname, '..', 'renderer')
}

function isAllowedPageUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    if (devServerUrl) return parsed.origin === new URL(devServerUrl).origin
    return parsed.protocol === `${APP_SCHEME}:` && parsed.host === APP_HOST
  } catch {
    return false
  }
}

function createWindow(): void {
  if (!logger) return
  const state = loadWindowState()
  const win = new BrowserWindow({
    title: '知弈 AgentOS',
    // 任务栏/Alt-Tab 用知弈图标（dist/icons 由 build.mjs 从 icons/ 拷入）；
    // 不设则未打包运行会显示 Electron 默认原子图标。
    icon: path.join(__dirname, 'icons', 'icon.ico'),
    width: state.width,
    height: state.height,
    minWidth: 1100,
    minHeight: 700,
    x: state.x,
    y: state.y,
    frame: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      spellcheck: false,
      devTools: devToolsEnabled
    }
  })

  win.once('ready-to-show', () => {
    win.show()
    if (state.isMaximized) win.maximize()
    if (state.isFullscreen) win.setFullScreen(true)
  })

  // 窗口级快捷键在 Main 拦截：页面僵死/崩溃后 F11/F12 仍可用。
  // 应用级快捷键（Ctrl+B、Ctrl+R、Alt+方向、F1）在渲染进程处理——
  // 内置终端里 Ctrl+R/B 是 shell 键，需按焦点让位，Main 无法感知。
  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return
    const plain = !input.control && !input.meta && !input.alt && !input.shift
    if (!plain) return
    if (input.key === 'F11') {
      event.preventDefault()
      win.setFullScreen(!win.isFullScreen())
      return
    }
    if (input.key === 'F12') {
      // 生产包 devTools 关闭：放行不拦截，按键无反应属预期。
      if (!devToolsEnabled) return
      event.preventDefault()
      if (win.webContents.isDevToolsOpened()) win.webContents.closeDevTools()
      else win.webContents.openDevTools({ mode: 'detach' })
    }
  })

  const sendMaximizeState = (): void => {
    if (!win.isDestroyed()) win.webContents.send(IPC.windowMaximizeChanged, win.isMaximized())
  }
  win.on('maximize', sendMaximizeState)
  win.on('unmaximize', sendMaximizeState)
  win.on('close', () => persistWindowState(win))

  mainWindow = win

  const target = devServerUrl || APP_INDEX_URL
  const log = logger
  log.info('loading page', { target })
  win.loadURL(target).catch((error) => {
    log.error('page load failed', { target, error: String(error) })
    dialog.showErrorBox('知弈 AgentOS', '界面加载失败，请查看日志后重试。')
    app.quit()
  })
  if (openDevtools) win.webContents.openDevTools({ mode: 'detach' })
}

/**
 * 虚拟伙伴托盘：只做「显示主窗口 / 快捷意图 / 免打扰」，不创建第二个 BrowserWindow。
 * 单窗口授权模型（authorized 绑定 mainWindow.mainFrame）与会话权限策略均保持不变。
 */
function restoreMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  if (!mainWindow.isVisible()) mainWindow.show()
  mainWindow.focus()
}

function emitTrayAction(action: string): void {
  if (!isTrayAction(action)) return
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(IPC.companionTrayAction, action)
  }
}

function refreshCompanionTray(): void {
  if (!companionTray) return
  companionTray.setToolTip(formatTrayTooltip(companionSnapshot))
  const template: Electron.MenuItemConstructorOptions[] = trayMenuDescriptor(companionSnapshot).map((item) => {
    if (item.kind === 'separator') return { type: 'separator' as const }
    if (item.kind === 'checkbox') {
      return {
        type: 'checkbox' as const,
        label: item.label,
        checked: item.checked,
        click: () => emitTrayAction('quiet')
      }
    }
    return {
      type: 'normal' as const,
      label: item.label,
      click: () => {
        const action = item.action
        if (action === 'quit') { app.quit(); return }
        if (action === 'focus') { restoreMainWindow(); emitTrayAction('focus'); return }
        if (isTrayAction(action)) {
          // 语音输入需要用户能看见并操作面板，先恢复主窗口再下发动作。
          if (action === 'summon' || action === 'progress' || action === 'voice') restoreMainWindow()
          emitTrayAction(action)
        }
      }
    }
  })
  companionTray.setContextMenu(Menu.buildFromTemplate(template))
}

function createCompanionTray(): void {
  const iconPath = path.join(__dirname, 'icons', 'companion-tray.png')
  const image = nativeImage.createFromPath(iconPath)
  if (image.isEmpty()) {
    logger?.warn('companion tray icon unavailable; tray disabled', { iconPath })
    return
  }
  try {
    const tray = new Tray(image)
    companionTray = tray
    refreshCompanionTray()
    tray.on('click', () => { restoreMainWindow(); emitTrayAction('toggle') })
    tray.on('double-click', () => { restoreMainWindow(); emitTrayAction('summon') })
  } catch (error) {
    logger?.warn('companion tray unavailable', { error: String(error) })
    companionTray = null
  }
}

/** 会话级加固：拒绝全部权限请求与检查（media/geolocation/notifications 等）。 */
function hardenSession(target: Electron.Session, log: FileLogger): void {
  target.setPermissionRequestHandler((_contents, permission, callback) => {
    log.warn('permission request denied', { permission })
    callback(false)
  })
  target.setPermissionCheckHandler((_contents, permission) => {
    log.warn('permission check denied', { permission })
    return false
  })
}

function wireWebContentsGuards(): void {
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-navigate', (event, url) => {
      if (isAllowedPageUrl(url)) return
      event.preventDefault()
      logger?.warn('navigation blocked', { url })
      const parsed = parseHttpUrl(url)
      if (parsed) void shell.openExternal(parsed.toString()).catch(() => undefined)
    })
    contents.setWindowOpenHandler(({ url }) => {
      // window.open 一律不建新窗口；HTTP(S) 目标交系统浏览器。
      const parsed = parseHttpUrl(url)
      if (parsed) {
        void shell.openExternal(parsed.toString()).catch(() => undefined)
      } else {
        logger?.warn('window.open blocked', { url })
      }
      return { action: 'deny' }
    })
    contents.on('will-attach-webview', (event) => {
      event.preventDefault()
      logger?.warn('webview attach denied')
    })
    contents.on('render-process-gone', (_event, details) => {
      logger?.error('renderer process gone', { reason: details.reason, exitCode: details.exitCode })
      if (mainWindow && !mainWindow.isDestroyed()) {
        void dialog
          .showMessageBox(mainWindow, {
            type: 'error',
            buttons: ['重新加载', '退出'],
            defaultId: 0,
            cancelId: 1,
            message: '界面进程异常退出',
            detail: `原因：${details.reason}`
          })
          .then((choice) => {
            if (choice.response === 0 && mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.reload()
            else app.quit()
          })
      }
    })
  })
}

function registerIpcHandlers(): void {
  const authorized = (event: Electron.IpcMainInvokeEvent): boolean =>
    Boolean(mainWindow) && !mainWindow!.isDestroyed() && event.sender.id === mainWindow!.webContents.id
      && event.senderFrame === mainWindow!.webContents.mainFrame

  const guard = (event: Electron.IpcMainInvokeEvent): void => {
    if (!authorized(event)) {
      logger?.warn('unauthorized ipc sender', { senderId: event.sender.id })
      throw new Error('Unauthorized IPC sender')
    }
  }

  const workspaceFiles = new WorkspaceFiles(path.join(app.getPath('userData'), 'workspace-folders.json'))
  const host = new LspHost()
  lspHost = host
  ipcMain.handle(IPC.lspOpen, async (event, root, relativePath, text) => {
    guard(event)
    return host.openDocument(await validateDiagnosticsRoot(root), String(relativePath), String(text))
  })
  ipcMain.handle(IPC.lspChange, async (event, root, relativePath, text) => {
    guard(event)
    return host.changeDocument(await validateDiagnosticsRoot(root), String(relativePath), String(text))
  })
  ipcMain.handle(IPC.lspClose, async (event, root, relativePath) => {
    guard(event)
    return host.closeDocument(await validateDiagnosticsRoot(root), String(relativePath))
  })
  ipcMain.handle(IPC.lspDiagnostics, async (event, root) => {
    guard(event)
    return host.diagnostics(await validateDiagnosticsRoot(root))
  })
  ipcMain.handle(IPC.lspDefinition, async (event, root, relativePath, line, column) => {
    guard(event)
    return host.definition(await validateDiagnosticsRoot(root), String(relativePath), Number(line), Number(column))
  })
  ipcMain.handle(IPC.terminalProfiles, event => { guard(event); return terminalClient.profiles() })
  ipcMain.handle(IPC.terminalList, event => { guard(event); return terminalClient.list() })
  ipcMain.handle(IPC.terminalCreate, (event, options) => { guard(event); return terminalClient.create(options) })
  ipcMain.handle(IPC.terminalRead, (event, id, after) => { guard(event); return terminalClient.read(id, after) })
  ipcMain.handle(IPC.terminalWrite, (event, id, data) => { guard(event); return terminalClient.write(id, data) })
  ipcMain.handle(IPC.terminalResize, (event, id, cols, rows) => { guard(event); return terminalClient.resize(id, cols, rows) })
  ipcMain.handle(IPC.terminalClose, (event, id) => { guard(event); return terminalClient.close(id) })
  ipcMain.handle(IPC.workspaceChoose, async event => {
    guard(event)
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {title: '打开工作文件夹', properties: ['openDirectory']})
    return result.canceled || !result.filePaths[0] ? null : workspaceFiles.select(result.filePaths[0])
  })
  ipcMain.handle(IPC.workspaceCurrent, event => { guard(event); return workspaceFiles.current() })
  ipcMain.handle(IPC.workspaceList, (event, id, relative) => { guard(event); return workspaceFiles.list(id, relative) })
  ipcMain.handle(IPC.workspaceRead, (event, id, relative) => { guard(event); return workspaceFiles.read(id, relative) })
  ipcMain.handle(IPC.workspaceSave, (event, id, relative, content, version) => { guard(event); return workspaceFiles.save(id, relative, content, version) })
  ipcMain.handle(IPC.workspaceSearch, async (event, root, options) => {
    guard(event)
    const resolved = await validateSearchRoot(root)
    return searchWorkspace(resolved, normalizeSearchOptions(options))
  })
  ipcMain.handle(IPC.workspaceDiagnostics, async (event, root) => {
    guard(event)
    return runDiagnostics(await validateDiagnosticsRoot(root))
  })
  ipcMain.handle(IPC.workspaceGitStatus, async (event, root) => {
    guard(event)
    return gitStatus(await validateGitRoot(root))
  })
  ipcMain.handle(IPC.workspaceGitDiff, async (event, root, filePath, staged) => {
    guard(event)
    return gitDiff(await validateGitRoot(root), String(filePath), staged === true)
  })
  ipcMain.handle(IPC.workspaceGitShow, async (event, root, filePath, ref) => {
    guard(event)
    return gitShow(await validateGitRoot(root), String(filePath), typeof ref === 'string' ? ref : 'HEAD')
  })
  ipcMain.handle(IPC.workspaceGitStage, async (event, root, paths) => {
    guard(event)
    return gitStage(await validateGitRoot(root), Array.isArray(paths) ? paths.map(String) : [])
  })
  ipcMain.handle(IPC.workspaceGitUnstage, async (event, root, paths) => {
    guard(event)
    return gitUnstage(await validateGitRoot(root), Array.isArray(paths) ? paths.map(String) : [])
  })
  ipcMain.handle(IPC.workspaceGitCommit, async (event, root, message) => {
    guard(event)
    return gitCommit(await validateGitRoot(root), String(message))
  })

  ipcMain.handle(IPC.windowMinimize, (event) => {
    guard(event)
    mainWindow?.minimize()
    return null
  })
  ipcMain.handle(IPC.windowToggleMaximize, (event) => {
    guard(event)
    if (!mainWindow) return null
    if (mainWindow.isMaximized()) mainWindow.unmaximize()
    else mainWindow.maximize()
    return null
  })
  ipcMain.handle(IPC.windowClose, (event) => {
    guard(event)
    mainWindow?.close()
    return null
  })
  ipcMain.handle(IPC.windowIsMaximized, (event) => {
    guard(event)
    return mainWindow?.isMaximized() ?? false
  })
  ipcMain.handle(IPC.windowIsFullscreen, (event) => {
    guard(event)
    return mainWindow?.isFullScreen() ?? false
  })
  ipcMain.handle(IPC.windowSetFullscreen, (event, raw) => {
    guard(event)
    const fullscreen = parseBoolean(raw)
    if (fullscreen === null) throw new Error('Invalid fullscreen flag')
    mainWindow?.setFullScreen(fullscreen)
    return null
  })
  ipcMain.handle(IPC.dialogOpenFile, async (event, raw) => {
    guard(event)
    const payload = (raw ?? {}) as { extensions?: unknown }
    const extensions = parseExtensions(payload.extensions)
    if (extensions === null) throw new Error('Invalid file filters')
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      filters: extensions && extensions.length > 0 ? [{ name: 'Supported files', extensions }] : undefined
    })
    const filePath = result.canceled ? undefined : result.filePaths[0]
    if (!filePath) return null
    return { name: path.basename(filePath), path: filePath }
  })
  ipcMain.handle(IPC.dialogOpenDirectory, async (event) => {
    guard(event)
    if (!mainWindow) return null
    // 只返回候选路径；是否允许访问由后端 Host Grant 权威决定。
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] })
    if (result.canceled) return null
    return result.filePaths[0] ?? null
  })
  ipcMain.handle(IPC.notify, (event, raw) => {
    guard(event)
    const payload = (raw ?? {}) as { title?: unknown; body?: unknown }
    const title = parseBoundedText(payload.title, 200)
    if (!title) throw new Error('Invalid notification title')
    const body = parseBoundedText(payload.body, 2000)
    new Notification({ title, body: body ?? undefined }).show()
    return null
  })
  ipcMain.handle(IPC.openExternal, async (event, raw) => {
    guard(event)
    const parsed = parseHttpUrl(raw)
    if (!parsed) throw new Error('Only HTTP(S) external URLs are allowed')
    await shell.openExternal(parsed.toString())
    return null
  })
  ipcMain.handle(IPC.appInfo, (event) => {
    guard(event)
    return { version: app.getVersion(), platform: process.platform, packaged: app.isPackaged }
  })

  // 同步返回后端 origin：Preload 在模块求值阶段要把它作为常量暴露给渲染层。
  ipcMain.on(IPC.appApiOrigin, (event) => {
    const senderOk = Boolean(mainWindow) && !mainWindow!.isDestroyed()
      && event.sender.id === mainWindow!.webContents.id
      && event.senderFrame === mainWindow!.webContents.mainFrame
    event.returnValue = senderOk ? apiOrigin : ''
  })

  // 虚拟伙伴：状态快照只影响托盘 tooltip 与菜单勾选，不参与任何执行决策。
  ipcMain.handle(IPC.companionState, (event, raw) => {
    guard(event)
    const snapshot = parseCompanionSnapshot(raw)
    if (!snapshot) throw new Error('Invalid companion state')
    companionSnapshot = snapshot
    refreshCompanionTray()
    return null
  })
  // 窗口正被用户看着时不弹系统通知；免打扰由 Main 依据已校验的快照兜底。
  ipcMain.handle(IPC.companionNotify, (event, raw) => {
    guard(event)
    const notice = parseNotification(raw)
    if (!notice) throw new Error('Invalid companion notification')
    const alive = Boolean(mainWindow && !mainWindow.isDestroyed())
    const focused = alive && mainWindow!.isFocused()
    const minimized = alive && mainWindow!.isMinimized()
    if (!shouldDeliverNotification(companionSnapshot, focused, minimized)) return null
    new Notification({ title: notice.title, body: notice.body }).show()
    return null
  })
}

function wireGlobalErrorHandling(): void {
  process.on('uncaughtException', (error) => {
    logger?.error('uncaught exception', { name: error.name, message: error.message, stack: error.stack })
    dialog.showErrorBox('知弈 AgentOS 主进程异常', `${error.name}: ${error.message}\n\n详情见应用日志。`)
    app.exit(1)
  })
  process.on('unhandledRejection', (reason) => {
    logger?.error('unhandled rejection', { reason: String(reason) })
  })
}

const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
  // 同一 userData 目录已有实例：明确写入 stderr，避免上游只看到“进程已退出”。
  console.error(`[electron] another instance already owns userData ${app.getPath('userData')}; exiting`)
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  app.whenReady().then(() => {
    logger = createFileLogger(path.join(app.getPath('userData'), 'logs'))
    logger.info('main starting', {
      appVersion: app.getVersion(),
      electron: process.versions.electron,
      chromium: process.versions.chrome,
      platform: process.platform,
      packaged: app.isPackaged,
      devServer: devServerUrl ?? null,
      apiOrigin
    })
    wireGlobalErrorHandling()

    // 无边框窗口的标题栏菜单没有存在意义；默认加速键一并移除，
    // 窗口级 F11/F12 由 before-input-event 重新接管，Ctrl+R 交渲染进程（终端焦点让位）。
    Menu.setApplicationMenu(null)
    hardenSession(session.defaultSession, logger)
    wireWebContentsGuards()

    if (!devServerUrl) {
      handleAppProtocol(rendererDir(), apiOrigin)
    }
    registerIpcHandlers()
    createWindow()
    // 托盘在主窗口就绪后创建：图标资源随 dist/icons 一起进 asar，缺失时静默降级。
    createCompanionTray()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })

  let terminalCleanupStarted = false
  app.on('before-quit', event => {
    if (terminalCleanupStarted) return
    terminalCleanupStarted = true
    event.preventDefault()
    lspHost?.dispose()
    lspHost = null
    companionTray?.destroy()
    companionTray = null
    void terminalClient.closeAll().catch(() => undefined).finally(() => app.quit())
  })
  app.on('window-all-closed', () => {
    app.quit()
  })
}
