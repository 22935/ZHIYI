"""单次工具工作进程；主服务以超时终止慢文档解析，密钥不传入该进程。"""
import json
import sys
from pathlib import Path
from .contracts import ConvertRequest, PdfParseRequest, ToolExecutionError
from .file_converter import FileConverter
from .pdf_parser import PdfParser


def execute(workspace, capability, data):
    if capability == "pdf.parse":
        return PdfParser(workspace).parse(PdfParseRequest.model_validate(data))
    if capability == "file.convert":
        return FileConverter(workspace, workspace / "outputs").convert(ConvertRequest.model_validate(data))
    raise ToolExecutionError("CAPABILITY_NOT_SUPPORTED")


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = execute(Path(request["workspace"]), request["capability"], request["input"])
        print(json.dumps({"output": result}, ensure_ascii=True))
    except ToolExecutionError as error:
        print(json.dumps({"output": {"error": str(error)}}))
    except Exception:
        print(json.dumps({"output": {"error": "INVALID_TOOL_INPUT"}}))
