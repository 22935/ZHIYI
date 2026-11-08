import { randomUUID } from 'node:crypto'
import { accessSync, lstatSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'

const SAFE_ENV = new Set(['SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
  'USERPROFILE', 'USERNAME', 'USERDOMAIN', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
  'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PSMODULEPATH',
  'ONEDRIVE', 'ONEDRIVECONSUMER', 'ONEDRIVECOMMERCIAL'])

export function shellEnvironment(environment = process.env) {
  return { ...Object.fromEntries(Object.entries(environment).filter(([key]) => SAFE_ENV.has(key.toUpperCase()))),
    TERM: 'xterm-256color', COLORTERM: 'truecolor', TERM_PROGRAM: 'Zhiyi', TERM_PROGRAM_VERSION: '0.1.0' }
}

export function discoverProfiles(environment = process.env) {
  // Windows Store execution aliases can be launchable while stat/existsSync
  // fails with EACCES on their reparse target. Inspect the alias itself.
  const launchable = file => { try { accessSync(file); return !lstatSync(file).isDirectory() } catch { return false } }
  const find = executable => (environment.PATH || environment.Path || '').split(path.delimiter)
    .map(folder => path.join(folder.replace(/^"|"$/g, ''), executable)).find(launchable)
  if (process.platform !== 'win32') {
    return [{ id: 'shell', name: 'Shell', executable: environment.SHELL || '/bin/bash', args: ['-l'] }]
  }
  const git = find('git.exe')
  const storePowerShell = path.join(environment.LOCALAPPDATA || '', 'Microsoft/WindowsApps/Microsoft.PowerShell_8wekyb3d8bbwe/pwsh.exe')
  const candidates = [
    { id: 'pwsh', name: 'PowerShell 7', executable: find('pwsh.exe') || (launchable(storePowerShell) ? storePowerShell : path.join(environment.ProgramFiles || 'C:\\Program Files', 'PowerShell/7/pwsh.exe')), args: ['-NoLogo'] },
    { id: 'powershell', name: 'Windows PowerShell', executable: path.join(environment.SystemRoot || 'C:\\Windows', 'System32/WindowsPowerShell/v1.0/powershell.exe'), args: ['-NoLogo'] },
    { id: 'cmd', name: 'Command Prompt', executable: environment.ComSpec || environment.COMSPEC || 'C:\\Windows\\System32\\cmd.exe', args: ['/d'] },
    { id: 'git-bash', name: 'Git Bash', executable: git ? path.resolve(path.dirname(git), '../bin/bash.exe') : path.join(environment.ProgramFiles || 'C:\\Program Files', 'Git/bin/bash.exe'), args: ['--login', '-i'] }
  ]
  return candidates.filter(profile => launchable(profile.executable))
}

export class TerminalSessions {
  constructor(pty, { defaultCwd, environment = process.env, maxSessions = 12, maxBufferBytes = 1024 * 1024 } = {}) {
    this.pty = pty
    this.environment = shellEnvironment(environment)
    this.profiles = discoverProfiles(environment)
    this.defaultCwd = defaultCwd || environment.USERPROFILE || process.cwd()
    this.maxSessions = maxSessions
    this.maxBufferBytes = maxBufferBytes
    this.sessions = new Map()
  }

  profileViews() { return this.profiles.map(({ id, name }) => ({ id, name })) }
  view(session) {
    const { id, profileId, profileName, cwd, pid, state, exitCode, cols, rows, createdAt } = session
    return { id, profileId, profileName, cwd, pid, state, exitCode, cols, rows, createdAt }
  }
  list(owner) { return [...this.sessions.values()].filter(session => session.owner === owner).map(session => this.view(session)) }
  owned(owner, id) {
    const session = this.sessions.get(id)
    if (!session || session.owner !== owner) throw Object.assign(new Error('Terminal session not found'), { status: 404 })
    return session
  }
  dimensions(cols, rows) {
    if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 2 || cols > 500 || rows < 1 || rows > 200) throw new Error('Invalid terminal dimensions')
    return { cols, rows }
  }
  create(owner, options = {}) {
    if (!options || typeof options !== 'object' || Array.isArray(options)
        || Object.keys(options).some(key => !['profileId', 'cwd', 'cols', 'rows'].includes(key))) throw new Error('Invalid terminal options')
    const { profileId, cwd, cols = 100, rows = 24 } = options
    if (this.sessions.size >= this.maxSessions) throw new Error('Terminal session limit reached; close an unused terminal')
    const profile = profileId ? this.profiles.find(item => item.id === profileId) : this.profiles[0]
    if (!profile) throw new Error('Selected shell is not installed')
    this.dimensions(cols, rows)
    const directory = cwd || this.defaultCwd
    if (typeof directory !== 'string' || directory.includes('\0') || !path.isAbsolute(directory)) throw new Error('An absolute working directory is required')
    const canonical = realpathSync(directory)
    if (!statSync(canonical).isDirectory()) throw new Error('Working directory must be a folder')
    const process = this.pty.spawn(profile.executable, profile.args, { name: 'xterm-256color', cwd: canonical,
      cols, rows, env: this.environment, useConpty: true })
    const session = { id: randomUUID(), owner, profileId: profile.id, profileName: profile.name, cwd: canonical,
      pid: process.pid, state: 'running', exitCode: null, cols, rows, createdAt: new Date().toISOString(),
      process, chunks: [], bytes: 0, sequence: 0 }
    this.sessions.set(session.id, session)
    session.dataListener = process.onData(data => {
      if (Buffer.byteLength(data) > this.maxBufferBytes) data = data.slice(-Math.max(1, Math.floor(this.maxBufferBytes / 4)))
      const chunk = { sequence: ++session.sequence, data }
      session.chunks.push(chunk)
      session.bytes += Buffer.byteLength(data)
      while (session.bytes > this.maxBufferBytes && session.chunks.length > 1) {
        session.bytes -= Buffer.byteLength(session.chunks.shift().data)
      }
    })
    session.exitListener = process.onExit(({ exitCode }) => {
      session.state = 'exited'; session.exitCode = exitCode
    })
    return this.view(session)
  }
  read(owner, id, after = 0) {
    if (!Number.isSafeInteger(after) || after < 0) throw new Error('Invalid output cursor')
    const session = this.owned(owner, id)
    return { session: this.view(session), cursor: session.sequence,
      truncated: session.chunks.length > 0 && after < session.chunks[0].sequence - 1,
      chunks: session.chunks.filter(chunk => chunk.sequence > after) }
  }
  write(owner, id, data) {
    if (typeof data !== 'string' || Buffer.byteLength(data) > 65536) throw new Error('Invalid terminal input')
    const session = this.owned(owner, id)
    if (session.state !== 'running') throw new Error('Terminal has exited; create a new session')
    session.process.write(data)
  }
  resize(owner, id, cols, rows) {
    this.dimensions(cols, rows)
    const session = this.owned(owner, id)
    if (session.state === 'running') session.process.resize(cols, rows)
    Object.assign(session, { cols, rows })
  }
  close(owner, id) {
    const session = this.owned(owner, id)
    session.dataListener.dispose(); session.exitListener.dispose()
    try { if (session.state === 'running') session.process.kill() }
    finally { this.sessions.delete(id) }
  }
  closeOwner(owner) {
    for (const session of [...this.sessions.values()]) if (session.owner === owner) this.close(owner, session.id)
  }
  dispose() { for (const session of [...this.sessions.values()]) this.close(session.owner, session.id) }
}
