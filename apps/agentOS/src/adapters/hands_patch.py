"""Chat patch_file 的 unified diff 应用器。

逐字移植自已删除的 apps/local-runtime/capabilities/filesystem.py 的
apply_unified_patch 及辅助函数（含 runtime.errors.PatchConflictError 的语义），
供 HandsHttpTransport 把 chat 的 ``patch`` diff 翻译成 hands 的读-改-写序列。
python Local Runtime 执行器已移除，本文件是其补丁算法的唯一存续副本；
算法追溯可用 git 历史对表原实现。
"""

from __future__ import annotations


class PatchConflictError(RuntimeError):
    """与 local-runtime runtime.errors.PatchConflictError 同义：无法干净应用。"""

    def __init__(self) -> None:
        super().__init__("PATCH_CONFLICT")


def apply_unified_patch(source: str, patch_text: str) -> str:
    """Apply exact single-file unified hunks without invoking a patch utility."""
    lines = source.splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    hunks: list[tuple[int, int, int, list[str]]] = []
    index = 0
    while index < len(patch_lines):
        line = patch_lines[index]
        if not line.startswith("@@"):
            index += 1
            continue
        try:
            header = line.split("@@", 2)[1].strip()
            old_part, new_part = header.split(" ", 1)
            old_start, old_count = _parse_hunk_range(old_part, "-")
            _new_start, _new_count = _parse_hunk_range(new_part, "+")
        except (IndexError, ValueError) as exc:
            raise PatchConflictError() from exc
        index += 1
        body: list[str] = []
        while index < len(patch_lines) and not patch_lines[index].startswith("@@"):
            item = patch_lines[index]
            if item.startswith((" ", "+", "-")):
                body.append(item)
            elif item.startswith("\\ No newline"):
                pass
            elif item.startswith(("---", "+++")) and not body:
                pass
            else:
                raise PatchConflictError()
            index += 1
        hunks.append((old_start, old_count, _new_count, body))
    if not hunks:
        raise PatchConflictError()
    offset = 0
    for old_start, old_count, new_count, body in hunks:
        position = (0 if old_start == 0 else old_start - 1) + offset
        old_lines: list[str] = []
        new_lines: list[str] = []
        for item in body:
            if item.startswith(" "):
                content = _normalize_patch_line(item[1:], newline)
                old_lines.append(content)
                new_lines.append(content)
            elif item.startswith("-"):
                old_lines.append(_normalize_patch_line(item[1:], newline))
            elif item.startswith("+"):
                new_lines.append(_normalize_patch_line(item[1:], newline))
        if (
            len(old_lines) != old_count
            or len(new_lines) != new_count
            or lines[position:position + old_count] != old_lines
        ):
            raise PatchConflictError()
        lines[position:position + old_count] = new_lines
        offset += len(new_lines) - old_count
    return "".join(lines)


def _parse_hunk_range(value: str, marker: str) -> tuple[int, int]:
    if not value.startswith(marker):
        raise ValueError("invalid hunk marker")
    raw = value[1:]
    if "," in raw:
        start, count = raw.split(",", 1)
        return int(start), int(count)
    return int(raw), 1


def _normalize_patch_line(value: str, newline: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        return normalized[:-1] + newline
    return normalized
