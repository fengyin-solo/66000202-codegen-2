"""受控点位下发通道：提交前校验、同点位串行化、全量审计。

- 每次提交（无论成败）都会留下审计记录：谁、什么时间、哪个点位、改成多少、结果与原因；
- 校验不通过时不改变点位原值；
- 同一点位上一次下发未结束时，后来的提交被拒绝并提示，以先到的一次为准；
- 失败/冲突的提交可再次提交（重试）。
"""
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.modbus_service import get_device, get_point

WRITE_LATENCY = 0.8  # 模拟一次设备写入的耗时（秒），期间同一点位的其他提交会被拒绝

STATUS_SUCCESS = "success"    # 下发成功
STATUS_FAILED = "failed"      # 校验不通过，原值未改变
STATUS_CONFLICT = "conflict"  # 同一点位有正在进行的下发，以先到的为准
STATUS_FORBIDDEN = "forbidden"# 无写入权限（只读查看者）

_locks: Dict[Tuple[str, int], asyncio.Lock] = {}
_records: List[Dict[str, Any]] = []
_seq = 0


def _lock_for(key: Tuple[str, int]) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _new_record(operator: Dict[str, Any], device_id: str, address: int, value: float) -> Dict[str, Any]:
    global _seq
    _seq += 1
    return {
        "id": f"w_{_seq:06d}",
        "operator": operator["username"],
        "operator_name": operator["display_name"],
        "device_id": device_id,
        "address": address,
        "point_name": None,
        "value": value,
        "old_value": None,
        "status": None,
        "reason": "",
        "timestamp": int(time.time() * 1000),
    }


def _save(record: Dict[str, Any]) -> Dict[str, Any]:
    _records.append(record)
    return record


async def submit_write(operator: Dict[str, Any], device_id: str, address: int, value: float):
    """提交一次点位下发，返回 (record, http_status)。任何提交都会留下审计记录。"""
    record = _new_record(operator, device_id, address, value)

    if get_device(device_id) is None:
        record.update(status=STATUS_FAILED, reason=f"目标设备不存在: {device_id}，原值未改变")
        return _save(record), 404

    point = get_point(device_id, address)
    if point is None:
        record.update(status=STATUS_FAILED, reason=f"目标点位不存在: {device_id} 地址 `{address}`，原值未改变")
        return _save(record), 404
    record["point_name"] = point["name"]

    if not point["writable"]:
        record.update(status=STATUS_FAILED, reason=f"点位「{point['name']}」为只读测量点，不允许下发，原值未改变")
        return _save(record), 400

    if not (point["min"] <= value <= point["max"]):
        record.update(
            status=STATUS_FAILED,
            reason=f"数值 {value} 超出允许范围 [{point['min']}, {point['max']}]，原值未改变",
        )
        return _save(record), 400

    lock = _lock_for((device_id, address))
    if lock.locked():
        record.update(status=STATUS_CONFLICT, reason="该点位上一次下发尚未结束，已以先到的一次为准，请稍后重试")
        return _save(record), 409

    async with lock:
        record["old_value"] = point["value"]
        # In production: client.write_register(address, value, slave=slave_id)
        await asyncio.sleep(WRITE_LATENCY)  # 模拟设备写入耗时
        point["value"] = value
        record["status"] = STATUS_SUCCESS
        record["reason"] = "下发成功"
    return _save(record), 200


def record_forbidden_attempt(operator: Dict[str, Any], device_id: str, address: int, value: float) -> Dict[str, Any]:
    """只读查看者的下发尝试同样留痕，但不改变任何点位。"""
    record = _new_record(operator, device_id, address, value)
    point = get_point(device_id, address)
    record["point_name"] = point["name"] if point else None
    record.update(status=STATUS_FORBIDDEN, reason="只读查看者无权下发点位，原值未改变")
    return _save(record)


def query_records(operator: Optional[str] = None, device_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """按操作者（可选设备）回看下发记录，最新的在前。"""
    records = _records
    if operator:
        records = [r for r in records if r["operator"] == operator]
    if device_id:
        records = [r for r in records if r["device_id"] == device_id]
    return sorted(records, key=lambda r: (r["timestamp"], r["id"]), reverse=True)
