"""Chat screen -- the primary interaction surface of the AgentOS TUI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, RichLog

from kinlin_tui.mascot import MascotMood
from kinlin_tui.theme import RoleTheme, ROLE_NAMES, ROLE_ICONS
from kinlin_tui.widgets.command_bar import CommandBar as CommandBarWidget
from kinlin_tui.widgets.header import HeaderWidget
from kinlin_tui.widgets.mascot_widget import MascotWidget


class ChatScreen(Screen):
    """Chat screen with file tree, message log, input, and context panel.

    Layout: 3-column CSS grid (1fr 4fr 1fr) with docked header and
    command bar.  The center column stacks a RichLog above an Input
    inside a Vertical container so both occupy the same grid cell.
    """

    CSS = """
    HeaderWidget {
        dock: top;
    }

    CommandBarWidget {
        dock: bottom;
    }

    #main-row {
        height: 1fr;
    }

    #center-col {
        width: 1fr;
        height: 1fr;
    }

    #center-col > RichLog {
        height: 1fr;
        border: solid #30363d;
        background: #0d1117;
    }

    #center-col > Input {
        height: auto;
        dock: bottom;
        margin: 0 0 1 0;
        border: solid #30363d;
    }

    #mascot-panel {
        width: 28;
        height: 1fr;
        padding: 1 1;
        border: solid #30363d;
        background: #0d1117;
    }

    #mascot {
        width: 100%;
        height: 14;
        content-align: center top;
        background: #0d1117;
    }
    """

    BINDINGS = [
        Binding("escape", "focus_input", "Focus Input"),
        Binding("f2", "toggle_role", "Switch Agent"),
        Binding("f3", "show_files", "Files"),
        Binding("f5", "goto_dashboard", "Dashboard"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Rendered markup lines kept so we can clear + rewrite the log
        # when replacing the "thinking" placeholder with a real answer.
        self._rendered: list[str] = []
        self._session_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield HeaderWidget(id="header")

        with Horizontal(id="main-row"):
            with Vertical(id="center-col"):
                yield RichLog(id="message-log", highlight=True, markup=True)
                yield Input(id="chat-input", placeholder="Type a message...")
            with Vertical(id="mascot-panel"):
                yield MascotWidget(id="mascot")

        yield CommandBarWidget(id="command-bar")

    # ------------------------------------------------------------------
    # Mount
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Focus the chat input and sync the header role from the app."""
        self.query_one("#chat-input", Input).focus()

        try:
            role = self.app.current_role  # type: ignore[attr-defined]
            header = self.query_one("#header", HeaderWidget)
            header.role = role
            self._set_mascot(role=role, mood=MascotMood.IDLE)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_focus_input(self) -> None:
        """Focus the chat input widget."""
        self.query_one("#chat-input", Input).focus()

    def action_goto_dashboard(self) -> None:
        """Navigate to the dashboard screen."""
        self.app.push_screen("dashboard")  # type: ignore[attr-defined]

    def action_toggle_role(self) -> None:
        """Cycle through agent roles: lawyer -> teacher -> programmer -> writer."""
        roles = list(RoleTheme)
        try:
            current = self.app.current_role  # type: ignore[attr-defined]
            idx = roles.index(current)
        except (ValueError, AttributeError):
            idx = 0
        next_role = roles[(idx + 1) % len(roles)]
        self.app.current_role = next_role  # type: ignore[attr-defined]
        header = self.query_one("#header", HeaderWidget)
        header.role = next_role
        self._set_mascot(role=next_role, mood=MascotMood.IDLE)
        self.notify(
            f"Switched to {ROLE_ICONS[next_role]} {ROLE_NAMES[next_role]}",
            timeout=2,
        )

    def action_show_files(self) -> None:
        """Show current working directory contents in the message log."""
        import os
        cwd = os.getcwd()
        items = sorted(os.listdir(cwd))
        lines = [f"[bold]Files in [underline]{cwd}[/][/]\n"]
        for item in items:
            full = os.path.join(cwd, item)
            prefix = "[bold blue]DIR [/]" if os.path.isdir(full) else "     "
            lines.append(f"  {prefix} {item}")
        self._rendered.append("\n".join(lines))
        log = self.query_one("#message-log", RichLog)
        self._render_log(log)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    @on(Input.Submitted)
    async def on_chat_input_submitted(self, event: Input.Submitted) -> None:
        """Send a chat message to the agent and display the reply."""
        text = event.value.strip()
        if not text:
            return

        # Clear the input immediately so the user can type the next message.
        input_widget = self.query_one("#chat-input", Input)
        input_widget.clear()

        log = self.query_one("#message-log", RichLog)
        now = datetime.now().strftime("%H:%M")

        # -- user message -------------------------------------------------
        user_line = f"[bold cyan]You:[/] {text}  [dim]{now}[/]"
        self._rendered.append(user_line)
        self._render_log(log)

        # -- thinking placeholder -----------------------------------------
        thinking_line = "[dim italic]ZhiYi is thinking...[/]"
        self._rendered.append(thinking_line)
        self._render_log(log)
        self._set_mascot(mood=MascotMood.THINKING)

        # -- API call -----------------------------------------------------
        role_str: str = "lawyer"
        try:
            role_str = self.app.current_role.value  # type: ignore[attr-defined]
        except Exception:
            pass

        result: dict = {}
        session_id = self._session_ids.get(role_str)
        try:
            result = await self.app.api_client.agent_chat(  # type: ignore[attr-defined]
                role_str,
                text,
                session_id=session_id,
            )
        except Exception as exc:
            result = {"error": str(exc)}

        # -- replace thinking with answer ---------------------------------
        self._rendered.pop()  # remove thinking placeholder

        returned_session_id = result.get("sessionId") or result.get("session_id")
        if returned_session_id:
            self._session_ids[role_str] = str(returned_session_id)

        if "error" in result:
            answer_line = f"[bold red]Error:[/] {result['error']}"
            self._set_mascot(mood=MascotMood.ERROR)
        elif result.get("answer"):
            answer_line = self._format_agent_reply(result)
            self._set_mascot(mood=MascotMood.HAPPY)
        elif not result.get("success", True):
            answer_line = f"[bold red]API failed:[/] {str(result)[:500]}"
            self._set_mascot(mood=MascotMood.ERROR)
        else:
            reply: str = (
                result.get("response")
                or result.get("reply")
                or result.get("text")
                or str(result)[:500]
            )
            answer_line = f"[bold #409EFF]ZhiYi:[/]\n{reply}"
            self._set_mascot(mood=MascotMood.HAPPY)

        self._rendered.append(answer_line)
        self._render_log(log)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_log(self, log: RichLog) -> None:
        """Clear *log* and rewrite every line from ``self._rendered``."""
        log.clear()
        for line in self._rendered:
            log.write(line)
        log.scroll_end(animate=False)

    def _format_agent_reply(self, result: dict[str, Any]) -> str:
        """Render the agent answer plus routing/trace metadata when present."""
        lines = [f"[bold #409EFF]ZhiYi:[/]\n{result.get('answer', '')}"]

        route_lines = self._routing_lines(result)
        if route_lines:
            lines.extend(["", *route_lines])

        trace_line = self._trace_line(result)
        if trace_line:
            lines.append(trace_line)

        return "\n".join(lines)

    def _routing_lines(self, result: dict[str, Any]) -> list[str]:
        routing = result.get("routing")
        if not isinstance(routing, dict):
            trace = result.get("trace")
            if self._is_legacy_direct_trace(trace):
                routing = {
                    "decision": "direct",
                    "source": "legacy",
                    "reason": "legacy backend response; rebuild or restart ai-service",
                }
            else:
                return []

        decision = str(routing.get("decision") or "unknown")
        source = routing.get("source")
        confidence = routing.get("confidence")
        reason = routing.get("reason")
        workflow_id = routing.get("workflowId") or result.get("workflowId")
        run_id = result.get("workflowRunId") or result.get("runId")
        engine = (
            routing.get("runtimeEngine")
            or result.get("runtimeEngine")
        )

        parts = [f"[dim]Route:[/] [bold]{decision}[/]"]
        if source:
            parts.append(f"via {source}")
        if confidence is not None:
            try:
                parts.append(f"conf={float(confidence):.2f}")
            except (TypeError, ValueError):
                pass
        if engine:
            parts.append(f"engine={engine}")
        if workflow_id:
            parts.append(f"workflow={workflow_id}")
        if run_id:
            parts.append(f"run={run_id}")

        lines = ["  " + "  ".join(parts)]
        if reason:
            lines.append(f"  [dim]Reason:[/] {str(reason)[:180]}")
        return lines

    def _trace_line(self, result: dict[str, Any]) -> str:
        trace = result.get("trace")
        if not isinstance(trace, list):
            return ""
        if self._is_legacy_direct_trace(trace):
            return "  [dim]Trace:[/] none"
        if not trace:
            return "  [dim]Trace:[/] none"

        actions: list[str] = []
        for item in trace[:5]:
            if isinstance(item, dict):
                action = item.get("action") or item.get("step")
                if action:
                    actions.append(str(action))
        if not actions:
            return f"  [dim]Trace:[/] {len(trace)} step(s)"

        suffix = "" if len(trace) <= len(actions) else f" +{len(trace) - len(actions)}"
        return f"  [dim]Trace:[/] {' -> '.join(actions)}{suffix}"

    @staticmethod
    def _is_legacy_direct_trace(trace: Any) -> bool:
        return (
            isinstance(trace, list)
            and len(trace) == 1
            and isinstance(trace[0], dict)
            and trace[0].get("action") == "direct_response"
        )

    def _set_mascot(
        self,
        *,
        mood: MascotMood | None = None,
        role: RoleTheme | None = None,
    ) -> None:
        """Update the mascot when the widget is present on the screen."""
        try:
            mascot = self.query_one("#mascot", MascotWidget)
        except Exception:
            return
        if role is not None:
            mascot.role = role
        if mood is not None:
            mascot.mood = mood
