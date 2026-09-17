"""点位目录与当前值管理。

下发前的两类前置校验在这里完成：
1. 目标点位是否存在（设备/地址是否已登记）；
2. 写入值是否在允许范围内（min/max，含布尔量点位的合法性）。
当前值保存在内存里：实时读取对已登记点位返回当前值，下发成功后当前值
被更新，因此刷新页面 / 重新读取仍能看到下发结果；校验未通过时当前值
原样保留。
"""
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.modbus_service import MOCK_DEVICES

_POINT_LOCK = threading.RLock()


@dataclass
class PointDef:
    device_id: str
    address: int
    name: str
    type: str            # holding | coil
    unit: str
    writable: bool
    min_value: Optional[float]
    max_value: Optional[float]
    value: Any           # 当前值

    @property
    def key(self) -> str:
        return f"{self.device_id}:{self.address}"


def _p(device_id: str, address: int, name: str, ptype: str, unit: str,
       writable: bool, min_value: Optional[float], max_value: Optional[float],
       value: Any) -> PointDef:
    return PointDef(device_id, address, name, ptype, unit, writable,
                    min_value, max_value, value)


# 已登记的点位目录（与前端点位口径一致）
_POINTS: Dict[str, PointDef] = {p.key: p for p in [
    _p("dev1", 0, "温度", "holding", "°C", True, -40, 125, 25.6),
    _p("dev1", 1, "湿度", "holding", "%RH", True, 0, 100, 62.3),
    _p("dev1", 2, "露点", "holding", "°C", True, -40, 125, 17.8),
    _p("dev2", 0, "管道压力", "holding", "MPa", True, 0, 10, 3.45),
    _p("dev2", 1, "差压", "holding", "kPa", False, -50, 50, 0.12),
    _p("dev3", 0, "转速", "holding", "RPM", True, 0, 3000, 1480),
    _p("dev3", 1, "电流", "holding", "A", True, 0, 50, 12.5),
    _p("dev3", 2, "运行状态", "coil", "", True, None, None, True),
]}


def device_online(device_id: str) -> bool:
    for dev in MOCK_DEVICES:
        if dev["id"] == device_id:
            return bool(dev["online"])
    return False


def get_point(device_id: str, address: int) -> Optional[PointDef]:
    return _POINTS.get(f"{device_id}:{address}")


def list_points() -> List[PointDef]:
    return list(_POINTS.values())


def get_current_value(point: PointDef) -> Any:
    with _POINT_LOCK:
        return point.value


def set_current_value(point: PointDef, value: Any) -> None:
    with _POINT_LOCK:
        point.value = value


def validate_value(point: PointDef, value: Any) -> Tuple[bool, str]:
    """校验写入值类型与量程；返回 (是否合法, 原因)。"""
    if point.type == "coil":
        if isinstance(value, bool):
            return True, ""
        if isinstance(value, int) and value in (0, 1):
            return True, ""
        return False, f"点位[{point.name}]是布尔量（ON/OFF），仅接受 true/false 或 1/0，收到: {value!r}"

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, f"点位[{point.name}]需要数值类型，收到: {value!r}"
    fvalue = float(value)
    if fvalue != fvalue:  # NaN
        return False, f"点位[{point.name}]不能写入 NaN"
    if point.min_value is not None and fvalue < point.min_value:
        return False, (f"点位[{point.name}]写入值 {fvalue} 低于允许下限 "
                       f"{point.min_value}{point.unit}")
    if point.max_value is not None and fvalue > point.max_value:
        return False, (f"点位[{point.name}]写入值 {fvalue} 高于允许上限 "
                       f"{point.max_value}{point.unit}")
    return True, ""


def serialize(point: PointDef) -> Dict:
    return {
        "deviceId": point.device_id,
        "address": point.address,
        "name": point.name,
        "type": point.type,
        "unit": point.unit,
        "writable": point.writable,
        "minValue": point.min_value,
        "maxValue": point.max_value,
        "value": get_current_value(point),
        "online": device_online(point.device_id),
    }
