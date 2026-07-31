#!/usr/bin/env python3
"""Read-only PostgreSQL schema fingerprinting and legacy Flyway version classification."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from scripts.infra.common import validate_deployment_id


CORE_COLUMNS = {
    "users": {"id": "uuid", "username": "character varying", "email": "character varying", "password_hash": "character varying", "created_at": "timestamp without time zone", "updated_at": "timestamp without time zone"},
    "roles": {"id": "uuid", "name": "character varying", "description": "text", "role_type": "character varying", "user_id": "uuid", "system_prompt": "text", "dialogue_style": "jsonb", "personality": "jsonb", "avatar_config": "jsonb", "created_at": "timestamp without time zone", "updated_at": "timestamp without time zone"},
    "conversations": {"id": "uuid", "user_id": "uuid", "role_id": "uuid", "context_id": "character varying", "created_at": "timestamp without time zone", "updated_at": "timestamp without time zone"},
    "messages": {"id": "uuid", "conversation_id": "uuid", "role": "character varying", "content": "text", "message_type": "character varying", "metadata": "jsonb", "created_at": "timestamp without time zone"},
}
V1_INDEXES = {"idx_messages_conversation", "idx_messages_created", "idx_roles_type", "idx_roles_user", "idx_conversations_context"}
V2_INDEXES = V1_INDEXES | {
    "idx_users_username", "idx_users_email", "idx_users_created", "idx_conversations_user",
    "idx_conversations_role", "idx_conversations_user_role", "idx_conversations_updated",
    "idx_messages_role", "idx_messages_type", "idx_messages_conversation_created",
    "idx_roles_name", "idx_roles_created", "idx_conversations_user_updated",
}
V4_COLUMNS = {
    "id": "uuid", "user_id": "uuid", "conversation_id": "uuid", "message_id": "uuid",
    "role_id": "uuid", "feedback_type": "character varying", "rating": "integer",
    "content": "text", "sentiment": "character varying", "created_at": "timestamp without time zone",
}
V4_INDEXES = {
    "idx_feedback_user", "idx_feedback_conversation", "idx_feedback_message", "idx_feedback_role",
    "idx_feedback_type", "idx_feedback_sentiment", "idx_feedback_created",
}
ALLOWED_EXTRA_COLUMNS = {
    ("conversations", "title"), ("messages", "file_url"), ("roles", "stable_key"),
}
ALLOWED_TABLES = set(CORE_COLUMNS) | {"user_feedback", "flyway_schema_history"}


def _run_psql(container: str, user: str, database: str, sql: str) -> list[str]:
    command = ["docker", "exec", container, "psql", "-X", "-U", user, "-d", database, "-At", "-F", "\t", "-c", sql]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def snapshot_container(container: str, user: str, database: str) -> dict[str, Any]:
    table_lines = _run_psql(container, user, database, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    column_lines = _run_psql(container, user, database, "SELECT table_name,column_name,data_type,COALESCE(character_maximum_length::text,''),is_nullable,COALESCE(column_default,'') FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
    index_lines = _run_psql(container, user, database, "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname")
    columns: dict[str, dict[str, dict[str, str]]] = {}
    for line in column_lines:
        table, name, data_type, length, nullable, default = line.split("\t", 5)
        columns.setdefault(table, {})[name] = {"type": data_type, "length": length, "nullable": nullable, "default": default}
    indexes = [{"table": parts[0], "name": parts[1], "definition": parts[2]} for line in index_lines if len(parts := line.split("\t", 2)) == 3]
    history = []
    if "flyway_schema_history" in table_lines:
        history = _run_psql(container, user, database, "SELECT installed_rank,COALESCE(version,''),description,type,script,checksum,success FROM flyway_schema_history ORDER BY installed_rank")
    return {"tables": table_lines, "columns": columns, "indexes": indexes, "flywayHistory": history}


def _check_columns(actual: dict[str, Any], expected: dict[str, dict[str, str]], errors: list[str]) -> None:
    for table, expected_columns in expected.items():
        actual_columns = actual.get(table, {})
        for name, expected_type in expected_columns.items():
            item = actual_columns.get(name)
            if item is None:
                errors.append(f"missing column {table}.{name}")
            elif item.get("type") != expected_type:
                errors.append(f"type drift {table}.{name}: expected {expected_type}, got {item.get('type')}")


def classify(snapshot: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    tables = set(snapshot.get("tables", []))
    if not tables:
        return {"state": "empty", "baselineVersion": None, "fingerprint": fingerprint, "errors": []}
    if "flyway_schema_history" in tables:
        history = snapshot.get("flywayHistory", [])
        if not history:
            return {"state": "drift", "baselineVersion": None, "fingerprint": fingerprint, "errors": ["flyway history table exists but is empty"]}
        return {"state": "managed", "baselineVersion": None, "fingerprint": fingerprint, "errors": [], "history": history}

    errors: list[str] = []
    unknown_tables = tables - ALLOWED_TABLES
    if unknown_tables:
        errors.append(f"unknown tables: {sorted(unknown_tables)}")
    _check_columns(snapshot.get("columns", {}), CORE_COLUMNS, errors)
    for table, actual_columns in snapshot.get("columns", {}).items():
        expected = CORE_COLUMNS.get(table, V4_COLUMNS if table == "user_feedback" else {})
        for column in actual_columns:
            if column not in expected and (table, column) not in ALLOWED_EXTRA_COLUMNS:
                errors.append(f"unknown column {table}.{column}")

    indexes = {item["name"] for item in snapshot.get("indexes", [])}
    if not V1_INDEXES.issubset(indexes):
        errors.append(f"V1 indexes incomplete: {sorted(V1_INDEXES - indexes)}")
    baseline = 1
    if V2_INDEXES.issubset(indexes):
        baseline = 3  # V3 is structurally redundant when password_hash already exists.
    elif indexes & (V2_INDEXES - V1_INDEXES):
        errors.append("partial V2 index set")
    if "user_feedback" in tables:
        _check_columns(snapshot.get("columns", {}), {"user_feedback": V4_COLUMNS}, errors)
        if not V4_INDEXES.issubset(indexes):
            errors.append(f"V4 indexes incomplete: {sorted(V4_INDEXES - indexes)}")
        baseline = 4
    elif indexes & V4_INDEXES:
        errors.append("feedback indexes exist without user_feedback table")
    return {
        "state": "drift" if errors else "legacy",
        "baselineVersion": None if errors else baseline,
        "fingerprint": fingerprint,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--database", default="kinlin_ai")
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if bool(args.container) == bool(args.snapshot):
        parser.error("provide exactly one of --container or --snapshot")
    deployment_id = validate_deployment_id(args.deployment_id)
    snapshot = snapshot_container(args.container, args.user, args.database) if args.container else json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    result = classify(snapshot)
    result.update({"reportId": str(uuid.uuid4()), "deploymentId": deployment_id, "database": args.database, "snapshot": snapshot})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("reportId", "state", "baselineVersion", "fingerprint", "errors")}, ensure_ascii=False))
    return 0 if result["state"] != "drift" else 2


if __name__ == "__main__":
    raise SystemExit(main())
