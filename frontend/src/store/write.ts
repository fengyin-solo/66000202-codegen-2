import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { apiLogin, apiMe, apiPoints, apiWrite, apiWriteRecords } from '../api'
import type { PointMeta, UserInfo, WriteRecord } from '../types'

const TOKEN_KEY = 'modbus_token'

export const useWriteStore = defineStore('write', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<UserInfo | null>(null)
  const points = ref<PointMeta[]>([])
  const records = ref<WriteRecord[]>([])
  const backendOnline = ref(true)
  const lastResult = ref<WriteRecord | null>(null)
  const submitting = ref<Record<string, boolean>>({})
  const loginError = ref('')

  const isOperator = computed(() => user.value?.role === 'operator')
  const writablePoints = computed(() => points.value.filter(p => p.writable))
  const operators = computed(() => Array.from(new Set(records.value.map(r => r.operator))))

  async function login(username: string, password: string) {
    loginError.value = ''
    try {
      const res = await apiLogin(username, password)
      token.value = res.token
      user.value = res.user
      localStorage.setItem(TOKEN_KEY, res.token)
      await refreshRecords()
    } catch (e: any) {
      loginError.value = e?.response?.data?.detail || '登录失败'
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    records.value = []
    localStorage.removeItem(TOKEN_KEY)
  }

  async function restore() {
    if (!token.value) return
    try {
      user.value = await apiMe(token.value)
    } catch {
      logout()
    }
  }

  async function loadPoints() {
    try {
      points.value = await apiPoints()
      backendOnline.value = true
    } catch {
      backendOnline.value = false
    }
  }

  async function refreshRecords() {
    if (!isOperator.value || !token.value) return
    try {
      records.value = await apiWriteRecords(token.value)
    } catch {
      // 保留现有列表，下次刷新再试
    }
  }

  async function submit(deviceId: string, address: number, value: number): Promise<WriteRecord | null> {
    const key = `${deviceId}_${address}`
    if (submitting.value[key]) return null
    submitting.value[key] = true
    try {
      const record = await apiWrite(token.value, deviceId, address, value)
      lastResult.value = record
      await Promise.all([loadPoints(), refreshRecords()])
      return record
    } finally {
      submitting.value[key] = false
    }
  }

  async function retry(record: WriteRecord): Promise<WriteRecord | null> {
    return submit(record.device_id, record.address, record.value)
  }

  return {
    token, user, points, records, backendOnline, lastResult, submitting, loginError,
    isOperator, writablePoints, operators,
    login, logout, restore, loadPoints, refreshRecords, submit, retry
  }
})
