export interface ModbusRegister {
  address: number
  name: string
  type: 'coil' | 'discrete' | 'holding' | 'input'
  value: number | boolean
  unit: string
  updatedAt: number
}

export interface Device {
  id: string
  name: string
  ip: string
  port: number
  slaveId: number
  online: boolean
  registers: ModbusRegister[]
}

export interface Alarm {
  id: string
  deviceId: string
  register: string
  message: string
  level: 'info' | 'warning' | 'critical'
  timestamp: number
  acknowledged: boolean
}

export interface UserInfo {
  username: string
  display_name: string
  role: 'operator' | 'viewer'
}

export interface PointMeta {
  device_id: string
  device_name: string
  address: number
  name: string
  unit: string
  writable: boolean
  min: number | null
  max: number | null
  value: number
}

export type WriteStatus = 'success' | 'failed' | 'conflict' | 'forbidden'

export interface WriteRecord {
  id: string
  operator: string
  operator_name: string
  device_id: string
  address: number
  point_name: string | null
  value: number
  old_value: number | null
  status: WriteStatus
  reason: string
  timestamp: number
}
