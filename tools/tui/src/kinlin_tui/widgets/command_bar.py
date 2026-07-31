"""Bottom command bar showing keyboard shortcuts."""

from textual.reactive import reactive
from textual.widgets import Static


class CommandBar(Static):
    """Bottom command bar showing keyboard shortcuts."""

    status_text: str = reactive("Connected")

    def render(self) -> str:
        return (
            "[bold]F1[/][dim]Home[/]  "
            "[bold]F2[/][dim]Switch[/]  "
            "[bold]F3[/][dim]Files[/]  "
            "[bold]F5[/][dim]Dashboard[/]  "
            "[bold]Ctrl+Q[/][dim]Quit[/]  "
            f"-- [dim]{self.status_text}[/]"
        )
