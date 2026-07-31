"""Workflow step progress list widget."""

from textual.widgets import Static


STATUS_ICONS: dict[str, str] = {
    "completed": "✅",
    "running": "🟢",
    "pending": "⏳",
    "failed": "❌",
    "waiting_review": "⏸️",
    "retrying": "🔄",
    "cancelled": "⊘",
    "planning": "⏳",
}


class StepList(Static):
    """Shows workflow step progress as a vertical list."""

    def __init__(self, steps: list[dict]) -> None:
        self._steps = steps
        super().__init__()

    def render(self) -> str:
        lines: list[str] = []
        for step in self._steps:
            name = step.get("name", "Unknown")
            status = step.get("status", "pending")
            error = step.get("error")
            icon = STATUS_ICONS.get(status, "⏳")

            line = f"{icon} {name}"

            if status == "running":
                line += "  [bold #409EFF][Running...][/]"

            lines.append(line)

            if error:
                lines.append(f"    [red]{error}[/]")

        return "\n".join(lines)
