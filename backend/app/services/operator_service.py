"""操作者与写入归属管理（演示版，内存存储）。

生产环境应对接统一身份认证；这里用固定名单 + 请求头 X-Operator-Id
来标识当前操作者。只有 role == "operator" 且拥有目标点位归属的操作者
才能提交下发；viewer 只读。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Operator:
    id: str
    name: str
    role: str  # "operator" | "viewer"
    owned_points: Set[str] = field(default_factory=set)


# 点位归属使用 "device_id:address" 作为全局点位键
_ALL_POINT_KEYS = {
    "dev1:0", "dev1:1", "dev1:2",
    "dev2:0", "dev2:1",
    "dev3:0", "dev3:1", "dev3:2",
}

_OPERATORS: Dict[str, Operator] = {
    "op001": Operator(
        id="op001", name="张工（A区运维）", role="operator",
        owned_points={"dev1:0", "dev1:1", "dev1:2"},
    ),
    "op002": Operator(
        id="op002", name="李工（B区运维）", role="operator",
        owned_points={"dev2:0", "dev2:1"},
    ),
    "op003": Operator(
        id="op003", name="王工（C区运维）", role="operator",
        owned_points={"dev3:0", "dev3:1", "dev3:2"},
    ),
    "viewer001": Operator(
        id="viewer001", name="访客（只读）", role="viewer", owned_points=set(),
    ),
}


def list_operators() -> List[Operator]:
    return list(_OPERATORS.values())


def get_operator(operator_id: Optional[str]) -> Optional[Operator]:
    if not operator_id:
        return None
    return _OPERATORS.get(operator_id)


def can_write(operator: Operator, point_key: str) -> bool:
    """具备写入归属：操作者角色 + 该点位在其归属名单内。"""
    return operator.role == "operator" and point_key in operator.owned_points


def serialize(operator: Operator) -> Dict:
    return {
        "id": operator.id,
        "name": operator.name,
        "role": operator.role,
        "ownedPoints": sorted(operator.owned_points),
    }


def all_point_keys() -> Set[str]:
    return set(_ALL_POINT_KEYS)
