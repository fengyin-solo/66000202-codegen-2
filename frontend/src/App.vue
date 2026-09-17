<template>
  <div class="flex h-screen">
    <!-- Sidebar -->
    <div class="w-64 bg-gray-900 p-4 flex flex-col gap-3 border-r border-gray-800 overflow-y-auto">
      <h1 class="text-lg font-bold text-orange-400">Modbus 工业监控</h1>

      <!-- 操作者身份 -->
      <div class="bg-gray-800 rounded p-2 text-xs flex flex-col gap-1.5">
        <template v-if="!writeStore.user">
          <div class="text-gray-400">操作者登录（登录后才可下发点位）</div>
          <input v-model.trim="loginForm.username" placeholder="用户名"
            class="bg-gray-900 rounded px-2 py-1 text-gray-200 outline-none focus:ring-1 ring-orange-500" />
          <input v-model="loginForm.password" type="password" placeholder="密码" @keyup.enter="onLogin"
            class="bg-gray-900 rounded px-2 py-1 text-gray-200 outline-none focus:ring-1 ring-orange-500" />
          <button @click="onLogin" class="bg-orange-600 hover:bg-orange-500 rounded py-1">登录</button>
          <div v-if="writeStore.loginError" class="text-red-400">{{ writeStore.loginError }}</div>
          <div class="text-gray-600">操作者 operator1/operator123<br />只读查看者 viewer1/viewer123</div>
        </template>
        <template v-else>
          <div class="flex justify-between items-center">
            <span class="text-gray-200">{{ writeStore.user.display_name }}（{{ writeStore.user.username }}）</span>
            <span class="px-1.5 py-0.5 rounded text-[10px]"
              :class="writeStore.isOperator ? 'bg-orange-900 text-orange-300' : 'bg-gray-700 text-gray-300'">
              {{ writeStore.isOperator ? '操作者' : '只读查看者' }}
            </span>
          </div>
          <div v-if="!writeStore.isOperator" class="text-gray-500">仅可查看实时读数，不能改动任何点位</div>
          <button @click="writeStore.logout()" class="bg-gray-700 hover:bg-gray-600 rounded py-1">退出登录</button>
        </template>
      </div>

      <div class="flex gap-2">
        <button @click="startPoll" :disabled="store.isPolling" class="flex-1 bg-green-700 py-1.5 rounded text-xs hover:bg-green-600 disabled:opacity-50">
          {{ store.isPolling ? '采集中...' : '开始采集' }}
        </button>
        <button @click="stopPoll" :disabled="!store.isPolling" class="flex-1 bg-red-700 py-1.5 rounded text-xs hover:bg-red-600 disabled:opacity-50">
          停止
        </button>
      </div>
      <div>
        <label class="text-gray-400 text-xs">轮询间隔: {{ store.pollInterval }}ms</label>
        <input type="range" v-model.number="store.pollInterval" min="200" max="5000" step="100" class="w-full" />
      </div>

      <h3 class="text-gray-400 text-xs mt-2">设备列表</h3>
      <div v-for="d in store.devices" :key="d.id" @click="store.selectedDevice = d"
        class="bg-gray-800 rounded p-2 cursor-pointer text-sm"
        :class="store.selectedDevice?.id === d.id ? 'ring-1 ring-orange-500' : ''">
        <div class="flex justify-between">
          <span>{{ d.name }}</span>
          <span class="w-2 h-2 rounded-full mt-1.5" :class="d.online ? 'bg-green-500' : 'bg-red-500'"></span>
        </div>
        <div class="text-xs text-gray-500">{{ d.ip }}:{{ d.port }} [{{ d.slaveId }}]</div>
      </div>

      <div v-if="store.criticalAlarms.length" class="bg-red-900/50 rounded p-2 mt-2">
        <h4 class="text-red-400 text-xs font-bold">⚠ 严重告警 {{ store.criticalAlarms.length }}</h4>
        <div v-for="a in store.criticalAlarms.slice(0, 3)" :key="a.id" class="text-xs text-red-300 mt-1 truncate">
          {{ a.message }}
        </div>
      </div>

      <div class="text-xs text-gray-600 mt-auto">
        在线: {{ store.onlineDevices.length }}/{{ store.devices.length }}
      </div>
    </div>

    <!-- Main Dashboard -->
    <div class="flex-1 flex flex-col gap-3 p-4 overflow-y-auto">
      <!-- Register Gauges -->
      <div class="grid grid-cols-4 gap-3">
        <div v-for="g in gauges" :key="g.key" class="bg-gray-900 rounded-xl p-3">
          <div class="text-xs text-gray-400">{{ g.deviceName }}</div>
          <div class="text-2xl font-bold" :class="g.online ? 'text-orange-400' : 'text-gray-600'">
            {{ typeof g.value === 'number' ? g.value.toFixed(g.value > 100 ? 0 : 1) : g.value ? 'ON' : 'OFF' }}
          </div>
          <div class="text-xs text-gray-500">{{ g.name }} {{ g.unit }}</div>
        </div>
      </div>

      <!-- 受控点位下发通道（仅操作者） -->
      <div v-if="writeStore.isOperator" class="bg-gray-900 rounded-xl p-3">
        <div class="flex justify-between items-center mb-2">
          <h3 class="text-sm text-gray-400">点位下发（受控通道）</h3>
          <button @click="writeStore.loadPoints()" class="text-xs text-blue-400 hover:underline">刷新点位</button>
        </div>
        <div v-if="!writeStore.backendOnline" class="text-xs text-red-400">后端服务不可用，无法下发</div>
        <template v-else>
          <div v-for="p in writeStore.writablePoints" :key="`${p.device_id}_${p.address}`"
            class="flex items-center gap-3 bg-gray-800 rounded p-2 mb-1 text-xs">
            <span class="w-48 truncate">{{ p.device_name }} · {{ p.name }}</span>
            <span class="text-gray-500 w-28">当前 {{ p.value }} {{ p.unit }}</span>
            <span class="text-gray-600 w-32">范围 [{{ p.min }}, {{ p.max }}]</span>
            <input type="number" v-model.number="drafts[`${p.device_id}_${p.address}`]"
              class="w-24 bg-gray-900 rounded px-2 py-1 text-gray-200 outline-none focus:ring-1 ring-orange-500" />
            <button @click="onSubmit(p)" :disabled="!!writeStore.submitting[`${p.device_id}_${p.address}`]"
              class="bg-orange-600 hover:bg-orange-500 rounded px-3 py-1 disabled:opacity-50">
              {{ writeStore.submitting[`${p.device_id}_${p.address}`] ? '下发中...' : '下发' }}
            </button>
          </div>
          <div v-if="!writeStore.writablePoints.length" class="text-xs text-gray-600">暂无可写点位</div>
          <div v-if="formError" class="text-xs text-red-400 mt-1">{{ formError }}</div>
        </template>
      </div>

      <!-- Chart -->
      <div class="bg-gray-900 rounded-xl p-3 flex-1">
        <h3 class="text-sm text-gray-400 mb-2">
          实时趋势 — {{ store.selectedDevice?.name || '选择设备' }}
        </h3>
        <TrendChart />
      </div>

      <!-- Alarm List -->
      <div class="bg-gray-900 rounded-xl p-3 max-h-48 overflow-y-auto">
        <h3 class="text-sm text-gray-400 mb-2">告警记录</h3>
        <div v-for="a in store.alarms.slice(0, 10)" :key="a.id"
          class="flex justify-between text-xs bg-gray-800 rounded p-2 mb-1"
          :class="{ 'border-l-4 border-red-500': a.level === 'critical', 'border-l-4 border-yellow-500': a.level === 'warning' }">
          <span>{{ a.message }}</span>
          <div class="flex gap-2">
            <span class="text-gray-500">{{ new Date(a.timestamp).toLocaleTimeString() }}</span>
            <button v-if="!a.acknowledged" @click="store.acknowledgeAlarm(a.id)" class="text-blue-400 hover:underline">确认</button>
          </div>
        </div>
      </div>

      <!-- 下发记录（仅操作者，可按操作者回看） -->
      <div v-if="writeStore.isOperator" class="bg-gray-900 rounded-xl p-3 max-h-64 overflow-y-auto">
        <div class="flex justify-between items-center mb-2">
          <h3 class="text-sm text-gray-400">下发记录</h3>
          <div class="flex items-center gap-2 text-xs">
            <select v-model="operatorFilter" class="bg-gray-800 rounded px-2 py-1 text-gray-300 outline-none">
              <option value="">全部操作者</option>
              <option v-for="op in writeStore.operators" :key="op" :value="op">{{ op }}</option>
            </select>
            <button @click="writeStore.refreshRecords()" class="text-blue-400 hover:underline">刷新</button>
          </div>
        </div>
        <div v-for="r in filteredRecords" :key="r.id"
          class="flex items-center gap-2 text-xs bg-gray-800 rounded p-2 mb-1">
          <span class="px-1.5 py-0.5 rounded text-[10px] shrink-0" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span>
          <span class="text-gray-300 w-24 truncate">{{ r.operator_name }}({{ r.operator }})</span>
          <span class="text-gray-400 w-44 truncate">{{ r.device_id }} · {{ r.point_name || `地址${r.address}` }}</span>
          <span class="text-orange-300 w-28 shrink-0">→ {{ r.value }}<span v-if="r.old_value !== null" class="text-gray-500">（原 {{ r.old_value }}）</span></span>
          <span class="text-gray-500 shrink-0">{{ new Date(r.timestamp).toLocaleTimeString() }}</span>
          <span class="text-gray-500 flex-1 truncate" :title="r.reason">{{ r.reason }}</span>
          <button v-if="r.status === 'failed' || r.status === 'conflict'" @click="onRetry(r)"
            class="text-blue-400 hover:underline shrink-0">重试</button>
        </div>
        <div v-if="!filteredRecords.length" class="text-xs text-gray-600">暂无记录</div>
      </div>
    </div>

    <!-- 下发结果提示 -->
    <div v-if="toast" class="fixed bottom-4 right-4 max-w-sm bg-gray-800 border rounded-lg p-3 text-xs shadow-lg z-50"
      :class="toastBorder">
      <div class="flex justify-between gap-3">
        <div>
          <div class="font-bold mb-1" :class="toastText">{{ toastTitle }}</div>
          <div class="text-gray-400">{{ toast.reason }}</div>
        </div>
        <button @click="toast = null" class="text-gray-500 hover:text-gray-300 self-start">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useModbusStore } from './store/modbus'
import { useWriteStore } from './store/write'
import TrendChart from './components/TrendChart.vue'
import type { PointMeta, WriteRecord, WriteStatus } from './types'

const store = useModbusStore()
const writeStore = useWriteStore()
let timer: number | null = null

const loginForm = reactive({ username: '', password: '' })
const drafts = reactive<Record<string, number>>({})
const operatorFilter = ref('')
const formError = ref('')
const toast = ref<WriteRecord | null>(null)
let toastTimer: number | null = null

const gauges = computed(() =>
  store.devices.flatMap(d =>
    d.registers.map(r => ({
      key: `${d.id}_${r.address}`,
      deviceName: d.name,
      online: d.online,
      name: r.name,
      unit: r.unit,
      value: r.value
    }))
  )
)

const filteredRecords = computed(() =>
  operatorFilter.value ? writeStore.records.filter(r => r.operator === operatorFilter.value) : writeStore.records
)

const STATUS_LABELS: Record<WriteStatus, string> = {
  success: '成功', failed: '失败', conflict: '冲突', forbidden: '拒绝'
}
const STATUS_CLASSES: Record<WriteStatus, string> = {
  success: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
  conflict: 'bg-yellow-900 text-yellow-300',
  forbidden: 'bg-gray-700 text-gray-300'
}
const statusLabel = (s: WriteStatus) => STATUS_LABELS[s]
const statusClass = (s: WriteStatus) => STATUS_CLASSES[s]

const toastTitle = computed(() => toast.value ? `下发${STATUS_LABELS[toast.value.status]} — ${toast.value.point_name || toast.value.device_id}` : '')
const toastText = computed(() => toast.value?.status === 'success' ? 'text-green-400' : 'text-red-400')
const toastBorder = computed(() => toast.value?.status === 'success' ? 'border-green-700' : 'border-red-700')

watch(() => writeStore.lastResult, r => {
  if (!r) return
  toast.value = r
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => { toast.value = null }, 5000)
})

// 点位台账加载后，用当前值初始化下发输入框
watch(() => writeStore.points, points => {
  for (const p of points) {
    const key = `${p.device_id}_${p.address}`
    if (p.writable && drafts[key] === undefined) drafts[key] = p.value
  }
}, { immediate: true })

function startPoll() {
  store.isPolling = true
  timer = window.setInterval(() => store.simulatePoll(), store.pollInterval)
}

function stopPoll() {
  store.isPolling = false
  if (timer) { clearInterval(timer); timer = null }
}

async function onLogin() {
  await writeStore.login(loginForm.username, loginForm.password)
  loginForm.password = ''
}

function applyIfSuccess(record: WriteRecord | null) {
  if (record?.status === 'success') {
    store.applyLocalWrite(record.device_id, record.address, record.value)
  }
}

async function onSubmit(p: PointMeta) {
  const value = drafts[`${p.device_id}_${p.address}`]
  if (typeof value !== 'number' || Number.isNaN(value)) {
    formError.value = '请输入有效数值'
    return
  }
  formError.value = ''
  applyIfSuccess(await writeStore.submit(p.device_id, p.address, value))
}

async function onRetry(r: WriteRecord) {
  applyIfSuccess(await writeStore.retry(r))
}

onMounted(() => {
  store.initMockDevices()
  writeStore.restore().then(() => writeStore.refreshRecords())
  writeStore.loadPoints()
})
onUnmounted(() => stopPoll())
</script>
