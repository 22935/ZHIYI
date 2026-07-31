"""Regression tests for the TUI app shell and chat screen."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual.widgets import DataTable, Input, RichLog

from kinlin_tui.app import AgentOSTuiApp, _parse_args
from kinlin_tui.mascot import (
    MASCOT_FRAME_HEIGHT,
    MASCOT_FRAME_WIDTH,
    MascotCharacter,
    MascotMood,
    WELCOME_BANNER,
    get_mascot,
)
from kinlin_tui.theme import RoleTheme
from kinlin_tui.widgets.mascot_widget import MascotWidget


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def agent_chat(
        self,
        role: str,
        text: str,
        session_id: str | None = None,
    ) -> dict[str, str]:
        self.calls.append((role, text, session_id))
        return {"answer": "pong", "sessionId": "session-1"}

    async def close(self) -> None:
        pass


class RoutingClient(FakeClient):
    async def agent_chat(
        self,
        role: str,
        text: str,
        session_id: str | None = None,
    ) -> dict:
        self.calls.append((role, text, session_id))
        return {
            "answer": "contract review summary",
            "sessionId": "session-route",
            "workflowId": "legal_contract_review_v1",
            "workflowRunId": "run-route-1",
            "runtimeEngine": "acg",
            "routing": {
                "decision": "workflow",
                "source": "llm",
                "confidence": 0.92,
                "workflowId": "legal_contract_review_v1",
                "reason": "用户明确要求审查合同。",
            },
            "trace": [
                {"action": "parse_contract"},
                {"action": "risk_detect"},
                {"action": "legal_evidence_match"},
            ],
        }


class LegacyDirectTraceClient(FakeClient):
    async def agent_chat(
        self,
        role: str,
        text: str,
        session_id: str | None = None,
    ) -> dict:
        self.calls.append((role, text, session_id))
        return {
            "answer": "hello direct answer",
            "sessionId": "session-direct",
            "trace": [{"action": "direct_response"}],
        }


class DashboardClient(FakeClient):
    async def list_workflow_runs(self) -> dict:
        return {
            "items": [
                {
                    "runId": "run_one",
                    "workflowId": "legal_case_analysis_v1",
                    "domain": "legal",
                    "status": "completed",
                    "steps": [{"status": "completed"}],
                },
                {
                    "runId": "run_two",
                    "workflowId": "legal_case_analysis_v1",
                    "domain": "legal",
                    "status": "completed",
                    "steps": [{"status": "completed"}],
                },
            ]
        }


def test_bare_role_args_default_to_os_command() -> None:
    _parser, args = _parse_args(["--role", "teacher"])

    assert args.command == "os"
    assert args.role == "teacher"


def test_chat_submit_calls_agent_and_renders_reply() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        fake_client = FakeClient()
        app.api_client = fake_client  # type: ignore[assignment]

        async with app.run_test(size=(100, 30)) as pilot:
            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "hello"

            await pilot.press("enter")
            await pilot.pause(0.1)

            log = app.screen.query_one("#message-log", RichLog)
            rendered_text = "\n".join(line.text for line in log.lines)

        assert fake_client.calls == [("lawyer", "hello", None)]
        assert "You: hello" in rendered_text
        assert "ZhiYi:" in rendered_text
        assert "pong" in rendered_text

    asyncio.run(scenario())


def test_chat_reuses_returned_session_id() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        fake_client = FakeClient()
        app.api_client = fake_client  # type: ignore[assignment]

        async with app.run_test(size=(100, 30)) as pilot:
            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "first"
            await pilot.press("enter")
            await pilot.pause(0.1)

            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "second"
            await pilot.press("enter")
            await pilot.pause(0.1)

        assert fake_client.calls == [
            ("lawyer", "first", None),
            ("lawyer", "second", "session-1"),
        ]

    asyncio.run(scenario())


def test_chat_renders_routing_and_trace_metadata() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        app.api_client = RoutingClient()  # type: ignore[assignment]

        async with app.run_test(size=(120, 34)) as pilot:
            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "审查这份软件开发合同"

            await pilot.press("enter")
            await pilot.pause(0.1)

            log = app.screen.query_one("#message-log", RichLog)
            rendered_text = "\n".join(line.text for line in log.lines)

        assert "contract review summary" in rendered_text
        assert "Route:" in rendered_text
        assert "workflow" in rendered_text
        assert "via llm" in rendered_text
        assert "engine=acg" in rendered_text
        assert "workflow=legal_contract_review_v1" in rendered_text
        assert "run=run-route-1" in rendered_text
        assert "Trace:" in rendered_text
        assert "parse_contract -> risk_detect -> legal_evidence_match" in rendered_text

    asyncio.run(scenario())


def test_chat_treats_legacy_direct_response_trace_as_no_workflow_trace() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        app.api_client = LegacyDirectTraceClient()  # type: ignore[assignment]

        async with app.run_test(size=(120, 34)) as pilot:
            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "你好"

            await pilot.press("enter")
            await pilot.pause(0.1)

            log = app.screen.query_one("#message-log", RichLog)
            rendered_text = "\n".join(line.text for line in log.lines)

        assert "hello direct answer" in rendered_text
        assert "Route:" in rendered_text
        assert "direct" in rendered_text
        assert "via legacy" in rendered_text
        assert "Trace: none" in rendered_text
        assert "direct_response" not in rendered_text

    asyncio.run(scenario())


def test_chat_mascot_mounts_and_tracks_role_and_reply_state() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        fake_client = FakeClient()
        app.api_client = fake_client  # type: ignore[assignment]

        async with app.run_test(size=(100, 30)) as pilot:
            mascot = app.screen.query_one("#mascot", MascotWidget)
            assert mascot.mood == MascotMood.IDLE
            assert mascot.role == RoleTheme.LAWYER

            await pilot.press("f2")
            await pilot.pause(0.1)
            assert mascot.role == RoleTheme.TEACHER
            assert mascot.mood == MascotMood.IDLE

            input_widget = app.screen.query_one("#chat-input", Input)
            input_widget.value = "hello"
            await pilot.press("enter")
            await pilot.pause(0.1)

            assert fake_client.calls == [("teacher", "hello", None)]
            assert mascot.role == RoleTheme.TEACHER
            assert mascot.mood == MascotMood.HAPPY

    asyncio.run(scenario())


def test_mascot_frames_are_clean_ascii_and_consistent() -> None:
    for character in MascotCharacter:
        for mood in MascotMood:
            frame = get_mascot(mood, character)
            rendered = [Text.from_markup(line).plain for line in frame]

            assert len(frame) == MASCOT_FRAME_HEIGHT
            assert all(line.isascii() for line in frame)
            assert all(line.isascii() for line in rendered)
            assert all(len(line) == MASCOT_FRAME_WIDTH for line in rendered)
            assert not any("[/" in line or "[bold" in line for line in rendered)

    # Welcome banners contain Chinese text and emoji — verify structure.
    for character in MascotCharacter:
        banner = WELCOME_BANNER.get(character, [])
        assert isinstance(banner, list)
        assert all(isinstance(line, str) and len(line) > 0 for line in banner)
    assert "o     o" in "\n".join(get_mascot(MascotMood.IDLE))


def test_dashboard_accepts_camel_case_run_ids() -> None:
    async def scenario() -> None:
        app = AgentOSTuiApp()
        await app.api_client.close()

        app.api_client = DashboardClient()  # type: ignore[assignment]

        async with app.run_test(size=(100, 30)) as pilot:
            await app.push_screen("dashboard")
            await pilot.pause(0.2)

            table = app.screen.query_one("#runs-table", DataTable)
            assert table.row_count == 2

    asyncio.run(scenario())
