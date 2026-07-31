import pytest

from scripts.infra.common import validate_deployment_id, volume_names


def test_deployment_id_is_embedded_in_every_volume():
    volumes = volume_names("kinlin-test-001")
    assert volumes
    assert all(name.startswith("kinlin-test-001_") for name in volumes.values())


@pytest.mark.parametrize("value", ["", "PROD", "a", "kinlin_prod", "0.0.0.0"])
def test_invalid_deployment_ids_are_rejected(value):
    with pytest.raises(ValueError):
        validate_deployment_id(value)
