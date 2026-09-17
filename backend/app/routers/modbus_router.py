from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from app.models.schemas import WriteRequest
from app.services import auth_service, write_service
from app.services.modbus_service import read_registers, get_device_status, list_points

router = APIRouter()


def _current_user(authorization: str):
    user = auth_service.user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


@router.get("/modbus/devices")
def list_devices():
    return get_device_status()


@router.get("/modbus/read/{device_id}/{address}/{count}")
def read_holding(device_id: str, address: int, count: int = 1):
    """Read holding registers from a Modbus device."""
    return read_registers(device_id, address, count)


@router.get("/modbus/points")
def list_point_catalog():
    """点位台账：名称、是否可写、允许范围与当前值（只读查询，无需登录）。"""
    return {"points": list_points()}


@router.post("/modbus/write")
async def write_point(req: WriteRequest, authorization: str = Header(None)):
    """受控点位下发通道：仅具备写入归属的操作者可提交。

    提交前校验目标点位是否存在、数值是否在允许范围内；不满足条件时
    说明原因且不改变原值。同一点位上一次下发未结束时，以先到的一次为准。
    每次提交都会留下审计记录。
    """
    user = _current_user(authorization)
    if user["role"] != "operator":
        record = write_service.record_forbidden_attempt(user, req.device_id, req.address, req.value)
        return JSONResponse(status_code=403, content=record)
    record, status = await write_service.submit_write(user, req.device_id, req.address, req.value)
    return JSONResponse(status_code=status, content=record)


@router.get("/modbus/write-records")
def list_write_records(operator: str = None, device_id: str = None, authorization: str = Header(None)):
    """按操作者回看下发记录（仅操作者可查）。"""
    user = _current_user(authorization)
    if user["role"] != "operator":
        raise HTTPException(status_code=403, detail="只读查看者无权查看下发记录")
    return {"records": write_service.query_records(operator=operator, device_id=device_id)}
