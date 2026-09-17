"""Modbus service with mock data (replace with pymodbus for production)."""
import random
from typing import Any, Dict, List, Optional, Tuple

MOCK_DEVICES = [
    {"id": "dev1", "name": "温湿度传感器-A区", "ip": "192.168.1.101", "port": 502, "slave_id": 1, "online": True},
    {"id": "dev2", "name": "压力变送器-B区", "ip": "192.168.1.102", "port": 502, "slave_id": 2, "online": True},
    {"id": "dev3", "name": "电机控制器-C区", "ip": "192.168.1.103", "port": 502, "slave_id": 3, "online": False},
    {"id": "dev4", "name": "流量计-D区", "ip": "192.168.1.104", "port": 502, "slave_id": 4, "online": True},
]

# 点位台账：key = (device_id, address)
# writable=True 的点位允许通过受控下发通道写入，且数值必须落在 [min, max] 内；
# writable=False 的点位为只读测量点，任何下发都会被拒绝。
POINTS: Dict[Tuple[str, int], Dict[str, Any]] = {
    ("dev1", 0): {"name": "温度", "unit": "°C", "writable": True, "min": -10.0, "max": 60.0, "value": 25.6},
    ("dev1", 1): {"name": "湿度", "unit": "%RH", "writable": True, "min": 0.0, "max": 100.0, "value": 62.3},
    ("dev1", 2): {"name": "露点", "unit": "°C", "writable": False, "min": None, "max": None, "value": 17.8},
    ("dev2", 0): {"name": "管道压力", "unit": "MPa", "writable": True, "min": 0.0, "max": 6.0, "value": 3.45},
    ("dev2", 1): {"name": "差压", "unit": "kPa", "writable": False, "min": None, "max": None, "value": 0.12},
    ("dev3", 0): {"name": "转速", "unit": "RPM", "writable": True, "min": 0.0, "max": 3000.0, "value": 1480.0},
    ("dev3", 1): {"name": "电流", "unit": "A", "writable": False, "min": None, "max": None, "value": 12.5},
    ("dev3", 2): {"name": "运行状态", "unit": "", "writable": True, "min": 0.0, "max": 1.0, "value": 1.0},
    ("dev4", 0): {"name": "瞬时流量", "unit": "L/min", "writable": False, "min": None, "max": None, "value": 156.7},
    ("dev4", 1): {"name": "累计流量", "unit": "L", "writable": True, "min": 0.0, "max": 999999.0, "value": 98234.0},
}


def get_device_status() -> List[Dict[str, Any]]:
    return MOCK_DEVICES


def get_device(device_id: str) -> Optional[Dict[str, Any]]:
    return next((d for d in MOCK_DEVICES if d["id"] == device_id), None)


def get_point(device_id: str, address: int) -> Optional[Dict[str, Any]]:
    return POINTS.get((device_id, address))


def list_points() -> List[Dict[str, Any]]:
    """点位台账（含当前值），供下发前展示与校验范围。"""
    devices = {d["id"]: d for d in MOCK_DEVICES}
    return [
        {
            "device_id": device_id,
            "device_name": devices[device_id]["name"] if device_id in devices else device_id,
            "address": address,
            "name": point["name"],
            "unit": point["unit"],
            "writable": point["writable"],
            "min": point["min"],
            "max": point["max"],
            "value": point["value"],
        }
        for (device_id, address), point in sorted(POINTS.items())
    ]


def read_registers(device_id: str, address: int, count: int) -> Dict[str, Any]:
    """Read registers via pymodbus (mock implementation)."""
    # In production: from pymodbus.client import ModbusTcpClient
    # client = ModbusTcpClient(host, port=port)
    # result = client.read_holding_registers(address, count, slave=slave_id)
    values = []
    for i in range(count):
        point = POINTS.get((device_id, address + i))
        if point is None:
            values.append(round(random.uniform(0, 100), 2))
        else:
            base = point["value"]
            noise = random.uniform(-0.02, 0.02) * max(abs(base), 1.0)
            values.append(round(base + noise, 2))
    return {"device_id": device_id, "address": address, "values": values}
