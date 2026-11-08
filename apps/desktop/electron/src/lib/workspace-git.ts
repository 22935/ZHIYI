/**
 * 工作区 Git 服务：读取状态/差异，以及暂存、取消暂存和提交。
 * 只通过参数数组调用 git（不使用 shell），所有外部命令都有超时与输出上限。
 */
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { promises as fs } from 'node:fs'
import * as path from 'node:path'

export interface GitFileChange {
  /** 相对仓库根目录的路径，统一用 / 分隔 */
  path: string
  /** 暂存区状态字母，如 'M'、'A'、'D'、'?'、' ' */
  index: string
  /** 工作区状态字母 */
  worktree: string
}

export interface GitStatusResult {
  branch: string
  ahead: number
  behind: number
  files: GitFileChange[]
}

const GIT_TIMEOUT_MS = 10_000
const MAX_OUTPUT_BYTES = 4 * 1024 * 1024
const MAX_ERROR_DETAIL = 2000

interface GitCommandResult {
  code: number | null
  stdout: string
  stderr: string
}

const clipDetail = (text: string): string => (
  text.length > MAX_ERROR_DETAIL ? `${text.slice(0, MAX_ERROR_DETAIL)}…` : text
)

const assertRepoRoot = (root: string): void => {
  if (typeof root !== 'string' || root.length === 0) throw new Error('Git 仓库路径不能为空')
  if (root.includes('\0')) throw new Error('Git 仓库路径不能包含空字符')
  if (!path.isAbsolute(root)) throw new Error('Git 仓库需要绝对路径')
}

const assertFilePath = (filePath: string): string => {
  if (typeof filePath !== 'string' || filePath.length === 0) throw new Error('Git 文件路径不能为空')
  if (filePath.includes('\0')) throw new Error('Git 文件路径不能包含空字符')
  return filePath
}

const assertPaths = (paths: string[]): string[] => {
  if (!Array.isArray(paths) || paths.length === 0) throw new Error('Git 路径列表不能为空')
  return paths.map(entry => {
    if (typeof entry !== 'string' || entry.length === 0) throw new Error('Git 路径不能为空')
    if (entry.includes('\0')) throw new Error('Git 路径不能包含空字符')
    return entry
  })
}

/** 参数数组交给 spawn，不经过 shell，因此路径不需要拼引号或做转义。 */
const runGit = (root: string, args: string[]): Promise<GitCommandResult> => new Promise((resolve, reject) => {
  let child: ChildProcessWithoutNullStreams
  try {
    child = spawn('git', args, { cwd: root, windowsHide: true })
  } catch {
    reject(new Error('git 未安装或不可用'))
    return
  }

  let settled = false
  const stdout: Buffer[] = []
  const stderr: Buffer[] = []
  let stdoutBytes = 0
  let stderrBytes = 0

  const timer = setTimeout(() => {
    if (settled) return
    settled = true
    child.kill()
    reject(new Error('git 命令超时（10 秒）'))
  }, GIT_TIMEOUT_MS)

  const fail = (message: string): void => {
    if (settled) return
    settled = true
    clearTimeout(timer)
    child.kill()
    reject(new Error(message))
  }

  const collect = (chunks: Buffer[], chunk: Buffer, current: number, other: number): number => {
    if (settled) return current
    const next = current + chunk.length
    if (next + other > MAX_OUTPUT_BYTES) {
      fail('git 输出超过 4 MB 上限')
      return current
    }
    chunks.push(chunk)
    return next
  }

  child.stdout.on('data', (chunk: Buffer) => {
    stdoutBytes = collect(stdout, chunk, stdoutBytes, stderrBytes)
  })
  child.stderr.on('data', (chunk: Buffer) => {
    stderrBytes = collect(stderr, chunk, stderrBytes, stdoutBytes)
  })
  child.on('error', (error: NodeJS.ErrnoException) => {
    fail(error.code === 'ENOENT' ? 'git 未安装或不可用' : `git 命令执行失败：${error.message}`)
  })
  child.on('close', code => {
    if (settled) return
    settled = true
    clearTimeout(timer)
    resolve({
      code,
      stdout: Buffer.concat(stdout, stdoutBytes).toString('utf8'),
      stderr: Buffer.concat(stderr, stderrBytes).toString('utf8')
    })
  })
})

const combinedOutput = (result: GitCommandResult): string => (
  [result.stdout.trim(), result.stderr.trim()].filter(Boolean).join('\n')
)

const commandFailure = (root: string, args: string[], result: GitCommandResult): Error => {
  const detail = [result.stderr.trim(), result.stdout.trim()].filter(Boolean).join('\n')
  if (/not a git repo(?:sitory)?|不是\s*git\s*仓库|不是\s*一个\s*git\s*仓库/i.test(detail)) {
    return new Error(`不是 Git 仓库：${root}`)
  }
  return new Error(
    `git ${args[0] || '命令'} 执行失败（退出码 ${result.code ?? '未知'}）：${clipDetail(detail || '无输出')}`
  )
}

const runGitChecked = async (root: string, args: string[]): Promise<GitCommandResult> => {
  const result = await runGit(root, args)
  if (result.code !== 0) throw commandFailure(root, args, result)
  return result
}

/** git 输出在各平台都用 / 分隔；Windows 上顺带兜底反斜杠。 */
const normalizeGitPath = (value: string): string => (
  path.sep === '\\' ? value.replace(/\\/g, '/') : value
)

const parseBranchHeader = (line: string): Pick<GitStatusResult, 'branch' | 'ahead' | 'behind'> => {
  let header = line.replace(/^##\s*/, '').trim()
  const tracking = /\[([^\]]*)\]\s*$/.exec(header)
  const trackingText = tracking?.[1] ?? ''
  if (tracking) header = header.slice(0, tracking.index).trim()

  let branch: string
  if (header.startsWith('No commits yet on ')) {
    branch = header.slice('No commits yet on '.length).trim() || 'HEAD'
  } else if (header.startsWith('HEAD (no branch)')) {
    branch = 'HEAD'
  } else {
    branch = header.split('...')[0]?.trim() || 'HEAD'
  }

  return {
    branch,
    ahead: Number(/\bahead\s+(\d+)/i.exec(trackingText)?.[1] ?? 0) || 0,
    behind: Number(/\bbehind\s+(\d+)/i.exec(trackingText)?.[1] ?? 0) || 0
  }
}

/**
 * 解析 `git status --porcelain=v1 -z --branch`。
 * 分支头也以 NUL 结尾；重命名/复制条目是 `XY new\0old\0`，需要跳过紧随其后的旧路径。
 */
const parseGitStatus = (output: string): GitStatusResult => {
  const result: GitStatusResult = { branch: 'HEAD', ahead: 0, behind: 0, files: [] }
  const records = output.split('\0')

  for (let cursor = 0; cursor < records.length; cursor += 1) {
    // 兼容个别输出在记录前带换行的情况；正常 -z 输出不会出现。
    const record = records[cursor].replace(/^[\r\n]+/, '')
    if (!record) continue
    if (record.startsWith('## ')) {
      Object.assign(result, parseBranchHeader(record))
      continue
    }
    if (record.length < 3) continue

    const index = record[0]
    const worktree = record[1]
    const filePath = record.slice(3)
    if (!filePath) continue
    result.files.push({ path: normalizeGitPath(filePath), index, worktree })

    if ('RC'.includes(index) || 'RC'.includes(worktree)) cursor += 1
  }

  return result
}

export async function gitStatus(root: string): Promise<GitStatusResult> {
  assertRepoRoot(root)
  const result = await runGitChecked(root, ['status', '--porcelain=v1', '-z', '--branch'])
  return parseGitStatus(result.stdout)
}

export async function gitDiff(root: string, filePath: string, staged: boolean): Promise<string> {
  assertRepoRoot(root)
  const safePath = assertFilePath(filePath)
  const args = ['diff', '--no-color']
  if (staged) args.push('--cached')
  args.push('--', safePath)
  const result = await runGitChecked(root, args)
  return result.stdout
}

/**
 * 读取文件在某个提交里的内容，用于行内 diff 的“原始版本”。
 * 文件不在该提交中（新增/未跟踪）时返回 null，让调用方按空基线渲染。
 */
export async function gitShow(root: string, filePath: string, ref = 'HEAD'): Promise<string | null> {
  assertRepoRoot(root)
  const safePath = assertFilePath(filePath)
  if (typeof ref !== 'string' || ref.trim().length === 0) throw new Error('Git 引用不能为空')
  if (ref.includes('\0')) throw new Error('Git 引用不能包含空字符')

  const result = await runGit(root, ['show', `${ref.trim()}:${safePath}`])
  if (result.code === 0) return result.stdout
  if (/does not exist|not in the working tree|unknown revision|bad revision|invalid object name/i.test(result.stderr)) {
    return null
  }
  throw commandFailure(root, ['show', ref], result)
}

/**
 * 在普通目录初始化 Git 仓库（源代码管理面板「初始化仓库」引导）。
 * 前提就是该目录还不是仓库，因此不做仓库断言；已 init 的目录重复执行
 * 属 git 自身的 reinitialize（幂等，退出码 0），无需特判。
 */
export async function gitInit(root: string): Promise<void> {
  assertRepoRoot(root)
  await runGitChecked(root, ['init'])
}

export async function gitStage(root: string, paths: string[]): Promise<void> {
  assertRepoRoot(root)
  const safePaths = assertPaths(paths)
  await runGitChecked(root, ['add', '--', ...safePaths])
}

export async function gitUnstage(root: string, paths: string[]): Promise<void> {
  assertRepoRoot(root)
  const safePaths = assertPaths(paths)

  try {
    const result = await runGit(root, ['restore', '--staged', '--', ...safePaths])
    if (result.code === 0) return
  } catch {
    // 落到下面的兜底命令；新仓库没有 HEAD 时 restore 可能直接失败。
  }

  try {
    await runGit(root, ['rm', '--cached', '-r', '--quiet', '--', ...safePaths])
  } catch {
    // 兜底也可能失败（例如路径已不在索引中），按约定不向调用方抛错。
  }
}

export async function gitCommit(root: string, message: string): Promise<{ committed: boolean; output: string }> {
  assertRepoRoot(root)
  if (typeof message !== 'string' || message.trim().length === 0) throw new Error('提交信息不能为空')
  if (message.includes('\0')) throw new Error('提交信息不能包含空字符')

  const result = await runGit(root, ['commit', '-m', message])
  const output = combinedOutput(result)
  if (result.code === 0) return { committed: true, output }
  if (/nothing to commit|nothing added to commit|no changes added to commit|working tree clean/i.test(output)) {
    return { committed: false, output }
  }
  throw commandFailure(root, ['commit'], result)
}

/** 校验 Git 根目录：绝对路径、真实目录、不是盘符根。 */
export async function validateGitRoot(input: unknown): Promise<string> {
  if (typeof input !== 'string' || input.length === 0) throw new Error('Git 仓库路径不能为空')
  if (input.includes('\0')) throw new Error('Git 仓库路径不能包含空字符')
  if (!path.isAbsolute(input)) throw new Error('Git 仓库需要绝对路径')

  let root: string
  try {
    root = await fs.realpath(input)
  } catch {
    throw new Error('Git 仓库路径不存在或不可访问')
  }
  const stat = await fs.stat(root)
  if (!stat.isDirectory()) throw new Error('Git 仓库路径不是目录')
  if (path.parse(root).root === root) throw new Error('不能使用整个磁盘作为 Git 仓库')
  return root
}
