"""受控点位写入通道。

规则：
- 只有具备写入归属的操作者可以提交（鉴权在 router 层完成，本模块只接收
  已识别的 Operator）；
- 每次提交都留下审计记录：谁(operator_id/name)、什么时间(created_at)、
  哪个点位(device/address/name)、改成多少(value)、原值(previous_value)、
  结果(status)与原因(reason)，可按操作者回看；
- 提交前校验：点位存在、点位可写、数值在允许范围内；不满足时给出原因、
  不改变原值，记录 status=failed/retryable=false；
- 同一点位上一次下发尚未结束(pending)时，后来的提交直接判负并提示，以
  先到的一次为准（status=conflict/retryable=true）；
- 下发到设备在后台线程执行（模拟通讯耗时/设备离线），失败可重试：
  retry 复用失败记录，重新走一遍校验与排队。
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.services import point_service
from app.services.operator_service import Operator


class WriteSubmissionError(HTTPException):
    """提交被拒绝：携带已落库的审计记录，便于回看。"""

    def __init__(self, status_code: int, record: Dict[str, Any]):
        super().__init__(status_code=status_code,
                         detail={"reason": record["reason"], "record": dict(record)})

# 模拟下发到设备的通讯耗时，便于观察 pending / 并发冲突
DISPATCH_DELAY_SECONDS = 2.5

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="write-dispatch")

# 审计记录：id -> record；按提交时间倒序保存
_RECORDS: Dict[str, Dict[str, Any]] = {}
_RECORD_ORDER: List[str] = []
_LOCK = threading.RLock()

# 每个点位的在途下发锁：同一点位同时只允许一个 pending
_INFLIGHT: Dict[str, str] = {}  # point_key -> record_id


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _make_record(operator: Operator, point: point_service.PointDef,
                 value: Any, previous_value: Any,
                 retry_of: Optional[str] = None) -> Dict[str, Any]:
    record_id = f"w_{uuid.uuid4().hex[:12]}"
    return {
        "id": record_id,
        "operatorId": operator.id,
        "operatorName": operator.name,
        "deviceId": point.device_id,
        "address": point.address,
        "pointName": point.name,
        "pointKey": point.key,
        "unit": point.unit,
        "value": value,
        "previousValue": previous_value,
        "status": "pending",        # pending | success | failed | conflict
        "reason": None,
        "retryable": False,
        "retryOf": retry_of,
        "createdAt": _now_ms(),
        "createdAtIso": _iso(_now_ms()),
        "finishedAt": None,
        "finishedAtIso": None,
    }


def _serialize(record: Dict[str, Any]) -> Dict[str, Any]:
    return dict(record)


def _finish(record_id: str, status: str, reason: Optional[str],
            retryable: bool, apply_value: bool = False,
            value: Any = None) -> None:
    with _LOCK:
        record = _RECORDS[record_id]
        if apply_value:
            point = point_service.get_point(record["deviceId"], record["address"])
            if point is not None:
                point_service.set_current_value(point, value if value is not None else record["value"])
        record["status"] = status
        record["reason"] = reason
        record["retryable"] = retryable
        record["finishedAt"] = _now_ms()
        record["finishedAtIso"] = _iso(record["finishedAt"])
        if record["pointKey"] in _INFLIGHT and _INFLIGHT[record["pointKey"]] == record_id:
            del _INFLIGHT[record["pointKey"]]


def _dispatch(record_id: str) -> None:
    """后台模拟设备下发。设备离线 -> 失败（可重试）；成功 -> 更新当前值。"""
    with _LOCK:
        record = _RECORDS[record_id]
    time.sleep(DISPATCH_DELAY_SECONDS)

    point = point_service.get_point(record["deviceId"], record["address"])
    if point is None:
        _finish(record_id, "failed", "目标点位已不存在", retryable=False)
        return
    if not point_service.device_online(record["deviceId"]):
        _finish(record_id, "failed",
                f"设备[{record['deviceId']}]离线，下发未送达，原值未改变（可在设备上线后重试）",
                retryable=True)
        return

    # 生产环境此处调用 pymodbus：
    # client.write_register(address, int(value), slave=slave_id)
    value = record["value"]
    if point.type == "coil" and isinstance(value, int):
        value = bool(value)
    _finish(record_id, "success", "下发成功，当前值已更新",
            retryable=False, apply_value=True, value=value)


def _store(record: Dict[str, Any]) -> None:
    with _LOCK:
        _RECORDS[record["id"]] = record
        _RECORD_ORDER.insert(0, record["id"])


def _precheck(operator: Operator, point: Optional[point_service.PointDef],
              value: Any) -> Optional[tuple]:
    """提交前校验。全部不改变原值，且失败不可重试（请求本身不合法）。

    返回 None 表示通过；否则返回 (http_status, reason)。
    """
    if point is None:
        return 422, "目标点位不存在：请检查设备编号与寄存器地址"
    if operator.role != "operator":
        return 403, "当前操作者为只读角色，无下发权限"
    from app.services.operator_service import can_write
    if not can_write(operator, point.key):
        return 403, f"点位[{point.name}]不在操作者[{operator.name}]的写入归属范围内"
    if not point.writable:
        return 403, f"点位[{point.name}]为只读点位，不允许下发"
    ok, reason = point_service.validate_value(point, value)
    if not ok:
        return 422, reason
    return None


def _conflict_reason(inflight_id: str) -> str:
    other = _RECORDS[inflight_id]
    return (f"点位[{other['pointName']}]上一次下发（{other['id']}，"
            f"提交人 {other['operatorName']}）尚未结束，本次提交不生效；"
            f"请等待其结束后再重试，以先到的一次为准")


def submit_write(operator: Operator, device_id: str, address: int,
                 value: Any, retry_of: Optional[str] = None) -> Dict[str, Any]:
    point = point_service.get_point(device_id, address)
    previous_value = point_service.get_current_value(point) if point else None

    # 1) 提交前校验：不满足 -> failed（不可重试），不改变原值；同样留审计
    precheck = _precheck(operator, point, value)
    if precheck is not None:
        status_code, reason = precheck
        record = _make_record(operator, point, value, previous_value, retry_of) \
            if point is not None else _make_unknown_record(operator, device_id, address, value, retry_of)
        record["status"] = "failed"
        record["reason"] = reason
        record["retryable"] = False
        record["finishedAt"] = _now_ms()
        record["finishedAtIso"] = _iso(record["finishedAt"])
        _store(record)
        raise WriteSubmissionError(status_code, record)

    assert point is not None

    with _LOCK:
        # 2) 并发控制：同一点位在途下发只认先到的一次
        inflight_id = _INFLIGHT.get(point.key)
        if inflight_id is not None and _RECORDS[inflight_id]["status"] == "pending":
            record = _make_record(operator, point, value, previous_value, retry_of)
            record["status"] = "conflict"
            record["reason"] = _conflict_reason(inflight_id)
            record["retryable"] = True
            record["finishedAt"] = _now_ms()
            record["finishedAtIso"] = _iso(record["finishedAt"])
            _store(record)
            raise WriteSubmissionError(409, record)

        # 3) 受理：先到的一次进入 pending，后台执行
        record = _make_record(operator, point, value, previous_value, retry_of)
        _store(record)
        _INFLIGHT[point.key] = record["id"]

    _executor.submit(_dispatch, record["id"])
    return _serialize(record)


def _make_unknown_record(operator: Operator, device_id: str, address: int,
                         value: Any, retry_of: Optional[str]) -> Dict[str, Any]:
    record_id = f"w_{uuid.uuid4().hex[:12]}"
    now = _now_ms()
    return {
        "id": record_id,
        "operatorId": operator.id,
        "operatorName": operator.name,
        "deviceId": device_id,
        "address": address,
        "pointName": None,
        "pointKey": f"{device_id}:{address}",
        "unit": "",
        "value": value,
        "previousValue": None,
        "status": "failed",
        "reason": None,
        "retryable": False,
        "retryOf": retry_of,
        "createdAt": now,
        "createdAtIso": _iso(now),
        "finishedAt": None,
        "finishedAtIso": None,
    }


def retry_write(operator: Operator, record_id: str) -> Dict[str, Any]:
    """重试失败/冲突的提交：复用原记录的点位与目标值，重新校验、重新排队。"""
    with _LOCK:
        original = _RECORDS.get(record_id)
        if original is None:
            raise HTTPException(status_code=404, detail={"reason": f"下发记录 {record_id} 不存在"})
        if original["operatorId"] != operator.id:
            raise HTTPException(status_code=403, detail={"reason": "只能重试本人提交的下发记录"})
        if original["status"] in ("pending",):
            raise HTTPException(status_code=409,
                                detail={"reason": "该下发仍在执行中，无需重试", "record": _serialize(original)})
        if original["status"] == "success":
            raise HTTPException(status_code=400,
                                detail={"reason": "该下发已成功，无需重试", "record": _serialize(original)})
        if not original.get("retryable"):
            raise HTTPException(status_code=400,
                                detail={"reason": "该提交属于校验不通过，请修正点位或数值后重新下发",
                                        "record": _serialize(original)})
        payload = (original["deviceId"], original["address"], original["value"], record_id)

    # submit_write 会在失败时抛出带记录的 HTTPException，直接向上传播
    return submit_write(operator, *payload)


def get_record(record_id: str) -> Dict[str, Any]:
    with _LOCK:
        record = _RECORDS.get(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"reason": f"下发记录 {record_id} 不存在"})
        return _serialize(record)


def list_records(operator_id: Optional[str] = None,
                 point_key: Optional[str] = None,
                 limit: int = 100) -> List[Dict[str, Any]]:
    """审计回看：可按操作者、点位过滤。"""
    with _LOCK:
        result = []
        for rid in _RECORD_ORDER:
            record = _RECORDS[rid]
            if operator_id and record["operatorId"] != operator_id:
                continue
            if point_key and record["pointKey"] != point_key:
                continue
            result.append(_serialize(record))
        return result[:limit]
