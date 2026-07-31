import json

import pytest

from scripts.release.check_builder import builder_platforms, current_builder, normalize_arch


def test_architecture_aliases_are_normalized():
    assert normalize_arch("x86_64") == "amd64"
    assert normalize_arch("aarch64") == "arm64"
    with pytest.raises(ValueError):
        normalize_arch("ppc64le")


def test_current_builder_platforms_are_deduplicated():
    payload = "\n".join(
        [
            json.dumps({"Name": "old", "Current": False}),
            json.dumps(
                {
                    "Name": "release",
                    "Current": True,
                    "Nodes": [
                        {"Status": "running", "Platforms": ["linux/amd64", "linux/amd64/v2", "linux/arm64"]},
                        {"Status": "stopped", "Platforms": ["linux/s390x"]},
                    ],
                }
            ),
        ]
    )

    assert builder_platforms(current_builder(payload)) == {"linux/amd64", "linux/arm64"}
