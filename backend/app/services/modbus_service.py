"""Modbus service with mock data (replace with pymodbus for production)."""
import random
from typing import List, Dict, Any

MOCK_DEVICES = [
    {"id": "dev1", "name": "温湿度传感器-A区", "ip": "192.168.1.101", "port": 502, "slave_id": 1, "online": True},
    {"id": "dev2", "name": "压力变送器-B区", "ip": "192.168.1.102", "port": 502, "slave_id": 2, "online": True},
    {"id": "dev3", "name": "电机控制器-C区", "ip": "192.168.1.103", "port": 502, "slave_id": 3, "online": False},
]

def get_device_status() -> List[Dict[str, Any]]:
    return MOCK_DEVICES

def read_registers(device_id: str, address: int, count: int) -> Dict[str, Any]:
    """Read registers via pymodbus (mock implementation).

    已在点位目录登记的点位返回其当前值（下发成功后即生效，刷新仍可见）；
    未登记的地址保持原有随机模拟读数口径。
    """
    # In production: from pymodbus.client import ModbusTcpClient
    # client = ModbusTcpClient(host, port=port)
    # result = client.read_holding_registers(address, count, slave=slave_id)
    from app.services import point_service  # 延迟导入，避免循环依赖

    values: List[Any] = []
    for offset in range(count):
        point = point_service.get_point(device_id, address + offset)
        if point is not None:
            val = point_service.get_current_value(point)
            values.append(bool(val) if point.type == "coil" else val)
        else:
            values.append(round(random.uniform(0, 100), 2))
    return {"device_id": device_id, "address": address, "values": values}
