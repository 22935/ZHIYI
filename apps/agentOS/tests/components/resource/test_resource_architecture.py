"""资源器分层迁移期间的公共导入兼容性。"""


def test_resource_contracts_keep_the_legacy_import_surface() -> None:
    from contracts.resource import ExecutionRequirement, Placement, RuntimeProfile

    assert ExecutionRequirement(requiredCapabilities=["compute.run"])
    assert Placement.DEVICE.value == "device"
    assert RuntimeProfile(
        runtimeId="runtime:device:test",
        nodeId="node:device:test",
        capabilities=["compute.run"],
    )
