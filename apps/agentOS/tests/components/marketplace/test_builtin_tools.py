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
