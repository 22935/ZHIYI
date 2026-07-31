from scripts.infra.schema_audit import CORE_COLUMNS, V1_INDEXES, V2_INDEXES, V4_COLUMNS, V4_INDEXES, classify


def snapshot(*, version: int, partial_v2: bool = False):
    columns = {table: {name: {"type": value} for name, value in values.items()} for table, values in CORE_COLUMNS.items()}
    tables = list(CORE_COLUMNS)
    indexes = set(V1_INDEXES)
    if version >= 2:
        indexes = set(V2_INDEXES)
    if partial_v2:
        indexes.add("idx_users_username")
    if version >= 4:
        tables.append("user_feedback")
        columns["user_feedback"] = {name: {"type": value} for name, value in V4_COLUMNS.items()}
        indexes.update(V4_INDEXES)
    return {"tables": tables, "columns": columns, "indexes": [{"table": "x", "name": name, "definition": name} for name in sorted(indexes)], "flywayHistory": []}


def test_empty_database_never_requests_baseline():
    result = classify({"tables": [], "columns": {}, "indexes": [], "flywayHistory": []})
    assert result["state"] == "empty"
    assert result["baselineVersion"] is None


def test_v1_and_v4_are_classified_deterministically():
    assert classify(snapshot(version=1))["baselineVersion"] == 1
    assert classify(snapshot(version=4))["baselineVersion"] == 4


def test_partial_migration_is_rejected():
    result = classify(snapshot(version=1, partial_v2=True))
    assert result["state"] == "drift"
    assert "partial V2 index set" in result["errors"]
