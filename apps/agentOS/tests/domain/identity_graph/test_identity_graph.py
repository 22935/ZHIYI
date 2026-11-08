from __future__ import annotations

import pytest

from domain.identity_graph import (
    IdentityRelation,
    ProvenanceLink,
    TaskBinding,
)
from domain.repository import IdentityConflictError
from runtime import AcgIdentityLifecycleService
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage


def test_task_binding_rejects_node_outside_blueprint() -> None:
    storage = SQLiteV2Storage(":memory:")
    runtime = AcgIdentityLifecycleService(SQLiteV2Repositories(storage))
    try:
        task = runtime.create_mission(user_id="user-1", goal="审查合同")
        node = runtime.create_task(
            mission_id=task.mission_id,
            title="分析风险",
            objective="分析付款风险",
        )
        blueprint = runtime.create_blueprint(
            mission_id=task.mission_id,
            version=1,
            graph_id="runtime_graph_0123456789ab",
            graph={"nodes": [], "edges": []},
        )
        with pytest.raises(IdentityConflictError, match="not contained"):
            runtime.repositories.task_bindings.add(TaskBinding(
                taskId=node.task_id,
                blueprintId=blueprint.blueprint_id,
                acgNodeId="missing-runtime-node",
            ))
    finally:
        runtime.close()


def test_provenance_links_are_directional() -> None:
    storage = SQLiteV2Storage(":memory:")
    repositories = SQLiteV2Repositories(storage)
    try:
        link = ProvenanceLink(
            sourceId="step_execution_0123456789ab",
            targetId="evidence_0123456789ab",
            relationType=IdentityRelation.PRODUCES,
        )
        repositories.provenance_links.add(link)
        assert repositories.provenance_links.list_from(link.source_id) == [link]
        assert repositories.provenance_links.list_to(link.target_id) == [link]
    finally:
        repositories.close()
