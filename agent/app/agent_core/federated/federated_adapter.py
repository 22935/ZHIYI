import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class FederatedAdapter:
    """Fail-open adapter for optional federated enhancement calls."""

    def __init__(self) -> None:
        self.enabled = os.getenv("AGENT_FEDERATED_ENABLED", "false").strip().lower() == "true"
        self.base_url = os.getenv("AGENT_FEDERATED_BASE_URL", "http://localhost:8000/ai").rstrip("/")
        timeout_ms = os.getenv("AGENT_FEDERATED_TIMEOUT_MS", "1500")
        try:
            parsed_timeout = int(timeout_ms)
        except ValueError:
            parsed_timeout = 1500
        self.timeout = max(0.2, parsed_timeout / 1000.0)
        self.optimize_paths = ["/federated-models/optimize", "/federated-model/optimize"]
        self.clients_path = "/global-model/clients"

    async def _post_optimize(self, client: httpx.AsyncClient, case_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = {
            "model_type": "advanced",
            "optimization_method": "federated",
            "target_metric": "quality",
            "epochs": 1,
            "case_features": case_info,
        }
        for path in self.optimize_paths:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            if response.status_code == 200:
                return response.json()
        return None

    async def _get_clients(self, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        response = await client.get(f"{self.base_url}{self.clients_path}")
        if response.status_code == 200:
            return response.json()
        return None

    async def get_risk_enhancement(self, case_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return federated enhancement payload.
        Any failure must not break the main pipeline, so this method returns {} on errors.
        """
        if not self.enabled:
            return {}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                optimize_data = await self._post_optimize(client, case_info or {}) or {}
                clients_data = await self._get_clients(client) or {}

            optimize_block = optimize_data.get("data", optimize_data) if isinstance(optimize_data, dict) else {}
            improvements = optimize_block.get("improvements", {}) if isinstance(optimize_block, dict) else {}

            # Risk adjustment convention: positive increases risk, negative decreases risk.
            # Federated optimization usually improves accuracy, thus tends to reduce risk.
            improvement_accuracy = float(improvements.get("accuracy", 0.0) or 0.0)
            improvement_efficiency = float(improvements.get("efficiency", 0.0) or 0.0)
            raw_adjustment = -(improvement_accuracy * 0.5 + improvement_efficiency * 0.3)
            risk_adjustment = max(-0.15, min(0.15, raw_adjustment))

            stats_block = clients_data.get("statistics", clients_data) if isinstance(clients_data, dict) else {}
            active_clients = int(stats_block.get("active_clients", 0) or 0)
            total_clients = int(stats_block.get("total_clients", 0) or 0)
            federated_nodes_count = max(active_clients, total_clients)

            confidence = float(optimize_block.get("confidence", 0.0) or 0.0)
            if confidence <= 0:
                confidence = min(0.95, 0.55 + 0.04 * federated_nodes_count + max(0.0, improvement_accuracy))

            return {
                "risk_adjustment": round(risk_adjustment, 4),
                "confidence": round(confidence, 4),
                "federated_nodes_count": federated_nodes_count,
            }
        except Exception as exc:
            logger.warning("Federated enhancement failed: %s", exc)
            return {}
