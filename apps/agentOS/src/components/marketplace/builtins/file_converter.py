"""白名单格式转换；不调用 shell、不加载宏、不访问网络、不覆盖源文件。"""
import csv
import html
import io
import json
import re
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path
import markdown
from .contracts import SUPPORTED_PAIRS, ConvertRequest, MAX_FILE_BYTES, MAX_ROWS, MAX_TEXT_CHARS, PdfParseRequest, ToolExecutionError, source_file
from .pdf_parser import PdfParser

class PlainText(HTMLParser):
    """提取可见文字；脚本/样式内容丢弃，不跟随任何链接。"""
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class SafeMarkup(HTMLParser):
    """保留 Markdown 排版标签，移除图片、链接属性等活动内容。"""
    allowed = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "code", "pre", "blockquote", "ul", "ol", "li", "hr", "br"}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.allowed:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in self.allowed:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(html.escape(data))


def markdown_html(text):
    cleaner = SafeMarkup()
    cleaner.feed(markdown.markdown(html.escape(text)))
    return "".join(cleaner.parts)


def visible_text(text):
    parser = PlainText()
    parser.feed(text)
    return "".join(parser.parts).strip()


def check_office_archive(path):
    """Office 文档为 ZIP；在解析前限制展开大小、条目数和压缩比。"""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 2000 or sum(m.file_size for m in members) > MAX_FILE_BYTES * 3:
            raise ToolExecutionError("ARCHIVE_LIMIT_EXCEEDED")
        if any(m.file_size > max(m.compress_size, 1) * 200 for m in members):
            raise ToolExecutionError("ARCHIVE_LIMIT_EXCEEDED")


class FileConverter:
    def __init__(self, workspace: Path, output_root: Path):
        self.workspace = Path(workspace).resolve()
        self.output_root = Path(output_root).resolve()
        if self.workspace not in self.output_root.parents:
            raise ValueError("output root must be inside workspace")

    def convert(self, request: ConvertRequest) -> dict:
        path = source_file(self.workspace, request.source_path)
        source, target = path.suffix.lower().lstrip("."), request.target_format
        if target not in SUPPORTED_PAIRS.get(source, set()):
            raise ToolExecutionError("FORMAT_NOT_SUPPORTED")
        try:
            text = self._convert(path, source, target)
        except ToolExecutionError:
            raise
        except Exception as error:
            raise ToolExecutionError("INVALID_SOURCE_DOCUMENT") from error
        if len(text) > MAX_TEXT_CHARS:
            raise ToolExecutionError("TEXT_LIMIT_EXCEEDED")
        # 每次调用独占随机目录；重新 resolve 防止输出根被替换为工作区外链接。
        directory = (self.output_root / uuid.uuid4().hex).resolve()
        if self.workspace not in directory.parents:
            raise ToolExecutionError("OUTPUT_PATH_INVALID")
        directory.mkdir(parents=True, exist_ok=False)
        output = directory / f"result.{target}"
        output.write_text(text, encoding="utf-8")
        return {"outputPath": output.relative_to(self.workspace).as_posix(), "format": target, "sizeBytes": output.stat().st_size}

    def _convert(self, path, source, target):
        if source in {"csv", "json", "xlsx"}:
            rows = self._read_rows(path, source)
            if target == "json":
                return json.dumps(rows, ensure_ascii=False, indent=2, default=str)
            if not rows:
                return ""
            if any(not isinstance(row, dict) for row in rows):
                raise ToolExecutionError("TABLE_SHAPE_INVALID")
            keys = list(dict.fromkeys(key for row in rows for key in row))
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=keys)
            writer.writeheader()
            # 防止导出的 CSV 在表格软件打开时触发公式。
            for row in rows:
                writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
            return buffer.getvalue()
        if source == "pdf":
            text = PdfParser(self.workspace).parse(PdfParseRequest(sourcePath=path.relative_to(self.workspace).as_posix()))["text"]
        elif source == "docx":
            from docx import Document
            check_office_archive(path)
            document = Document(path)
            text = "\n".join([p.text for p in document.paragraphs] + ["\t".join(c.text for c in row.cells) for table in document.tables for row in table.rows])
        else:
            text = path.read_text(encoding="utf-8-sig")
        if source == "html":
            text = visible_text(text)
        if target == "html":
            body = markdown_html(text) if source == "md" else "<pre>" + html.escape(text) + "</pre>"
            return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'"></head><body>' + body + '</body></html>'
        if source == "md" and target == "txt":
            return visible_text(markdown_html(text))
        if target == "md":
            # 非 Markdown 文档按纯文本导出，转义语法字符，避免内容被误解释为排版。
            return re.sub(r"([\\`*_{}\[\]<>#+.!|~-])", r"\\\1", text)
        return text

    def _read_rows(self, path, source):
        if source == "xlsx":
            from openpyxl import load_workbook
            check_office_archive(path)
            book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
            try:
                sheet = book.active
                if sheet.max_row > MAX_ROWS + 1 or sheet.max_column > 256:
                    raise ToolExecutionError("TABLE_LIMIT_EXCEEDED")
                iterator = sheet.iter_rows(values_only=True)
                headers = [str(v) if v is not None else f"column_{i}" for i, v in enumerate(next(iterator, []))]
                if len(headers) != len(set(headers)):
                    raise ToolExecutionError("TABLE_SHAPE_INVALID")
                rows = [dict(zip(headers, row)) for row in iterator]
            finally:
                book.close()
        elif source == "csv":
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = []
                reader = csv.DictReader(file)
                if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise ToolExecutionError("TABLE_SHAPE_INVALID")
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ToolExecutionError("TABLE_SHAPE_INVALID")
                    rows.append(row)
                    if len(rows) > MAX_ROWS:
                        raise ToolExecutionError("TABLE_LIMIT_EXCEEDED")
        else:
            rows = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(rows, list) or len(rows) > MAX_ROWS or any(not isinstance(r, dict) for r in rows):
            raise ToolExecutionError("TABLE_SHAPE_INVALID")
        return rows
