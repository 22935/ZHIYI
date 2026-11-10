"""基于 pypdf 的本地文本 PDF 提取，不执行附件、脚本或外链。"""
from pathlib import Path
from pypdf import PdfReader, __version__
from .contracts import MAX_PAGES, MAX_TEXT_CHARS, PdfParseRequest, ToolExecutionError, source_file


class PdfParser:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)

    def parse(self, request: PdfParseRequest) -> dict:
        path = source_file(self.workspace, request.source_path)
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ToolExecutionError("INVALID_PDF")
            stream.seek(0)
            try:
                reader = PdfReader(stream, strict=True)
                if reader.is_encrypted:
                    raise ToolExecutionError("ENCRYPTED_PDF_NOT_SUPPORTED")
                total = len(reader.pages)
                if total > MAX_PAGES:
                    raise ToolExecutionError("PAGE_LIMIT_EXCEEDED")
                last = request.last_page or total
                if request.first_page > total or last > total:
                    raise ToolExecutionError("PAGE_RANGE_INVALID")
                pages, length = [], 0
                for index in range(request.first_page - 1, last):
                    text = (reader.pages[index].extract_text() or "").strip()
                    if not text:
                        raise ToolExecutionError("OCR_NOT_AVAILABLE")
                    length += len(text)
                    if length > MAX_TEXT_CHARS:
                        raise ToolExecutionError("TEXT_LIMIT_EXCEEDED")
                    pages.append({"page": index + 1, "text": text})
                metadata = reader.metadata or {}
                return {"pages": total, "extractedPages": pages, "text": "\n\n".join(p["text"] for p in pages),
                        "extractor": {"name": "pypdf", "version": __version__},
                        "metadata": {key[1:].lower(): str(metadata[key])[:256] for key in ("/Title", "/Author", "/Subject") if key in metadata}}
            except ToolExecutionError:
                raise
            except Exception as error:
                raise ToolExecutionError("INVALID_PDF") from error
