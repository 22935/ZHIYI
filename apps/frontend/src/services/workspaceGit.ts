import { getElectronBridge } from '@/platform/electron/bridge'

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

/**
 * Git 操作只走桌面宿主（本地仓库）。所有方法在 Web 构建下都会明确失败，
 * 由调用方展示「仅桌面端可用」。
 */
const bridge = () => {
  const git = getElectronBridge()?.workspace
  if (!git?.gitStatus) throw new Error('Git 仅在桌面端可用')
  return git
}

export const gitStatus = (root: string): Promise<GitStatusResult> => bridge().gitStatus!(root)
export const gitDiff = (root: string, path: string, staged: boolean): Promise<string> => bridge().gitDiff!(root, path, staged)
export const gitShow = (root: string, path: string, ref = 'HEAD'): Promise<string | null> => bridge().gitShow!(root, path, ref)
export const gitStage = (root: string, paths: string[]): Promise<void> => bridge().gitStage!(root, paths)
export const gitUnstage = (root: string, paths: string[]): Promise<void> => bridge().gitUnstage!(root, paths)
export const gitCommit = (root: string, message: string): Promise<{ committed: boolean; output: string }> => bridge().gitCommit!(root, message)
export const gitInit = (root: string): Promise<void> => {
  const git = bridge()
  if (!git.gitInit) throw new Error('桌面端版本过旧，无法初始化仓库')
  return git.gitInit(root)
}

/**
 * 主进程把「目录不是 Git 仓库」统一包装成 `不是 Git 仓库：<路径>`（跨 IPC 只保留
 * message），据此让源代码管理面板切换到初始化引导而非红字报错；英文报错留正则兜底。
 */
export const isNotRepositoryError = (cause: unknown): boolean => {
  const message = cause instanceof Error ? cause.message : typeof cause === 'object' && cause !== null
    ? String((cause as { message?: unknown }).message ?? '')
    : String(cause ?? '')
  return message.includes('不是 Git 仓库') || /not a git repo/i.test(message)
}
