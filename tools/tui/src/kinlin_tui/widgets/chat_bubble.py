"""Chat message bubble widget."""

from textual.widgets import Static


class ChatBubble(Static):
    """Renders a chat message bubble."""

    def __init__(self, role: str, content: str, timestamp: str = "") -> None:
        self._role = role
        self._content = content
        self._timestamp = timestamp
        super().__init__()

    def render(self) -> str:
        if self._role == "user":
            sender = "[bold cyan]You:[/]"
        else:
            sender = "[bold #409EFF]ZhiYi:[/]"

        parts = [sender, self._content]

        if self._timestamp:
            parts.append(f"[dim]{self._timestamp}[/]")

        return "\n".join(parts)
