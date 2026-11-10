"""资源商店目录与安装任务合同。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from components.marketplace.contracts import CatalogItem, InstallationJob, InstallationStatus


def test_catalog_item_rejects_package_escape_and_invalid_checksum() -> None:
    with pytest.raises(ValidationError):
        CatalogItem(
            catalogId="model.demo",
            kind="model_server",
            version="1.0.0",
            packagePath="../escape",
            sha256="bad",
            runtime={},
        )


def test_job_only_advances_through_installation_lifecycle() -> None:
    job = InstallationJob.new("job-1", "model.demo", "tenant-a")

    job = job.advance(InstallationStatus.INSTALLING)
    assert job.status is InstallationStatus.INSTALLING
    job = job.advance(InstallationStatus.REGISTERING)
    assert job.status is InstallationStatus.REGISTERING
    with pytest.raises(ValueError, match="invalid installation status transition"):
        job.advance(InstallationStatus.QUEUED)
