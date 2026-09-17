import axios, { AxiosError } from 'axios'
import type { OperatorInfo, PointInfo, WriteRecord } from '../types'

const http = axios.create({ baseURL: '/api' })

export interface ApiError {
  reason: string
  record?: WriteRecord
}

export function extractError(e: unknown): ApiError {
  const err = e as AxiosError<{ detail: ApiError | string }>
  const detail = err.response?.data?.detail
  if (detail && typeof detail === 'object') return detail
  return { reason: typeof detail === 'string' ? detail : (err.message || '请求失败') }
}

/** 所有受控接口都带上当前操作者标识 */
export function authHeaders(operatorId: string) {
  return { headers: { 'X-Operator-Id': operatorId } }
}

export async function fetchOperators(): Promise<OperatorInfo[]> {
  const { data } = await http.get<OperatorInfo[]>('/operators')
  return data
}

export async function fetchPoints(): Promise<PointInfo[]> {
  const { data } = await http.get<PointInfo[]>('/modbus/points')
  return data.map(p => ({ ...p, key: `${p.deviceId}:${p.address}` }))
}

export async function submitWrite(
  operatorId: string, deviceId: string, address: number, value: number | boolean,
): Promise<WriteRecord> {
  const { data } = await http.post<WriteRecord>(
    `/modbus/write/${deviceId}/${address}`, { value }, authHeaders(operatorId),
  )
  return data
}

export async function retryWrite(operatorId: string, recordId: string): Promise<WriteRecord> {
  const { data } = await http.post<WriteRecord>(
    `/modbus/writes/${recordId}/retry`, {}, authHeaders(operatorId),
  )
  return data
}

export async function fetchWrites(operatorId: string, mine: boolean): Promise<WriteRecord[]> {
  const { data } = await http.get<WriteRecord[]>('/modbus/writes', {
    params: { mine }, ...authHeaders(operatorId),
  })
  return data
}

export async function setDeviceOnline(operatorId: string, deviceId: string, online: boolean) {
  const { data } = await http.patch<{ device_id: string; online: boolean }>(
    `/modbus/devices/${deviceId}/online`, null, { params: { online }, ...authHeaders(operatorId) },
  )
  return data
}
