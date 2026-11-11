"""本地工具的越界输入、真实转换和输出隔离测试。"""
import pytest
from pydantic import ValidationError
from components.marketplace.builtins.contracts import ConvertRequest, PdfParseRequest


@pytest.mark.parametrize("path", ["../secret.txt", "/etc/passwd", "C:/secret.txt", "a\\b.txt", "https://x/y", "", ".", "a/../b"])
def test_reject_unsafe_paths(path):
    with pytest.raises(ValidationError):
        ConvertRequest(sourcePath=path, targetFormat="txt")


def test_reject_commands_and_unknown_formats():
    with pytest.raises(ValidationError):
        ConvertRequest(sourcePath="a.txt", targetFormat="exe")
    with pytest.raises(ValidationError):
        PdfParseRequest(sourcePath="a.pdf", command="whoami")
    with pytest.raises(ValidationError):
        PdfParseRequest(sourcePath="a.pdf", firstPage=3, lastPage=1)


def text_pdf(path):
    # 最小有效 PDF，带真实文字流，避免测试依赖额外 PDF 绘图库。
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    content = b'BT /F1 12 Tf 30 200 Td (agentos) Tj ET'
    objects.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream')
    data = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
    path.write_bytes(data)


def test_pdf_extracts_real_text_and_rejects_scans(tmp_path):
    from components.marketplace.builtins.pdf_parser import PdfParser
    from components.marketplace.builtins.contracts import ToolExecutionError
    from pypdf import PdfWriter
    text_pdf(tmp_path / "input.pdf")
    result = PdfParser(tmp_path).parse(PdfParseRequest(sourcePath="input.pdf"))
    assert result["text"] == "agentos"
    assert result["pages"] == 1
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with (tmp_path / "scan.pdf").open("wb") as file:
        writer.write(file)
    with pytest.raises(ToolExecutionError, match="OCR_NOT_AVAILABLE"):
        PdfParser(tmp_path).parse(PdfParseRequest(sourcePath="scan.pdf"))


def test_conversion_is_real_isolated_and_never_overwrites(tmp_path):
    from components.marketplace.builtins.file_converter import FileConverter
    (tmp_path / "input.md").write_text("# Title\n<script>bad()</script>", encoding="utf-8")
    converter = FileConverter(tmp_path, tmp_path / "out")
    result = converter.convert(ConvertRequest(sourcePath="input.md", targetFormat="html"))
    output = tmp_path / result["outputPath"]
    assert output.parent.parent == tmp_path / "out"
    assert "<h1>Title</h1>" in output.read_text(encoding="utf-8")
    assert "<script>" not in output.read_text(encoding="utf-8")
    assert (tmp_path / "input.md").read_text(encoding="utf-8").startswith("# Title")
    again = converter.convert(ConvertRequest(sourcePath="input.md", targetFormat="html"))
    assert again["outputPath"] != result["outputPath"]


def test_csv_json_roundtrip_and_unsupported_pair(tmp_path):
    from components.marketplace.builtins.file_converter import FileConverter
    from components.marketplace.builtins.contracts import ToolExecutionError
    import json
    (tmp_path / "input.csv").write_text('name,value\n中文,42\n', encoding="utf-8")
    converter = FileConverter(tmp_path, tmp_path / "out")
    result = converter.convert(ConvertRequest(sourcePath="input.csv", targetFormat="json"))
    assert json.loads((tmp_path / result["outputPath"]).read_text(encoding="utf-8")) == [{"name": "中文", "value": "42"}]
    with pytest.raises(ToolExecutionError, match="FORMAT_NOT_SUPPORTED"):
        converter.convert(ConvertRequest(sourcePath="input.csv", targetFormat="html"))


def test_office_files_are_converted_without_calculating_formulas(tmp_path):
    from docx import Document
    from openpyxl import Workbook
    from components.marketplace.builtins.file_converter import FileConverter
    import json
    document = Document()
    document.add_paragraph("真实文档")
    document.save(tmp_path / "input.docx")
    book = Workbook()
    book.active.append(["name", "value"])
    book.active.append(["中文", "=1+2"])
    book.save(tmp_path / "input.xlsx")
    converter = FileConverter(tmp_path, tmp_path / "out")
    result = converter.convert(ConvertRequest(sourcePath="input.docx", targetFormat="txt"))
    assert (tmp_path / result["outputPath"]).read_text(encoding="utf-8") == "真实文档"
    result = converter.convert(ConvertRequest(sourcePath="input.xlsx", targetFormat="json"))
    assert json.loads((tmp_path / result["outputPath"]).read_text(encoding="utf-8")) == [{"name": "中文", "value": None}]


def test_duplicate_csv_headers_and_spreadsheet_formula_export(tmp_path):
    from components.marketplace.builtins.file_converter import FileConverter
    from components.marketplace.builtins.contracts import ToolExecutionError
    converter = FileConverter(tmp_path, tmp_path / "out")
    (tmp_path / "input.csv").write_text("a,a\n1,2", encoding="utf-8")
    with pytest.raises(ToolExecutionError, match="TABLE_SHAPE_INVALID"):
        converter.convert(ConvertRequest(sourcePath="input.csv", targetFormat="json"))
    (tmp_path / "input.json").write_text('[{"name":"=1+2"}]', encoding="utf-8")
    result = converter.convert(ConvertRequest(sourcePath="input.json", targetFormat="csv"))
    assert "'=1+2" in (tmp_path / result["outputPath"]).read_text(encoding="utf-8")
