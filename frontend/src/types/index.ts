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

export interface OperatorInfo {
  id: string
  name: string
  role: 'operator' | 'viewer'
  ownedPoints: string[]
}

export interface PointInfo {
  deviceId: string
  address: number
  name: string
  type: 'holding' | 'coil'
  unit: string
  writable: boolean
  minValue: number | null
  maxValue: number | null
  value: number | boolean
  online: boolean
  /** 前端拼接的全局点位键 */
  key?: string
}

export type WriteStatus = 'pending' | 'success' | 'failed' | 'conflict'

export interface WriteRecord {
  id: string
  operatorId: string
  operatorName: string
  deviceId: string
  address: number
  pointName: string | null
  pointKey: string
  unit: string
  value: number | boolean
  previousValue: number | boolean | null
  status: WriteStatus
  reason: string | null
  retryable: boolean
  retryOf: string | null
  createdAt: number
  createdAtIso: string
  finishedAt: number | null
  finishedAtIso: string | null
}
