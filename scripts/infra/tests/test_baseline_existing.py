import pytest

from scripts.infra.baseline_existing import authorize


REPORT = {
    "deploymentId": "kinlin-legacy-001",
    "reportId": "audit-1",
    "fingerprint": "abc123",
    "baselineVersion": 4,
    "state": "legacy",
}


def test_baseline_requires_exact_report_and_unchanged_live_schema():
    authorize(
        REPORT,
        deployment_id="kinlin-legacy-001",
        report_id="audit-1",
        fingerprint="abc123",
        baseline_version=4,
        current={"fingerprint": "abc123", "baselineVersion": 4, "state": "legacy"},
    )


@pytest.mark.parametrize("version", [0, -1])
def test_baseline_zero_or_lower_is_forbidden(version):
    with pytest.raises(ValueError):
        authorize(
            REPORT,
            deployment_id="kinlin-legacy-001",
            report_id="audit-1",
            fingerprint="abc123",
            baseline_version=version,
            current={"fingerprint": "abc123", "baselineVersion": 4, "state": "legacy"},
        )


def test_stale_schema_report_is_rejected():
    with pytest.raises(ValueError, match="live schema changed"):
        authorize(
            REPORT,
            deployment_id="kinlin-legacy-001",
            report_id="audit-1",
            fingerprint="abc123",
            baseline_version=4,
            current={"fingerprint": "changed", "baselineVersion": 4, "state": "legacy"},
        )
