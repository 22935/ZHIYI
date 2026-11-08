"""工作区只读预览提取：把非 UTF-8 文本与二进制文档转成统一预览载荷。

与桌面端 apps/desktop/electron/src/lib/workspace-preview.ts 保持同一合同
（kind/content/version=null/encoding/mime/format/reason），编辑器凭同一套
分支渲染。version 恒为 None（只读），可编辑链路仍在 hands 的 versioned
文本读写里。

解析对象是不可信文件：只有大小/页数上限与本地解析库，无网络请求；
解析器全部按需懒加载，不拖慢 agent 启动。
"""
from __future__ import annotations

import base64
import io
from pathlib import PurePosixPath

MAX_PREVIEW_SOURCE_BYTES = 32 * 1024 * 1024
MAX_EXTRACTED_TEXT_BYTES = 1024 * 1024
MAX_PDF_PAGES = 500

_KINDS = ('text', 'extracted', 'image', 'unsupported')


def _payload(kind: str, content: str, **extra) -> dict:
    if kind not in _KINDS:
        raise ValueError(f'unknown preview kind: {kind}')
    return {'kind': kind, 'content': content, **extra}


def decode_text_best_effort(raw: bytes) -> dict | None:
    """BOM 嗅探 + 严格解码：UTF-16 BOM → NUL 探测 → UTF-8 → GB18030。"""
    if len(raw) >= 2 and raw[0] == 0xFF and raw[1] == 0xFE:
        return _payload('text', raw.decode('utf-16-le', 'strict').lstrip('\ufeff'), encoding='utf-16le')
    if len(raw) >= 2 and raw[0] == 0xFE and raw[1] == 0xFF:
        return _payload('text', raw.decode('utf-16-be', 'strict').lstrip('\ufeff'), encoding='utf-16be')
    # NUL 一票否决：合法 UTF-8 可编码 U+0000，GB18030 也能解码 0x00，
    # 必须先排除无 BOM 的 UTF-16 与真二进制。
    if b'\x00' in raw:
        return None
    try:
        return _payload('text', raw.decode('utf-8', 'strict'), encoding='utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return _payload('text', raw.decode('gb18030', 'strict'), encoding='gb18030')
    except UnicodeDecodeError:
        return None


_IMAGE_SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'GIF8', 'image/gif'),
    (b'BM', 'image/bmp'),
    (b'\x00\x00\x01\x00', 'image/x-icon'),
)


def _image_mime(raw: bytes, extension: str) -> str | None:
    for signature, mime in _IMAGE_SIGNATURES:
        if raw.startswith(signature):
            return mime
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp'
    if extension == 'svg' and b'<svg' in raw[:512]:
        return 'image/svg+xml'
    return None


_FORMAT_LABELS = {
    'exe': 'Windows 可执行程序', 'dll': 'Windows 动态库', 'sys': 'Windows 驱动', 'msi': 'Windows 安装包',
    'zip': 'ZIP 压缩包', '7z': '7z 压缩包', 'rar': 'RAR 压缩包', 'gz': 'gzip 压缩包', 'tar': 'tar 归档',
    'mp4': '视频文件', 'avi': '视频文件', 'mov': '视频文件', 'mkv': '视频文件',
    'mp3': '音频文件', 'wav': '音频文件', 'flac': '音频文件',
    'db': '数据库文件', 'sqlite': '数据库文件', 'sqlite3': '数据库文件',
    'doc': '旧版 Word 文档（.doc）', 'psd': 'Photoshop 源文件',
}


def _truncate(content: str) -> tuple[str, bool]:
    encoded = content.encode('utf-8')
    if len(encoded) <= MAX_EXTRACTED_TEXT_BYTES:
        return content, False
    truncated = encoded[:MAX_EXTRACTED_TEXT_BYTES].decode('utf-8', 'ignore')
    return truncated + '\n\n（内容已截断：提取文本超过 1 MiB）', True


def _extract_docx(raw: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(raw))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(','.join(cells))
    return '\n'.join(parts)


def _extract_xlsx(raw: bytes) -> str:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    parts = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    rows.append(','.join('' if cell is None else str(cell) for cell in row))
            parts.append(f'## Sheet: {sheet.title}\n' + '\n'.join(rows))
    finally:
        workbook.close()
    return '\n\n'.join(parts)


def _extract_pptx(raw: bytes) -> str:
    from pptx import Presentation  # python-pptx

    presentation = Presentation(io.BytesIO(raw))
    parts = []
    for index, slide in enumerate(presentation.slides, start=1):
        lines = []
        for shape in slide.shapes:
            if getattr(shape, 'has_text_frame', False):
                text = shape.text_frame.text.strip()
                if text:
                    lines.append(text)
        parts.append(f'## 第 {index} 页\n' + '\n'.join(lines))
    return '\n\n'.join(parts)


def _extract_pdf(raw: bytes) -> str:
    import fitz  # PyMuPDF

    document = fitz.open(stream=raw, filetype='pdf')
    parts = []
    try:
        pages = min(document.page_count, MAX_PDF_PAGES)
        for number in range(pages):
            parts.append(f'## 第 {number + 1} 页\n' + document[number].get_text().strip())
        if document.page_count > pages:
            parts.append(f'（仅提取前 {pages} 页，全文共 {document.page_count} 页）')
    finally:
        document.close()
    return '\n\n'.join(parts)


_EXTRACTORS = {'docx': _extract_docx, 'xlsx': _extract_xlsx, 'xls': _extract_xlsx, 'pptx': _extract_pptx, 'pdf': _extract_pdf}


def extract_preview(relative_path: str, raw: bytes) -> dict:
    """按扩展名分发提取；无转换器或解析失败时回落文本探测/友好不支持。"""
    extension = PurePosixPath(relative_path.replace('\\', '/')).suffix.lower().lstrip('.')
    if len(raw) > MAX_PREVIEW_SOURCE_BYTES:
        raise ValueError(f'file exceeds {MAX_PREVIEW_SOURCE_BYTES} bytes')

    mime = _image_mime(raw, extension)
    if mime:
        return _payload('image', 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii'),
                        mime=mime, format=extension or None)

    extractor = _EXTRACTORS.get(extension)
    if extractor is not None:
        try:
            content, truncated = _truncate(extractor(raw))
            return _payload('extracted', content, format=extension,
                            **({'reason': '内容已截断：提取文本超过 1 MiB'} if truncated else {}))
        except Exception:  # noqa: BLE001 损坏/不支持的文档一律降级为只读提示，不放大成 5xx
            pass

    decoded = decode_text_best_effort(raw)
    if decoded is not None:
        return decoded

    label = _FORMAT_LABELS.get(extension, '二进制文件')
    return _payload('unsupported', '', format=extension or None,
                    reason=f'{label}（{(extension or "bin").upper()}，{len(raw)} 字节）暂不支持预览')
