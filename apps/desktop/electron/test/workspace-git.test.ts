import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtemp, realpath, rm, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import * as path from 'node:path'
import { test } from 'node:test'
import {
  gitCommit,
  gitDiff,
  gitInit,
  gitShow,
  gitStage,
  gitStatus,
  gitUnstage,
  validateGitRoot
} from '../src/lib/workspace-git.ts'

const gitAvailable = (() => {
  try {
    const probe = spawnSync('git', ['--version'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      windowsHide: true,
      timeout: 5000
    })
    return probe.status === 0
  } catch {
    return false
  }
})()

const skipWithoutGit = (t: { skip: (message?: string) => void }): boolean => {
  if (gitAvailable) return false
  t.skip('当前机器没有可用的 git，跳过 Git 集成测试')
  return true
}

const git = (root: string, args: string[]): string => {
  const result = spawnSync('git', args, {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 15_000
  })
  assert.equal(
    result.status,
    0,
    `git ${args[0]} 失败：${String(result.stderr || result.stdout || '').trim()}`
  )
  return String(result.stdout ?? '')
}

interface GitFixture {
  root: string
  branch: string
}

const createRepo = async (): Promise<GitFixture> => {
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-git-'))
  try {
    git(root, ['init', '--quiet'])
    git(root, ['config', 'user.name', 'Kinlin Test'])
    git(root, ['config', 'user.email', 'kinlin-test@example.com'])
    await writeFile(path.join(root, 'modify.txt'), 'base\nline\n')
    await writeFile(path.join(root, 'delete.txt'), 'remove me\n')
    git(root, ['add', '--', '.'])
    git(root, ['commit', '--quiet', '-m', 'initial'])
    return { root, branch: git(root, ['symbolic-ref', '--short', 'HEAD']).trim() }
  } catch (error) {
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

const createUnbornRepo = async (): Promise<string> => {
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-git-unborn-'))
  try {
    git(root, ['init', '--quiet'])
    git(root, ['config', 'user.name', 'Kinlin Test'])
    git(root, ['config', 'user.email', 'kinlin-test@example.com'])
    return root
  } catch (error) {
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

const applyChanges = async (root: string): Promise<void> => {
  await writeFile(path.join(root, 'modify.txt'), 'base\nchanged\n')
  await unlink(path.join(root, 'delete.txt'))
  await writeFile(path.join(root, 'new.txt'), 'new file\n')
}

test('gitStatus reports branch and worktree changes for modified, deleted and untracked files', async t => {
  if (skipWithoutGit(t)) return
  const { root, branch } = await createRepo()
  try {
    await applyChanges(root)
    const status = await gitStatus(root)
    assert.equal(status.branch, branch)
    assert.equal(status.ahead, 0)
    assert.equal(status.behind, 0)
    assert.equal(status.files.length, 3)

    const changes = new Map(status.files.map(change => [change.path, change]))
    assert.deepEqual(changes.get('modify.txt'), { path: 'modify.txt', index: ' ', worktree: 'M' })
    assert.deepEqual(changes.get('delete.txt'), { path: 'delete.txt', index: ' ', worktree: 'D' })
    assert.deepEqual(changes.get('new.txt'), { path: 'new.txt', index: '?', worktree: '?' })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitDiff and gitStage expose unstaged and staged changes', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    await writeFile(path.join(root, 'modify.txt'), 'base\nchanged\n')

    assert.match(await gitDiff(root, 'modify.txt', false), /^\+.*changed/m)
    assert.equal(await gitDiff(root, 'modify.txt', true), '')

    await gitStage(root, ['modify.txt'])
    assert.match(await gitDiff(root, 'modify.txt', true), /^\+.*changed/m)
    assert.equal(await gitDiff(root, 'modify.txt', false), '')

    const change = (await gitStatus(root)).files.find(file => file.path === 'modify.txt')
    assert.ok(change)
    assert.equal(change.index, 'M')
    assert.notEqual(change.index, ' ')
    assert.equal(change.worktree, ' ')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitShow returns the committed content and null for untracked files', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    assert.equal(await gitShow(root, 'modify.txt'), 'base\nline\n')
    await writeFile(path.join(root, 'modify.txt'), 'base\nchanged\n')
    assert.equal(await gitShow(root, 'modify.txt'), 'base\nline\n')
    assert.equal(await gitShow(root, 'untracked.txt'), null)
    await assert.rejects(() => gitShow(root, 'modify.txt', ''), /引用不能为空/)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitCommit commits staged changes, reports a clean no-op and rejects an empty message', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    await applyChanges(root)
    await gitStage(root, ['modify.txt', 'delete.txt', 'new.txt'])

    const committed = await gitCommit(root, '提交工作区改动')
    assert.equal(committed.committed, true)
    assert.equal(typeof committed.output, 'string')
    assert.deepEqual((await gitStatus(root)).files, [])

    const noop = await gitCommit(root, '再次提交')
    assert.equal(noop.committed, false)
    assert.match(noop.output, /nothing to commit|nothing added to commit|working tree clean/i)

    await assert.rejects(() => gitCommit(root, '   '), /提交信息不能为空/)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitUnstage restores a normal staged change', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    await writeFile(path.join(root, 'modify.txt'), 'base\nchanged\n')
    await gitStage(root, ['modify.txt'])
    assert.equal(await gitDiff(root, 'modify.txt', false), '')

    await gitUnstage(root, ['modify.txt'])
    assert.equal(await gitDiff(root, 'modify.txt', true), '')
    const change = (await gitStatus(root)).files.find(file => file.path === 'modify.txt')
    assert.ok(change)
    assert.equal(change.index, ' ')
    assert.equal(change.worktree, 'M')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitUnstage falls back to rm --cached in a repository without HEAD', async t => {
  if (skipWithoutGit(t)) return
  const root = await createUnbornRepo()
  try {
    await writeFile(path.join(root, 'first.txt'), 'first\n')
    await gitStage(root, ['first.txt'])

    const staged = (await gitStatus(root)).files.find(file => file.path === 'first.txt')
    assert.ok(staged)
    assert.equal(staged.index, 'A')

    await gitUnstage(root, ['first.txt'])
    const unstaged = (await gitStatus(root)).files.find(file => file.path === 'first.txt')
    assert.ok(unstaged)
    assert.equal(unstaged.index, '?')
    assert.equal(unstaged.worktree, '?')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitStatus parses rename records and skips the old path', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    await writeFile(path.join(root, 'old.txt'), 'old\n')
    git(root, ['add', '--', 'old.txt'])
    git(root, ['commit', '--quiet', '-m', 'add old name'])
    git(root, ['mv', 'old.txt', 'renamed.txt'])

    assert.deepEqual((await gitStatus(root)).files, [
      { path: 'renamed.txt', index: 'R', worktree: ' ' }
    ])
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('validateGitRoot rejects relative paths, files and drive roots', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    assert.equal(await validateGitRoot(root), await realpath(root))
    await assert.rejects(() => validateGitRoot('relative/path'), /绝对路径/)
    await assert.rejects(() => validateGitRoot(path.join(root, 'modify.txt')), /不是目录/)
    await assert.rejects(() => validateGitRoot(path.parse(root).root), /整个磁盘/)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitStatus gives a readable error outside a Git repository', async t => {
  if (skipWithoutGit(t)) return
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-git-plain-'))
  try {
    await writeFile(path.join(root, 'readme.txt'), 'plain directory\n')
    await assert.rejects(() => gitStatus(root), /不是 Git 仓库|not a git repository/i)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('gitInit turns a plain directory into a working repository', async t => {
  if (skipWithoutGit(t)) return
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-git-init-'))
  try {
    await writeFile(path.join(root, 'readme.txt'), 'plain directory\n')
    await assert.rejects(() => gitStatus(root), /不是 Git 仓库|not a git repository/i)

    await gitInit(root)

    const status = await gitStatus(root)
    assert.deepEqual(status.files, [{ path: 'readme.txt', index: '?', worktree: '?' }])
    assert.equal(status.ahead, 0)
    assert.equal(status.behind, 0)
    assert.doesNotMatch(status.branch, /^\s*$/)
    // 空仓库可继续走暂存链路（无 HEAD 时 unstage 走 rm --cached 兜底）。
    await gitStage(root, ['readme.txt'])
    assert.equal((await gitStatus(root)).files[0]?.index, 'A')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('path and message arguments containing NUL are rejected', async t => {
  if (skipWithoutGit(t)) return
  const { root } = await createRepo()
  try {
    await assert.rejects(() => gitDiff(root, 'bad\0path', false), /空字符/)
    await assert.rejects(() => gitStage(root, ['bad\0path']), /空字符/)
    await assert.rejects(() => gitUnstage(root, ['bad\0path']), /空字符/)
    await assert.rejects(() => gitCommit(root, 'bad\0message'), /空字符/)
    await assert.rejects(() => validateGitRoot(`${root}\0`), /空字符/)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
