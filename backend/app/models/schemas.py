from pydantic import BaseModel
from typing import List, Optional, Union

class ModbusRegister(BaseModel):
    address: int
    name: str
    type: str
    value: float
    unit: str

class Device(BaseModel):
    id: str
    name: str
    ip: str
    port: int
    slave_id: int
    online: bool
    registers: List[ModbusRegister] = []

class WriteRequest(BaseModel):
    """受控下发请求体：目标值（数值或布尔量）。"""
    value: Union[float, int, bool]
