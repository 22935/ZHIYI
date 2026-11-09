"""端、边、云放置偏好；仅参与软排序，不替代资格约束。"""

from contracts.resource import Placement


_PLACEMENT_PREFERENCE = {
    Placement.DEVICE: 1.0,
    Placement.EDGE: 0.5,
    Placement.CLOUD: 0.0,
}


def placement_preference(placement: Placement) -> float:
    """返回默认端优先、边缘次之、云端兜底的归一化软偏好。"""
    return _PLACEMENT_PREFERENCE[placement]
