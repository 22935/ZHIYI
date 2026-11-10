"""固定工具合同：调用方只能选工作区文件和支持格式，不能传命令或输出路径。"""
from pathlib import Path, PurePosixPath
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
MAX_PAGES = 200
MAX_ROWS = 50_000
SUPPORTED_PAIRS = {
    "txt": {"md", "html"}, "md": {"txt", "html"}, "html": {"txt", "md"},
    "csv": {"json"}, "json": {"csv"}, "docx": {"txt", "md", "html"},
    "xlsx": {"csv", "json"}, "pdf": {"txt", "md"},
}


class ToolExecutionError(ValueError):
    """可公开的稳定错误码，不携带本机路径或文档正文。"""


class ToolRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    source_path: str = Field(alias="sourcePath", min_length=1, max_length=512)

    @field_validator("source_path")
    @classmethod
    def safe_relative_path(cls, value):
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or any(c in value for c in ("\\", ":", "\x00")) or value in {"", "."}:
            raise ValueError("sourcePath must be a relative workspace path")
        return value


class ConvertRequest(ToolRequest):
    target_format: Literal["txt", "md", "html", "csv", "json"] = Field(alias="targetFormat")


class PdfParseRequest(ToolRequest):
    first_page: int = Field(default=1, alias="firstPage", ge=1, le=MAX_PAGES)
    last_page: int | None = Field(default=None, alias="lastPage", ge=1, le=MAX_PAGES)

    @model_validator(mode="after")
    def page_order(self):
        if self.last_page is not None and self.last_page < self.first_page:
            raise ValueError("lastPage must not precede firstPage")
        return self


def source_file(workspace: Path, relative: str) -> Path:
    """再次校验真实路径，拒绝 symlink/junction 跳出受控工作区。"""
    root = workspace.resolve()
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ToolExecutionError("SOURCE_NOT_FOUND")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolExecutionError("FILE_TOO_LARGE")
    return path
