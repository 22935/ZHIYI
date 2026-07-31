"""Async HTTP client for the AgentOS FastAPI backend."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, Optional

import httpx


class AgentOSClient:
    """Async HTTP client for the AgentOS API.

    Usage::

        async with AgentOSClient() as client:
            tasks = await client.list_tasks()
            run = await client.start_workflow("audit", "legal", "contract_review")
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000/ai") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(60.0),
            trust_env=False,
        )

    async def __aenter__(self) -> "AgentOSClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        """Manually close the underlying httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Issue an HTTP request and return the JSON body.

        On any error returns ``{"error": "<message>"}`` so callers never
        have to deal with raw exceptions.
        """
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                payload = exc.response.json()
                if isinstance(payload, dict):
                    detail = str(
                        payload.get("detail")
                        or payload.get("message")
                        or payload.get("error")
                        or payload
                    )
                else:
                    detail = str(payload)
            except Exception:
                detail = exc.response.text.strip()
            if not detail:
                detail = str(exc)
            return {"error": detail}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def create_task(
        self,
        title: str,
        domain: str,
        intent: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Create a new task.

        Extra keyword arguments are forwarded as body fields:
        ``role_type``, ``task_type``, ``input`` (dict), ``security_level``,
        ``priority``.
        """
        body: Dict[str, Any] = {
            "title": title,
            "domain": domain,
            "intent": intent,
        }
        # Merge recognised optional fields.
        for key in ("role_type", "task_type", "input", "security_level", "priority"):
            if key in kwargs:
                body[key] = kwargs.pop(key)
        # Accept snake_case aliases that the API also understands via its
        # camelCase model validators so callers can use either style.
        for key in ("roleType", "taskType", "securityLevel"):
            if key in kwargs:
                body[key] = kwargs.pop(key)
        body.update(kwargs)
        return await self._request("POST", "/core/tasks", json=body)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List tasks with optional filtering."""
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if status is not None:
            params["status"] = status
        if domain is not None:
            params["domain"] = domain
        return await self._request("GET", "/core/tasks", params=params)

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    async def start_workflow(
        self,
        title: str,
        domain: str,
        intent: str,
        role_type: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        review_mode: str = "auto",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Create a task and immediately start its workflow.

        Returns a dict with ``task`` and ``run`` keys.
        """
        body: Dict[str, Any] = {
            "title": title,
            "domain": domain,
            "intent": intent,
            "input": input_data or {},
            "security_level": kwargs.pop("security_level", "internal"),
            "priority": kwargs.pop("priority", "normal"),
            "review_mode": review_mode,
        }
        if role_type is not None:
            body["role_type"] = role_type
        if workflow_id is not None:
            body["workflow_id"] = workflow_id
        # Allow callers to pass task_type or camelCase equivalents.
        for key in ("task_type", "taskType"):
            if key in kwargs:
                body[key] = kwargs.pop(key)
        body.update(kwargs)
        return await self._request("POST", "/core/workflows/start", json=body)

    async def list_workflow_runs(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        workflow_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List workflow runs with optional filtering."""
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if status is not None:
            params["status"] = status
        if domain is not None:
            params["domain"] = domain
        if workflow_id is not None:
            params["workflowId"] = workflow_id
        return await self._request("GET", "/core/workflows/runs", params=params)

    async def get_workflow_run(self, run_id: str) -> Dict[str, Any]:
        """Get a single workflow run by ID."""
        return await self._request("GET", f"/core/workflows/runs/{run_id}")

    async def get_checkpoints(self, run_id: str) -> Dict[str, Any]:
        """List checkpoints for a workflow run."""
        return await self._request(
            "GET", f"/core/workflows/runs/{run_id}/checkpoints"
        )

    async def get_trace(
        self,
        run_id: str,
        format: str = "json",  # noqa: A002  -- API parameter name
    ) -> Any:
        """Export the execution trace.

        When *format* is ``"markdown"`` the server returns plain text;
        the method returns that text as a string.  Otherwise it returns a
        parsed JSON dict.
        """
        path = f"/core/workflows/runs/{run_id}/trace"
        try:
            response = await self._client.get(
                path, params={"format": format}
            )
            response.raise_for_status()
            if format == "markdown":
                return response.text
            return response.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except Exception:
                detail = str(exc)
            return {"error": detail}
        except Exception as exc:
            return {"error": str(exc)}

    async def get_reviews(self, run_id: str) -> Dict[str, Any]:
        """List reviews for a workflow run."""
        return await self._request(
            "GET", f"/core/workflows/runs/{run_id}/reviews"
        )

    async def submit_review(
        self,
        run_id: str,
        step_id: str,
        decision: str,
        reviewer: str = "user",
        comment: str = "",
    ) -> Dict[str, Any]:
        """Submit a human-in-the-loop review decision."""
        body: Dict[str, Any] = {
            "step_id": step_id,
            "decision": decision,
            "reviewer": reviewer,
            "comment": comment,
        }
        return await self._request(
            "POST",
            f"/core/workflows/runs/{run_id}/reviews",
            json=body,
        )

    async def resume_workflow(
        self,
        run_id: str,
        checkpoint_id: str,
    ) -> Dict[str, Any]:
        """Resume a suspended workflow from a checkpoint."""
        return await self._request(
            "POST",
            f"/core/workflows/runs/{run_id}/resume",
            json={"checkpoint_id": checkpoint_id},
        )

    async def cancel_workflow(self, run_id: str) -> Dict[str, Any]:
        """Cancel a running workflow."""
        return await self._request(
            "POST", f"/core/workflows/runs/{run_id}/cancel"
        )

    # ------------------------------------------------------------------
    # Legacy agent chat
    # ------------------------------------------------------------------

    ALLOWED_ROLES = {"lawyer", "teacher", "programmer", "writer"}

    async def agent_chat(
        self,
        role: str,
        text: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Legacy agent chat endpoint.

        *role* is one of ``lawyer``, ``teacher``, ``programmer``, ``writer``.
        """
        if role not in self.ALLOWED_ROLES:
            return {"error": f"Invalid role '{role}'. Must be: {sorted(self.ALLOWED_ROLES)}"}
        body: Dict[str, Any] = {"text": text}
        if session_id is not None:
            body["session_id"] = session_id
        return await self._request(
            "POST", f"/agent/{role}/chat", json=body
        )

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        text: str,
        role_id: Optional[str] = None,
        context: Optional[list[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completions via SSE.

        Yields each ``delta`` token as it arrives.  Stops when the server
        sends ``data: [DONE]``.
        """
        body: Dict[str, Any] = {"text": text}
        if role_id is not None:
            body["role_id"] = role_id
        if context is not None:
            body["context"] = context

        try:
            async with self._client.stream(
                "POST", "/chat/text/stream", json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        return
                    if line.startswith("data: "):
                        payload = line[len("data: "):]
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if "error" in data:
                            yield f"[ERROR] {data['error']}"
                            return
                        delta = data.get("delta")
                        if delta is not None:
                            yield delta
        except httpx.HTTPStatusError as exc:
            yield f"[ERROR] {exc}"
        except Exception as exc:
            yield f"[ERROR] {exc}"
