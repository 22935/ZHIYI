"""Header bar widget showing app title, current agent role, and working directory."""

from textual.widgets import Static
from textual.reactive import reactive
from kinlin_tui.theme import RoleTheme, ROLE_ICONS, ROLE_NAMES, ROLE_COLORS
import os


class HeaderWidget(Static):
    """Top header bar showing app title, current agent role, and working directory."""

    role: RoleTheme = reactive(RoleTheme.LAWYER)
    cwd: str = reactive(os.path.basename(os.getcwd()))

    def render(self) -> str:
        icon = ROLE_ICONS.get(self.role, "?")
        name = ROLE_NAMES.get(self.role, "Unknown")
        color = ROLE_COLORS.get(self.role, "#409EFF")
        return (
            f"[bold {color}]ZhiYi AgentOS TUI[/]  |  "
            f"{icon} [bold]{name}[/]  |  "
            f"[dim]cwd:[/] {self.cwd}  |  "
            f"[dim]Settings[/]"
        )
