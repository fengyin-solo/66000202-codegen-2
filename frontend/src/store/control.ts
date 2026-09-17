import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { OperatorInfo, PointInfo, WriteRecord } from '../types'
import {
  fetchOperators, fetchPoints, fetchWrites, submitWrite, retryWrite,
  setDeviceOnline, extractError,
} from '../api/modbus'
import { useModbusStore } from './modbus'

/** 受控点位写入通道的前端状态：操作者、点位目录、审计记录、在途轮询 */
export const useControlStore = defineStore('control', () => {
  const operators = ref<OperatorInfo[]>([])
  const currentOperatorId = ref<string>('')
  const points = ref<PointInfo[]>([])
  const records = ref<WriteRecord[]>([])
  const auditScope = ref<'mine' | 'all'>('mine')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const apiAvailable = ref(true)
  const submittingKeys = ref<Set<string>>(new Set())
  const pendingIds = ref<Set<string>>(new Set())
  let pollTimer: number | null = null

  const currentOperator = computed(
    () => operators.value.find(o => o.id === currentOperatorId.value) ?? null,
  )
  const isViewer = computed(() => currentOperator.value?.role === 'viewer')

  /** 该操作者可下发的点位（具备写入归属） */
  const writablePoints = computed<PointInfo[]>(() => {
    const op = currentOperator.value
    if (!op || op.role !== 'operator') return []
    return points.value.filter(p => op.ownedPoints.includes(p.key!))
  })

  const deviceName = (deviceId: string) => {
    const dev = useModbusStore().devices.find(d => d.id === deviceId)
    return dev ? dev.name : deviceId
  }

  function ownsPoint(point: PointInfo): boolean {
    const op = currentOperator.value
    return !!op && op.role === 'operator' && op.ownedPoints.includes(point.key!)
  }

  async function init() {
    try {
      const [ops, pts] = await Promise.all([fetchOperators(), fetchPoints()])
      operators.value = ops
      // 默认选第一个操作者（若上次选择过则恢复）
      const saved = localStorage.getItem('operatorId')
      currentOperatorId.value = (saved && ops.some(o => o.id === saved)) ? saved : ops[0]?.id ?? ''
      points.value = pts
      syncValuesToDashboard()
      apiAvailable.value = true
      await refreshRecords()
      startPolling()
    } catch (e) {
      apiAvailable.value = false
      error.value = `无法连接后端采集服务：${extractError(e).reason}`
    }
  }

  function selectOperator(id: string) {
    currentOperatorId.value = id
    localStorage.setItem('operatorId', id)
    error.value = null
    records.value = []
    void refreshRecords()
  }

  /** 后端点位当前值同步到实时大屏（初始加载/下发后），刷新后仍显示真实值 */
  function syncValuesToDashboard() {
    const dashboard = useModbusStore()
    for (const p of points.value) {
      const dev = dashboard.devices.find(d => d.id === p.deviceId)
      const reg = dev?.registers.find(r => r.address === p.address)
      if (reg) {
        reg.value = p.value
        reg.updatedAt = Date.now()
      }
    }
  }

  function applyRecordToPoints(record: WriteRecord) {
    if (record.status !== 'success') return
    const point = points.value.find(p => p.key === record.pointKey)
    if (point) {
      point.value = record.value
      syncValuesToDashboard()
    }
  }

  async function refreshPoints() {
    points.value = await fetchPoints()
    syncValuesToDashboard()
  }

  async function refreshRecords() {
    const op = currentOperator.value
    if (!op || op.role !== 'operator') {
      records.value = []
      return
    }
    try {
      records.value = await fetchWrites(op.id, auditScope.value === 'mine')
      trackPending()
    } catch (e) {
      error.value = extractError(e).reason
    }
  }

  function trackPending() {
    pendingIds.value = new Set(
      records.value.filter(r => r.status === 'pending').map(r => r.id),
    )
  }

  function startPolling() {
    if (pollTimer != null) return
    pollTimer = window.setInterval(async () => {
      const stillPending = [...pendingIds.value]
      if (!stillPending.length) return
      await refreshRecords()
      await refreshPoints()
      // 本轮刚结束的记录，若成功则同步到大屏
      for (const id of stillPending) {
        const rec = records.value.find(r => r.id === id)
        if (rec && rec.status !== 'pending') applyRecordToPoints(rec)
      }
    }, 1000)
  }

  async function submit(point: PointInfo, rawValue: string) {
    error.value = null
    const value: number | boolean =
      point.type === 'coil'
        ? ['true', '1', 'on'].includes(rawValue.trim().toLowerCase())
        : Number(rawValue)
    submittingKeys.value.add(point.key!)
    try {
      const record = await submitWrite(currentOperatorId.value, point.deviceId, point.address, value)
      pendingIds.value.add(record.id)
      await refreshRecords()
      // 立即刷新点位在线状态等
      await refreshPoints()
    } catch (e) {
      const apiErr = extractError(e)
      error.value = apiErr.reason
      // 409冲突/422校验失败等：服务端已落审计记录，刷新列表
      await refreshRecords()
      if (apiErr.record && apiErr.record.status === 'conflict') {
        pendingIds.value.add(apiErr.record.id)
      }
    } finally {
      submittingKeys.value.delete(point.key!)
    }
  }

  async function retry(record: WriteRecord) {
    error.value = null
    try {
      const fresh = await retryWrite(currentOperatorId.value, record.id)
      pendingIds.value.add(fresh.id)
      await refreshRecords()
      await refreshPoints()
    } catch (e) {
      const apiErr = extractError(e)
      error.value = apiErr.reason
      await refreshRecords()
    }
  }

  async function bringOnlineAndRetry(record: WriteRecord) {
    loading.value = true
    try {
      await setDeviceOnline(currentOperatorId.value, record.deviceId, true)
      await refreshPoints()
      await retry(record)
    } catch (e) {
      error.value = extractError(e).reason
    } finally {
      loading.value = false
    }
  }

  return {
    operators, currentOperatorId, currentOperator, isViewer, points, writablePoints,
    records, auditScope, loading, error, apiAvailable, submittingKeys, pendingIds,
    deviceName, ownsPoint, init, selectOperator, submit, retry, bringOnlineAndRetry,
    refreshRecords, syncValuesToDashboard,
  }
})
