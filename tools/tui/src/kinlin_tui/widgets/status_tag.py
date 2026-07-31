"""Colored status label widget."""

from textual.widgets import Static


STATUS_MAP: dict[str, tuple[str, str]] = {
    "pending": ("[dim grey]●[/] [dim]Pending[/]", "grey"),
    "planning": ("[dim grey]●[/] [dim]Planning[/]", "grey"),
    "running": ("[bold #409EFF]●[/] [bold]Running[/]", "#409EFF"),
    "waiting_review": ("[bold #E6A23C]●[/] [bold]Review Needed[/]", "#E6A23C"),
    "retrying": ("[bold #E6A23C]●[/] [bold]Retrying[/]", "#E6A23C"),
    "failed": ("[bold #F56C6C]●[/] [bold]Failed[/]", "#F56C6C"),
    "completed": ("[bold #67C23A]●[/] [bold]Done[/]", "#67C23A"),
    "cancelled": ("[dim grey]●[/] [dim]Cancelled[/]", "grey"),
}


class StatusTag(Static):
    """A small widget that renders a colored status label."""

    def __init__(self, status: str) -> None:
        self._status = status
        super().__init__()

    def render(self) -> str:
        markup, _color = STATUS_MAP.get(self._status, STATUS_MAP["pending"])
        return markup

    @classmethod
    def get_color(cls, status: str) -> str:
        _markup, color = STATUS_MAP.get(status, STATUS_MAP["pending"])
        return color
