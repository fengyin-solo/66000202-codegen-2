from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.models.schemas import WriteRequest
from app.services import point_service, write_service, operator_service
from app.services.modbus_service import read_registers, get_device_status, MOCK_DEVICES
from app.services.operator_service import Operator

router = APIRouter()


def require_operator(x_operator_id: Optional[str] = Header(default=None)) -> Operator:
    """从请求头 X-Operator-Id 识别操作者；无法识别一律拒绝下发。"""
    operator = operator_service.get_operator(x_operator_id)
    if operator is None:
        raise HTTPException(
            status_code=401,
            detail={"reason": "缺少或无效的操作者标识（请求头 X-Operator-Id），拒绝下发"},
        )
    return operator


def require_writer(operator: Operator = Depends(require_operator)) -> Operator:
    """只有具备写入角色的操作者能访问下发/审计通道；只读查看者仅能看实时读数。"""
    if operator.role != "operator":
        raise HTTPException(status_code=403, detail={"reason": "只读查看者仅可查看实时读数，无下发与审计访问权限"})
    return operator


# ---------------------------------------------------------------------------
# 只读接口（口径不变，无需身份）：设备状态 / 实时读取
# ---------------------------------------------------------------------------
@router.get("/modbus/devices")
def list_devices():
    return get_device_status()


@router.get("/modbus/read/{device_id}/{address}/{count}")
def read_holding(device_id: str, address: int, count: int = 1):
    """Read holding registers from a Modbus device."""
    return read_registers(device_id, address, count)


# ---------------------------------------------------------------------------
# 身份与点位目录
# ---------------------------------------------------------------------------
@router.get("/operators")
def operators():
    return [operator_service.serialize(op) for op in operator_service.list_operators()]


@router.get("/modbus/points")
def list_points():
    """可下发点位目录：含量程、是否可写、当前值、设备在线状态。"""
    return [point_service.serialize(p) for p in point_service.list_points()]


# ---------------------------------------------------------------------------
# 受控下发通道
# ---------------------------------------------------------------------------
@router.post("/modbus/write/{device_id}/{address}", status_code=202)
def write_register(device_id: str, address: int, body: WriteRequest,
                   operator: Operator = Depends(require_operator)):
    """受控点位下发。

    - 只读查看者 / 无归属 / 只读点位 -> 403，拒绝下发（同样留审计记录）；
    - 点位不存在 / 数值越界 -> 422，说明原因，原值不变（留审计记录）；
    - 同一点位上次下发未结束 -> 409，以先到为准，本次可稍后重试；
    - 受理后返回 202 + 审计记录（pending），后台执行，可凭 id 查询结果。
    """
    return write_service.submit_write(operator, device_id, address, body.value)


@router.get("/modbus/writes/{record_id}")
def get_write(record_id: str, operator: Operator = Depends(require_writer)):
    record = write_service.get_record(record_id)
    if record["operatorId"] != operator.id:
        raise HTTPException(status_code=403, detail={"reason": "只能查看本人的下发记录"})
    return record


@router.post("/modbus/writes/{record_id}/retry", status_code=202)
def retry_write(record_id: str, operator: Operator = Depends(require_writer)):
    """重试失败/冲突的下发（仅本人、仅可重试的记录）。"""
    return write_service.retry_write(operator, record_id)


@router.get("/modbus/writes")
def list_writes(operator: Operator = Depends(require_writer),
                mine: bool = Query(False, description="仅看本人提交"),
                operator_id: Optional[str] = Query(None, description="按操作者回看"),
                device_id: Optional[str] = None,
                address: Optional[int] = None,
                limit: int = Query(100, ge=1, le=500)):
    """下发审计记录：谁、什么时间、哪个点位、改成多少、结果与原因。"""
    point_key = f"{device_id}:{address}" if device_id is not None and address is not None else None
    filter_operator = operator.id if mine else operator_id
    return write_service.list_records(filter_operator, point_key, limit)


@router.patch("/modbus/devices/{device_id}/online")
def set_device_online(device_id: str, online: bool = Query(...),
                      operator: Operator = Depends(require_writer)):
    """切换设备在线状态（用于设备恢复后重试下发）。仅操作者可用。"""
    for dev in MOCK_DEVICES:
        if dev["id"] == device_id:
            dev["online"] = online
            return {"device_id": device_id, "online": online}
    raise HTTPException(status_code=404, detail={"reason": f"设备 {device_id} 不存在"})
