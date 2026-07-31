"""Dashboard screen showing workflow runs and details."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from kinlin_tui.widgets.command_bar import CommandBar
from kinlin_tui.widgets.header import HeaderWidget
from kinlin_tui.widgets.status_tag import StatusTag
from kinlin_tui.widgets.step_list import StepList


def _first_text(mapping: dict, *keys: str, default: str = "") -> str:
    """Return the first non-empty value for *keys* as text."""
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value):
            return str(value)
    return default


def _row_key_text(row_key: object) -> str:
    """Extract a string value from Textual's RowKey wrapper."""
    value = getattr(row_key, "value", row_key)
    return str(value)


class TraceScreen(Screen):
    """Simple full-screen trace viewer."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
    ]

    def __init__(self, trace_text: str) -> None:
        super().__init__()
        self._trace_text = trace_text

    def compose(self) -> ComposeResult:
        yield Static("Execution Trace", id="trace-title")
        yield Static(self._trace_text, id="trace-content")

    def action_dismiss(self) -> None:
        self.app.pop_screen()


class DashboardScreen(Screen):
    """Dashboard showing workflow runs in a DataTable with a detail panel."""

    BINDINGS = [
        Binding("escape", "goto_chat", "Chat"),
        Binding("f1", "goto_chat", "Home"),
        Binding("r", "refresh_runs", "Refresh"),
        Binding("v", "view_trace", "View Trace"),
        Binding("c", "cancel_run", "Cancel"),
    ]

    CSS = """
    #section-title {
        height: 1;
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
        padding: 0 2;
    }

    #runs-table {
        height: 55%;
    }

    #detail-title {
        height: 1;
        background: #1c2128;
        color: #8b949e;
        padding: 0 2;
    }

    StepList {
        height: auto;
        max-height: 12;
        padding: 0 2;
    }

    #detail-actions {
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 2;
    }

    #trace-title {
        height: 1;
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
        padding: 0 2;
    }

    #trace-content {
        padding: 1 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._selected_run_id: str | None = None

    def compose(self) -> ComposeResult:
        yield HeaderWidget(id="header")
        yield Label("Workflow Console", id="section-title")
        yield DataTable(id="runs-table", cursor_type="row")
        yield Static("Select a run to view details", id="detail-title")
        yield StepList(steps=[])
        yield Static("[R]efresh  [V]iew Trace  [C]ancel Run", id="detail-actions")
        yield CommandBar(id="command-bar")

    def on_mount(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.add_column("#", width=4)
        table.add_column("Run ID", width=14)
        table.add_column("Title", width=30)
        table.add_column("Status", width=16)
        table.add_column("Progress", width=10)
        table.add_column("Role", width=12)
        self.call_after_refresh(self.action_refresh_runs)
        self.set_interval(3, self.action_refresh_runs)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_refresh_runs(self) -> None:
        """Fetch workflow runs from the API and populate the table."""
        result = await self.app.api_client.list_workflow_runs()
        table = self.query_one("#runs-table", DataTable)
        table.clear()

        items = result.get("items", [])
        if not items:
            self.query_one("#detail-title", Static).update(
                "No workflow runs found"
            )
            return

        for i, run in enumerate(items, start=1):
            run_id = _first_text(run, "runId", "run_id", "id")
            title = _first_text(
                run,
                "title",
                "taskTitle",
                "task_title",
                "workflowId",
                "workflow_id",
                default="Untitled",
            )
            status = _first_text(run, "status", default="unknown")
            domain = _first_text(
                run,
                "domain",
                "roleType",
                "role_type",
                "role",
                default="-",
            )
            row_key = run_id or _first_text(run, "taskId", "task_id", default=f"row-{i}")

            steps = run.get("steps", [])
            total = len(steps)
            done = sum(1 for s in steps if s.get("status") == "completed")

            progress = f"{done}/{total}" if total > 0 else "-/-"

            status_color = StatusTag.get_color(status)
            status_cell = f"[{status_color}]{status}[/]"

            table.add_row(
                str(i),
                (run_id or row_key)[:12],
                title[:50],
                status_cell,
                progress,
                domain,
                key=row_key,
            )

    async def on_data_table_row_selected(
        self, event: DataTable.RowSelected
    ) -> None:
        """Handle row selection: fetch run details and show steps."""
        if event.row_key is None:
            return
        run_id = _row_key_text(event.row_key)
        self._selected_run_id = run_id

        result = await self.app.api_client.get_workflow_run(run_id)
        if "error" in result:
            self.notify(f"Error: {result['error']}", severity="error")
            return

        title = _first_text(
            result,
            "title",
            "taskTitle",
            "task_title",
            "workflowId",
            "workflow_id",
            default="Untitled",
        )
        status = _first_text(result, "status", default="unknown")
        status_color = StatusTag.get_color(status)

        self.query_one("#detail-title", Static).update(
            f"[bold]Run:[/] {title}  [{status_color}]{status}[/]"
        )

        steps = result.get("steps", [])
        step_list = self.query_one(StepList)
        step_list._steps = steps
        step_list.refresh()

    async def action_view_trace(self) -> None:
        """Fetch and display the execution trace for the selected run."""
        if not self._selected_run_id:
            self.notify("Select a run first", severity="warning")
            return

        result = await self.app.api_client.get_trace(
            self._selected_run_id, "markdown"
        )
        if isinstance(result, dict) and "error" in result:
            self.notify(f"Error: {result['error']}", severity="error")
            return

        trace_text = result if isinstance(result, str) else str(result)
        self.app.push_screen(TraceScreen(trace_text))

    async def action_cancel_run(self) -> None:
        """Cancel the selected workflow run."""
        if not self._selected_run_id:
            self.notify("Select a run first", severity="warning")
            return

        result = await self.app.api_client.cancel_workflow(
            self._selected_run_id
        )
        if "error" in result:
            self.notify(f"Error: {result['error']}", severity="error")
        else:
            self.notify(
                f"Run {self._selected_run_id[:12]} cancelled"
            )
        await self.action_refresh_runs()

    def action_goto_chat(self) -> None:
        """Switch to the chat screen."""
        self.app.switch_screen("chat")
