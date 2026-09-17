import axios from 'axios'
import type { PointMeta, UserInfo, WriteRecord } from './types'

const http = axios.create({ baseURL: '/api', timeout: 15000 })

function authHeader(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export async function apiLogin(username: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const { data } = await http.post('/auth/login', { username, password })
  return data
}

export async function apiMe(token: string): Promise<UserInfo> {
  const { data } = await http.get('/auth/me', { headers: authHeader(token) })
  return data
}

export async function apiPoints(): Promise<PointMeta[]> {
  const { data } = await http.get('/modbus/points')
  return data.points
}

export async function apiWrite(token: string, deviceId: string, address: number, value: number): Promise<WriteRecord> {
  const { data } = await http.post(
    '/modbus/write',
    { device_id: deviceId, address, value },
    // 4xx 响应同样携带审计记录，统一在这里取出
    { headers: authHeader(token), validateStatus: s => s < 500 }
  )
  if (data && data.id) return data as WriteRecord
  throw new Error(data?.detail || '下发请求失败')
}

export async function apiWriteRecords(token: string, operator?: string): Promise<WriteRecord[]> {
  const { data } = await http.get('/modbus/write-records', {
    headers: authHeader(token),
    params: operator ? { operator } : {}
  })
  return data.records
}
