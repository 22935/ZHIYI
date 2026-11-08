/**
 * 只读预览提取器：把非 UTF-8 文本与二进制文档转成统一预览载荷。
 * 编辑权威仍在 workspace-files.ts（UTF-8 文本可写）；这里的一切产物都不可写，
 * version 恒为 null（前端凭 null 令牌自动进入只读态）。
 *
 * 安全约束：解析对象是磁盘上不可信文件——只有大小/页数上限，禁网络
 * （pdfjs useWorkerFetch/isEvalSupported），禁 v-html；解析器按需懒加载，
 * 不拖慢主进程冷启动。
 */
export type WorkspacePreviewKind = 'text' | 'extracted' | 'image' | 'unsupported'

export interface WorkspaceFilePayload {
  kind: WorkspacePreviewKind
  content: string
  /** null = 只读；editable UTF-8 文本才有 sha256 令牌 */
  version: string | null
  encoding?: 'utf-8' | 'utf-16le' | 'utf-16be' | 'gb18030'
  mime?: string
  format?: string
  reason?: string
}

export const MAX_TEXT_BYTES = 16 * 1024 * 1024
/** 转换类/图片的源文件上限（docx/pdf 等压缩容器本身偏大）。 */
export const MAX_PREVIEW_SOURCE_BYTES = 32 * 1024 * 1024
/** 提取文本输出上限：超出即截断并附注记，防止把整本书灌进编辑器。 */
export const MAX_EXTRACTED_TEXT_BYTES = 1024 * 1024
export const MAX_PDF_PAGES = 500

export interface DecodedText {
  content: string
  encoding: 'utf-8' | 'utf-16le' | 'utf-16be' | 'gb18030'
}

/** BOM 嗅探 + 严格解码：UTF-16 BOM → NUL 探测 → UTF-8 → GB18030，全部失败返回 null。 */
export function decodeTextBestEffort(bytes: Buffer): DecodedText | null {
  if (bytes.length >= 2 && bytes[0] === 0xFF && bytes[1] === 0xFE) {
    return { content: new TextDecoder('utf-16le').decode(bytes), encoding: 'utf-16le' }
  }
  if (bytes.length >= 2 && bytes[0] === 0xFE && bytes[1] === 0xFF) {
    return { content: new TextDecoder('utf-16be').decode(bytes), encoding: 'utf-16be' }
  }
  // NUL 一票否决（沿用旧编辑器语义）：合法 UTF-8 可以编码 U+0000，
  // 且 GB18030 也能解码 0x00，必须先排除无 BOM 的 UTF-16 与真二进制。
  if (bytes.includes(0)) return null
  try {
    return { content: new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes), encoding: 'utf-8' }
  } catch { /* 继续尝试 GB18030 */ }
  try {
    return { content: new TextDecoder('gb18030').decode(bytes), encoding: 'gb18030' }
  } catch { return null }
}

const IMAGE_SIGNATURES: Array<{ mime: string; test: (bytes: Buffer) => boolean }> = [
  { mime: 'image/png', test: b => b.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) },
  { mime: 'image/jpeg', test: b => b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF },
  { mime: 'image/gif', test: b => b.subarray(0, 4).toString('ascii') === 'GIF8' },
  { mime: 'image/webp', test: b => b.subarray(0, 4).toString('ascii') === 'RIFF' && b.subarray(8, 12).toString('ascii') === 'WEBP' },
  { mime: 'image/bmp', test: b => b.subarray(0, 2).toString('ascii') === 'BM' },
  { mime: 'image/x-icon', test: b => b[0] === 0x00 && b[1] === 0x00 && b[2] === 0x01 && b[3] === 0x00 }
]

/** 图片走魔数判定（扩展名仅作参考），返回可用的 MIME 或 null。 */
export function imageMimeFromBytes(bytes: Buffer, extension: string): string | null {
  for (const signature of IMAGE_SIGNATURES) {
    if (signature.test(bytes)) return signature.mime
  }
  if (extension === 'svg' && bytes.subarray(0, 512).toString('utf8').includes('<svg')) return 'image/svg+xml'
  return null
}

const FORMAT_LABELS: Record<string, string> = {
  exe: 'Windows 可执行程序', dll: 'Windows 动态库', sys: 'Windows 驱动', msi: 'Windows 安装包',
  zip: 'ZIP 压缩包', '7z': '7z 压缩包', rar: 'RAR 压缩包', gz: 'gzip 压缩包', tar: 'tar 归档',
  mp4: '视频文件', avi: '视频文件', mov: '视频文件', mkv: '视频文件',
  mp3: '音频文件', wav: '音频文件', flac: '音频文件',
  db: '数据库文件', sqlite: '数据库文件', sqlite3: '数据库文件',
  doc: '旧版 Word 文档（.doc）', psd: 'Photoshop 源文件'
}

export function buildUnsupported(extension: string, bytes: Buffer): WorkspaceFilePayload {
  const label = FORMAT_LABELS[extension] || '二进制文件'
  return {
    kind: 'unsupported', content: '', version: null, format: extension || undefined,
    reason: `${label}（${(extension || 'bin').toUpperCase()}，${bytes.length} 字节）暂不支持预览`
  }
}

const XML_ENTITIES: Record<string, string> = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" }

function decodeXmlEntities(text: string): string {
  return text
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&(amp|lt|gt|quot|apos);/g, match => XML_ENTITIES[match])
}

async function extractDocx(bytes: Buffer): Promise<string> {
  const mammoth = (await import('mammoth') as { default: { extractRawText(input: { buffer: Buffer }): Promise<{ value: string }> } }).default
  const result = await mammoth.extractRawText({ buffer: bytes })
  return result.value
}

async function extractXlsx(bytes: Buffer): Promise<string> {
  const XLSX = await import('xlsx')
  const workbook = XLSX.read(bytes, { type: 'buffer' })
  const parts: string[] = []
  for (const name of workbook.SheetNames) {
    const csv = XLSX.utils.sheet_to_csv(workbook.Sheets[name], { blankrows: false }).trimEnd()
    parts.push(`## Sheet: ${name}\n${csv}`)
  }
  return parts.join('\n\n')
}

async function extractPptx(bytes: Buffer): Promise<string> {
  const JSZip = (await import('jszip') as { default: { loadAsync(data: Buffer): Promise<{ files: Record<string, { async(type: 'string'): Promise<string> }> }> } }).default
  const zip = await JSZip.loadAsync(bytes)
  const slides = Object.keys(zip.files)
    .filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
    .sort((a, b) => Number(a.match(/slide(\d+)\.xml/)![1]) - Number(b.match(/slide(\d+)\.xml/)![1]))
  const parts: string[] = []
  for (let index = 0; index < slides.length; index += 1) {
    const xml = await zip.files[slides[index]].async('string')
    const runs = [...xml.matchAll(/<a:t>([\s\S]*?)<\/a:t>/g)].map(match => decodeXmlEntities(match[1]))
    parts.push(`## 第 ${index + 1} 页\n${runs.join('\n').trim()}`)
  }
  return parts.join('\n\n')
}

async function extractPdf(bytes: Buffer): Promise<string> {
  // legacy build 适配 Node 主进程；关掉 worker 取值与 eval，确保零网络零动态代码。
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs')
  const doc = await pdfjs.getDocument({ data: new Uint8Array(bytes), useWorkerFetch: false, isEvalSupported: false, disableFontFace: true }).promise
  try {
    const pages = Math.min(doc.numPages, MAX_PDF_PAGES)
    const parts: string[] = []
    for (let n = 1; n <= pages; n += 1) {
      const page = await doc.getPage(n)
      const content = await page.getTextContent()
      let text = ''
      for (const item of content.items) {
        if (typeof item.str !== 'string') continue
        text += item.str
        if (item.hasEOL) text += '\n'
      }
      parts.push(`## 第 ${n} 页\n${text.trim()}`)
    }
    if (doc.numPages > pages) parts.push(`（仅提取前 ${pages} 页，全文共 ${doc.numPages} 页）`)
    return parts.join('\n\n')
  } finally { await doc.destroy() }
}

const EXTRACTORS: Record<string, (bytes: Buffer) => Promise<string>> = {
  docx: extractDocx,
  xlsx: extractXlsx,
  xls: extractXlsx,
  pptx: extractPptx,
  pdf: extractPdf
}

export interface ExtractedPreview {
  content: string
  format: string
  truncated: boolean
}

/** 有转换器且解析成功返回提取文本；无转换器返回 null（由调用方给 unsupported）。 */
export async function extractPreview(extension: string, bytes: Buffer): Promise<ExtractedPreview | null> {
  const extractor = EXTRACTORS[extension]
  if (!extractor) return null
  let content: string
  try { content = await extractor(bytes) } catch { return null }
  let truncated = false
  if (Buffer.byteLength(content, 'utf8') > MAX_EXTRACTED_TEXT_BYTES) {
    // 按 UTF-8 码边界截断，避免把多字节字符切一半。
    content = Buffer.from(content, 'utf8').subarray(0, MAX_EXTRACTED_TEXT_BYTES).toString('utf8') + '\n\n（内容已截断：提取文本超过 1 MiB）'
    truncated = true
  }
  return { content, format: extension, truncated }
}
