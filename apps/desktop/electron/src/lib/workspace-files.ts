/** Human-operated editor files. This is not an Agent execution backend. */
import { createHash, randomUUID } from 'node:crypto'
import { promises as fs } from 'node:fs'
import * as path from 'node:path'
import {
  buildUnsupported, decodeTextBestEffort, extractPreview, imageMimeFromBytes,
  MAX_PREVIEW_SOURCE_BYTES, MAX_TEXT_BYTES, type WorkspaceFilePayload
} from './workspace-preview.ts'

export class WorkspaceFiles {
  private roots = new Map<string, string>()
  private currentId: string | null = null
  private saves = new Map<string, Promise<unknown>>()
  private readonly settingsPath: string
  constructor(settingsPath: string) { this.settingsPath = settingsPath }

  async current() {
    if (!this.currentId) {
      try {
        const saved = JSON.parse(await fs.readFile(this.settingsPath, 'utf8'))
        if (Array.isArray(saved.roots)) {
          for (const entry of saved.roots) if (typeof entry.id === 'string' && typeof entry.root === 'string') this.roots.set(entry.id, entry.root)
          if (this.roots.has(saved.currentId)) this.currentId = saved.currentId
        }
      } catch { /* First use or unavailable previous folder: the picker remains available. */ }
    }
    return this.currentId ? { id: this.currentId, root: this.roots.get(this.currentId)! } : null
  }

  /** Only Main's successful native folder dialog may call this. */
  async select(directory: string) {
    const root = await fs.realpath(directory)
    if (!(await fs.stat(root)).isDirectory()) throw new Error('请选择文件夹')
    const id = [...this.roots].find(([, value]) => value === root)?.[0] || randomUUID()
    this.roots.set(id, root); this.currentId = id
    await fs.writeFile(this.settingsPath, JSON.stringify({ currentId: id, roots: [...this.roots].map(([id, root]) => ({ id, root })) }), 'utf8')
    return { id, root }
  }

  private async resolve(id: unknown, relative: unknown) {
    await this.current()
    if (typeof id !== 'string' || !this.roots.has(id) || typeof relative !== 'string' || relative.includes('\0') || path.isAbsolute(relative)) throw new Error('请先打开文件夹')
    const root = await fs.realpath(this.roots.get(id)!)
    const target = await fs.realpath(path.resolve(root, relative))
    const offset = path.relative(root, target)
    if (offset === '..' || offset.startsWith('..' + path.sep) || path.isAbsolute(offset)) throw new Error('文件位于所选文件夹之外，请直接打开其所在文件夹')
    return { root, target }
  }

  async list(id: unknown, relative: unknown) {
    const {root, target} = await this.resolve(id, relative)
    const entries = await fs.readdir(target, {withFileTypes: true})
    return { workspaceRoot: root, path: relative as string, entries: entries.filter(entry => entry.isFile() || entry.isDirectory()).map(entry => ({
      name: entry.name, path: path.relative(root, path.join(target, entry.name)).split(path.sep).join('/'), type: entry.isDirectory() ? 'directory' as const : 'file' as const
    })) }
  }

  /** 按字节计算的磁盘版本（不解码）：保存冲突检测用，语义与旧 snapshot 一致。 */
  private async versionOf(target: string) {
    const stat = await fs.stat(target)
    if (!stat.isFile()) throw new Error('所选路径不是文件')
    const bytes = await fs.readFile(target)
    return createHash('sha256').update(bytes).digest('hex')
  }

  /**
   * 统一读取载荷：UTF-8 文本可编辑（sha256 版本），其余一律只读预览。
   * 大小口径：文本 >16 MiB 转 只读；任何源文件 >32 MiB 直接拒绝。
   */
  private async readPayload(target: string): Promise<WorkspaceFilePayload> {
    const stat = await fs.stat(target)
    if (!stat.isFile()) throw new Error('所选路径不是文件')
    if (stat.size > MAX_PREVIEW_SOURCE_BYTES) throw new Error(`文件超过 ${MAX_PREVIEW_SOURCE_BYTES / 1024 / 1024} MiB，暂不支持读取`)
    const bytes = await fs.readFile(target)
    const extension = path.extname(target).toLowerCase().replace(/^\./, '')

    const imageMime = imageMimeFromBytes(bytes, extension)
    if (imageMime) {
      return { kind: 'image', content: `data:${imageMime};base64,${bytes.toString('base64')}`, version: null, mime: imageMime, format: extension || undefined }
    }

    // 已知文档格式按扩展名优先走提取器：纯 ASCII 的 PDF 等也能通过 UTF-8 探测，
    // 若先做文本解码会把 PDF 语法当正文展示；提取失败再回落文本路径。
    const extracted = await extractPreview(extension, bytes)
    if (extracted) {
      return { kind: 'extracted', content: extracted.content, version: null, format: extracted.format, ...(extracted.truncated ? { reason: '内容已截断：提取文本超过 1 MiB' } : {}) }
    }

    const decoded = decodeTextBestEffort(bytes)
    if (decoded) {
      const editable = decoded.encoding === 'utf-8' && bytes.length <= MAX_TEXT_BYTES
      return {
        kind: 'text', content: decoded.content,
        version: editable ? createHash('sha256').update(bytes).digest('hex') : null,
        encoding: decoded.encoding,
        ...(editable ? {} : { reason: decoded.encoding === 'utf-8' ? '文件超过 16 MiB，只读预览' : `以 ${decoded.encoding} 编码读取，只读预览` })
      }
    }

    return buildUnsupported(extension, bytes)
  }

  async read(id: unknown, relative: unknown) {
    const {root, target} = await this.resolve(id, relative)
    return {workspaceRoot: root, path: relative as string, ...await this.readPayload(target)}
  }

  async save(id: unknown, relative: unknown, content: unknown, expectedVersion: unknown) {
    if (typeof content !== 'string' || content.includes('\0') || Buffer.byteLength(content, 'utf8') > MAX_TEXT_BYTES || typeof expectedVersion !== 'string') throw new Error('无效的文本保存请求')
    const {target} = await this.resolve(id, relative)
    const previous = this.saves.get(target) || Promise.resolve()
    const pending = previous.catch(() => undefined).then(async () => {
      // 只允许把文本写回 UTF-8 文本文件：目标一旦含 NUL 或非严格 UTF-8 即拒绝，
      // 防止把编辑器内容覆盖到二进制文件上。
      const before = await fs.readFile(target)
      if (before.includes(0)) throw new Error('仅支持保存 UTF-8 文本文件')
      try { new TextDecoder('utf-8', {fatal: true}).decode(before) } catch { throw new Error('仅支持保存 UTF-8 文本文件') }
      if (createHash('sha256').update(before).digest('hex') !== expectedVersion) throw new Error('FILE_CONFLICT: 磁盘文件已变化，请重新读取后合并')
      const temporary = path.join(path.dirname(target), `.zhiyi-save-${randomUUID()}.tmp`)
      try {
        await fs.writeFile(temporary, content, {encoding: 'utf8', flag: 'wx'})
        if ((await this.versionOf(target)) !== expectedVersion) throw new Error('FILE_CONFLICT: 磁盘文件已变化')
        await fs.rename(temporary, target)
      } finally { await fs.unlink(temporary).catch(() => undefined) }
      return {path: relative as string, version: createHash('sha256').update(content, 'utf8').digest('hex')}
    })
    this.saves.set(target, pending)
    try { return await pending }
    finally { if (this.saves.get(target) === pending) this.saves.delete(target) }
  }
}
