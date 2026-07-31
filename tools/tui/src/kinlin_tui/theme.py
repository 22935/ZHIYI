"""
AgentOS TUI theme system.

Maps the four Agent roles to colors, names, icons, and Textual CSS classes.
"""

from enum import Enum


class RoleTheme(str, Enum):
    LAWYER = "lawyer"
    TEACHER = "teacher"
    PROGRAMMER = "programmer"
    WRITER = "writer"


ROLE_COLORS: dict[RoleTheme, str] = {
    RoleTheme.LAWYER: "#409EFF",
    RoleTheme.TEACHER: "#67C23A",
    RoleTheme.PROGRAMMER: "#9B59B6",
    RoleTheme.WRITER: "#E6A23C",
}

ROLE_NAMES: dict[RoleTheme, str] = {
    RoleTheme.LAWYER: "\u5f8b\u5e08",
    RoleTheme.TEACHER: "\u6559\u5e08",
    RoleTheme.PROGRAMMER: "\u7a0b\u5e8f\u5458",
    RoleTheme.WRITER: "\u4f5c\u5bb6",
}

ROLE_ICONS: dict[RoleTheme, str] = {
    RoleTheme.LAWYER: "\u2696\ufe0f",
    RoleTheme.TEACHER: "\U0001f4da",
    RoleTheme.PROGRAMMER: "\U0001f4bb",
    RoleTheme.WRITER: "\u270d\ufe0f",
}

# ---------------------------------------------------------------------------
# Textual CSS - dark theme with per-role accent borders
# ---------------------------------------------------------------------------

TEXTUAL_THEME_CSS = """

/* ---- Dark theme base ---- */

Screen {
    background: #0d1117;
}

Widget {
    background: #161b22;
    color: #c9d1d9;
}

/* ---- Role accent borders ---- */

.lawyer-theme {
    border: solid #409EFF;
}

.teacher-theme {
    border: solid #67C23A;
}

.programmer-theme {
    border: solid #9B59B6;
}

.writer-theme {
    border: solid #E6A23C;
}

/* ---- Layout widgets ---- */

Header {
    dock: top;
    height: 3;
    background: #161b22;
}

CommandBar {
    dock: bottom;
    height: 1;
    background: #161b22;
}

/* ---- Components ---- */

StatusTag {
    height: 1;
    /* status colors: success #67C23A, warning #E6A23C, error #F56C6C, info #409EFF */
}

StepList {
    height: auto;
}

ChatBubble {
    height: auto;
    padding: 1;
}

/* ---- Scrollbar ---- */

Scrollbar {
    background: #21262d;
    color: #484f58;
}

Scrollbar:hover {
    color: #8b949e;
}

/* ---- Footer / status bar ---- */

Footer {
    dock: bottom;
    height: 1;
    background: #161b22;
    color: #8b949e;
}

"""


def get_role_css(role: RoleTheme) -> str:
    """Return the CSS class name scoped to *role* (e.g. ``"lawyer-theme"``)."""
    return f"{role.value}-theme"
