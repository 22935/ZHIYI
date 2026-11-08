"""架构职责名称不变量。"""

from contracts.workflow import RuntimeMissionRecord, RuntimeRunRecord
from runtime import ExecutionRuntime
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge
from support.acg import RuntimeBlueprintSpec


def test_architecture_exports_only_responsibility_names() -> None:
    assert ExecutionRuntime.__name__ == "ExecutionRuntime"
    assert AcgIdentityLifecycleService.__name__ == "AcgIdentityLifecycleService"
    assert IdentityProjectionBridge.__name__ == "IdentityProjectionBridge"
    assert RuntimeMissionRecord.__name__ == "RuntimeMissionRecord"
    assert RuntimeRunRecord.__name__ == "RuntimeRunRecord"
    assert RuntimeBlueprintSpec.__name__ == "RuntimeBlueprintSpec"
