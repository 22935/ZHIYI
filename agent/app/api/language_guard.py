import asyncio
import logging
import re
from typing import Dict, List, Optional

from app.services.aiservice import AIService

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _chinese_ratio(text: str) -> float:
    visible = [ch for ch in (text or "") if not ch.isspace()]
    if not visible:
        return 1.0
    cjk_count = sum(1 for ch in visible if _CJK_RE.match(ch))
    return cjk_count / len(visible)


def _needs_chinese_normalization(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False

    # Already mostly Chinese: skip extra model call.
    if _chinese_ratio(content) >= 0.25:
        return False

    # Non-Chinese text with latin letters likely needs conversion.
    return bool(_LATIN_RE.search(content))


async def ensure_simplified_chinese(
    text: str,
    ai_service: AIService,
    history: Optional[List[Dict[str, str]]] = None,
    timeout_seconds: int = 8,
) -> str:
    content = (text or "").strip()
    if not _needs_chinese_normalization(content):
        return content

    prompt = (
        "请将下面内容转换为简体中文输出。\n"
        "要求：\n"
        "1. 保留原始含义，不新增事实。\n"
        "2. 保留 Markdown 结构（标题、列表、表格）。\n"
        "3. 代码块、Mermaid、JSON 键名、URL、文件路径、命令保持原样，不要翻译。\n"
        "4. 仅返回转换后的内容，不要附加解释。\n\n"
        f"原文：\n{content}"
    )

    try:
        response = await asyncio.wait_for(
            ai_service.generate_text(text=prompt, context=(history or [])[-6:]),
            timeout=timeout_seconds,
        )
        converted = (response.get("text", "") or "").strip()
        if not converted:
            return content

        # Keep safer fallback: if converted loses fenced code blocks, preserve original.
        if content.count("```") >= 2 and converted.count("```") < content.count("```"):
            return content
        return converted
    except Exception as exc:
        logger.warning("Failed to normalize response to Simplified Chinese: %s", exc)
        return content
