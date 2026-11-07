/**
 * 工作台文档层：一份 URI 对应一份 TextDocument，编辑器、命令、Agent 工具都通过它读写。
 *
 * 设计要点（对齐 VS Code 的 TextModel）：
 * - 文本是权威副本，版本号单调递增，脏状态 = 当前文本 ≠ 上次保存的文本；
 * - 所有修改走 applyEdits（事务化），变更事件带 range，便于增量同步/撤销/协作；
 * - 读写由 DocumentSource 注入：桌面走 Electron 桥，Web 走 HTTP，测试走假实现。
 */
import { getElectronBridge } from '@/platform/electron/bridge'
import { agentosApi, type WorkspaceFileOpenRequest } from '@/services/api/agentos'

export interface Position {
  /** 1 基行号 */
  line: number
  /** 1 基列号 */
  column: number
}

export interface TextEdit {
  from: number
  to: number
  insert: string
}

export interface DocumentChange {
  document: TextDocument
  changes: TextEdit[]
  /** 应用修改后的版本号 */
  version: number
  /** 修改来源，编辑器用它避免回灌自己的变更 */
  origin?: unknown
}

export interface LoadedFile {
  content: string
  /** 后端版本令牌；null 表示不支持版本保护保存（只读） */
  version: string | null
}

export interface DocumentSource {
  load: (request: WorkspaceFileOpenRequest, signal?: AbortSignal) => Promise<LoadedFile>
  save: (request: WorkspaceFileOpenRequest, content: string, expectedVersion: string) => Promise<{ version: string | null }>
}

export class DocumentConflictError extends Error {
  constructor(message = '磁盘文件已变化，未覆盖。请复制当前修改，重新读取后再合并。') {
    super(message)
    this.name = 'DocumentConflictError'
  }
}

const lineStartsOf = (text: string): number[] => {
  const starts = [0]
  for (let index = 0; index < text.length; index += 1) {
    if (text.charCodeAt(index) === 10) starts.push(index + 1)
  }
  return starts
}

/** 一份可寻址、可订阅的文本文档。行号与列号对外都是 1 基。 */
export class TextDocument {
  readonly uri: string
  private text: string
  private savedText: string
  private token: string | null
  private currentVersion = 1
  private lineStarts: number[] | null = null
  private readonly listeners = new Set<(event: DocumentChange) => void>()

  constructor(uri: string, content: string, token: string | null = null) {
    this.uri = uri
    this.text = content
    this.savedText = content
    this.token = token
  }

  get version(): number {
    return this.currentVersion
  }

  /** 后端版本令牌；null 时编辑器应只读。 */
  get versionToken(): string | null {
    return this.token
  }

  get dirty(): boolean {
    if (this.text.length !== this.savedText.length) return true
    return this.text !== this.savedText
  }

  get lineCount(): number {
    return this.starts.length
  }

  getText(): string {
    return this.text
  }

  lineAt(line: number): { text: string; from: number; to: number } {
    const starts = this.starts
    const index = Math.min(Math.max(line, 1), starts.length) - 1
    const from = starts[index]
    const to = index + 1 < starts.length ? starts[index + 1] - 1 : this.text.length
    return { text: this.text.slice(from, to), from, to }
  }

  offsetAt(position: Position): number {
    const starts = this.starts
    const line = Math.min(Math.max(position.line, 1), starts.length)
    const lineStart = starts[line - 1]
    const lineEnd = line < starts.length ? starts[line] - 1 : this.text.length
    return Math.min(lineStart + Math.max(position.column - 1, 0), lineEnd)
  }

  positionAt(offset: number): Position {
    const starts = this.starts
    const target = Math.min(Math.max(offset, 0), this.text.length)
    let low = 0
    let high = starts.length - 1
    while (low < high) {
      const mid = (low + high + 1) >> 1
      if (starts[mid] <= target) low = mid
      else high = mid - 1
    }
    return { line: low + 1, column: target - starts[low] + 1 }
  }

  /** 应用一组互不重叠的修改；返回 false 表示没有任何实际变化。 */
  applyEdits(edits: readonly TextEdit[], origin?: unknown): boolean {
    if (!edits.length) return false
    const sorted = [...edits]
      .filter(edit => edit.from !== edit.to || edit.insert.length > 0)
      .sort((left, right) => left.from - right.from || left.to - right.to)
    if (!sorted.length) return false
    let result = ''
    let cursor = 0
    for (const edit of sorted) {
      if (edit.from < cursor) continue // 重叠修改直接丢弃，保持文本一致
      result += this.text.slice(cursor, edit.from) + edit.insert
      cursor = edit.to
    }
    result += this.text.slice(cursor)
    if (result === this.text) return false
    this.text = result
    this.currentVersion += 1
    this.lineStarts = null
    this.emit({ document: this, changes: sorted, version: this.currentVersion, origin })
    return true
  }

  /** 保存成功后记录新的基线：版本令牌与文本一起更新，脏状态随之为 false。 */
  markSaved(token: string | null, savedText = this.text): void {
    this.token = token
    this.savedText = savedText
  }

  /** 重新读取磁盘内容：视为一次外部加载，版本号继续递增使旧缓存失效。 */
  reset(content: string, token: string | null): void {
    this.text = content
    this.savedText = content
    this.token = token
    this.currentVersion += 1
    this.lineStarts = null
  }

  onDidChange(listener: (event: DocumentChange) => void): () => void {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private get starts(): number[] {
    if (!this.lineStarts) this.lineStarts = lineStartsOf(this.text)
    return this.lineStarts
  }

  private emit(event: DocumentChange): void {
    for (const listener of [...this.listeners]) listener(event)
  }
}

/** 默认数据源：桌面优先走 Electron 桥，其余走 AgentOS HTTP。 */
export const createPlatformDocumentSource = (): DocumentSource => ({
  async load(request, signal) {
    const native = getElectronBridge()?.workspace
    const file = request.desktopWorkspaceId && native
      ? await native.read(request.desktopWorkspaceId, request.relativePath)
      : await agentosApi.readWorkspaceFile(request.missionId, request.relativePath, { signal })
    return { content: file.content, version: file.version || null }
  },
  async save(request, content, expectedVersion) {
    const native = getElectronBridge()?.workspace
    const result = request.desktopWorkspaceId && native
      ? await native.save(request.desktopWorkspaceId, request.relativePath, content, expectedVersion)
      : await agentosApi.saveWorkspaceFile(request.missionId, {
          path: request.relativePath,
          content,
          expectedVersion,
          operationId: operationId()
        })
    return { version: result.version || null }
  }
})

const operationId = (): string => {
  const uuid = (globalThis.crypto as Crypto | undefined)?.randomUUID
  if (typeof uuid === 'function') return uuid.call(globalThis.crypto)
  return `op-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const documentKey = (request: WorkspaceFileOpenRequest): string => (
  `${request.desktopWorkspaceId || request.missionId}:${request.relativePath}`
)

export class WorkspaceDocumentService {
  private readonly documents = new Map<string, TextDocument>()
  private readonly requests = new Map<string, WorkspaceFileOpenRequest>()

  constructor(private readonly source: DocumentSource = createPlatformDocumentSource()) {}

  key(request: WorkspaceFileOpenRequest): string {
    return documentKey(request)
  }

  get(uri: string): TextDocument | undefined {
    return this.documents.get(uri)
  }

  /** 打开文档：已存在直接复用（保留编辑状态），否则从数据源读取。 */
  async open(request: WorkspaceFileOpenRequest, signal?: AbortSignal): Promise<TextDocument> {
    const uri = documentKey(request)
    this.requests.set(uri, request)
    const existing = this.documents.get(uri)
    if (existing) return existing
    const file = await this.source.load(request, signal)
    const document = new TextDocument(uri, file.content, file.version)
    this.documents.set(uri, document)
    return document
  }

  /** 重新读取：丢弃本地修改并刷新令牌，保留文档实例让订阅者继续有效。 */
  async reload(request: WorkspaceFileOpenRequest, signal?: AbortSignal): Promise<TextDocument> {
    const uri = documentKey(request)
    this.requests.set(uri, request)
    const file = await this.source.load(request, signal)
    const existing = this.documents.get(uri)
    if (existing) {
      existing.reset(file.content, file.version)
      return existing
    }
    const document = new TextDocument(uri, file.content, file.version)
    this.documents.set(uri, document)
    return document
  }

  /** 保存当前文本；没有版本令牌时抛错（只读文件不允许保存）。 */
  async save(document: TextDocument): Promise<void> {
    const request = this.requests.get(document.uri)
    if (!request) throw new Error('文档没有对应的文件请求，无法保存')
    const expectedVersion = document.versionToken
    if (!expectedVersion) throw new Error('当前文件不支持版本保护保存')
    try {
      const result = await this.source.save(request, document.getText(), expectedVersion)
      document.markSaved(result.version)
    } catch (cause: any) {
      if (isConflict(cause)) throw new DocumentConflictError()
      throw cause
    }
  }

  close(uri: string): void {
    this.documents.delete(uri)
    this.requests.delete(uri)
  }

  /** 测试与本机工作区重置时清空全部缓存。 */
  reset(): void {
    this.documents.clear()
    this.requests.clear()
  }
}

const isConflict = (cause: any): boolean => (
  cause?.response?.status === 409
  || String(cause?.message || '').includes('FILE_CONFLICT')
)

export const workspaceDocuments = new WorkspaceDocumentService()
