<template>
  <div class="w-96 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
    <!-- 操作者切换 -->
    <div class="p-3 border-b border-gray-800">
      <h2 class="text-sm font-bold text-orange-400 mb-2">受控下发通道</h2>
      <label class="text-xs text-gray-400">当前操作者</label>
      <select
        :value="control.currentOperatorId"
        @change="control.selectOperator(($event.target as HTMLSelectElement).value)"
        class="w-full bg-gray-800 text-sm rounded p-1.5 mt-1 text-gray-200"
      >
        <option v-for="op in control.operators" :key="op.id" :value="op.id">
          {{ op.name }}（{{ op.role === 'operator' ? '可下发' : '只读' }}）
        </option>
      </select>
      <div v-if="control.isViewer" class="mt-2 text-xs text-yellow-400 bg-yellow-900/30 rounded p-2">
        🔒 只读查看者：仅可查看实时读数，不能下发或改动任何点位。
      </div>
      <div v-else class="mt-2 text-xs text-gray-500">
        归属点位 {{ control.writablePoints.length }} 个；每次下发均留审计记录。
      </div>
    </div>

    <!-- 后端不可用提示 -->
    <div v-if="!control.apiAvailable" class="m-3 text-xs text-red-300 bg-red-900/40 rounded p-2">
      {{ control.error }}
    </div>

    <div class="flex-1 overflow-y-auto p-3 space-y-3">
      <!-- 可下发点位 -->
      <div v-if="!control.isViewer">
        <h3 class="text-xs text-gray-400 mb-2">我的点位下发</h3>
        <div
          v-for="p in control.writablePoints"
          :key="p.key"
          class="bg-gray-800 rounded-lg p-2.5 mb-2"
        >
          <div class="flex justify-between items-center">
            <div>
              <span class="text-sm text-gray-200">{{ p.name }}</span>
              <span class="text-xs text-gray-500 ml-1">{{ p.unit }}</span>
              <span class="text-[10px] text-gray-600 ml-1">[{{ p.deviceId }}:{{ p.address }}]</span>
            </div>
            <span
              class="w-2 h-2 rounded-full"
              :class="p.online ? 'bg-green-500' : 'bg-red-500'"
              :title="p.online ? '设备在线' : '设备离线'"
            ></span>
          </div>
          <div class="text-xs text-gray-500 mt-0.5">
            当前值：
            <span class="text-orange-300">{{ formatValue(p.value, p.type) }}</span>
            <span v-if="p.minValue !== null || p.maxValue !== null" class="ml-2">
              允许范围：{{ p.minValue ?? '−' }} ~ {{ p.maxValue ?? '+' }}
            </span>
          </div>
          <div class="flex gap-2 mt-2">
            <select
              v-if="p.type === 'coil'"
              v-model="coilDraft[p.key!]"
              class="bg-gray-700 text-xs rounded px-2 py-1 flex-1"
            >
              <option value="true">ON / true</option>
              <option value="false">OFF / false</option>
            </select>
            <input
              v-else
              v-model="numberDraft[p.key!]"
              type="number"
              :min="p.minValue ?? undefined"
              :max="p.maxValue ?? undefined"
              class="bg-gray-700 text-xs rounded px-2 py-1 flex-1 text-gray-100"
              placeholder="输入目标值"
            />
            <button
              @click="control.submit(p, (p.type === 'coil' ? coilDraft : numberDraft)[p.key!] ?? '')"
              :disabled="control.submittingKeys.has(p.key!)"
              class="bg-orange-700 hover:bg-orange-600 disabled:opacity-50 text-xs rounded px-3 py-1 text-white"
            >
              {{ control.submittingKeys.has(p.key!) ? '提交中' : '下发' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 最近一次错误提示 -->
      <div v-if="control.error" class="text-xs text-red-300 bg-red-900/40 border-l-4 border-red-500 rounded p-2">
        {{ control.error }}
      </div>

      <!-- 审计记录 -->
      <div v-if="!control.isViewer">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs text-gray-400">下发审计</h3>
          <div class="flex gap-1 text-[10px]">
            <button
              @click="setScope('mine')"
              class="px-2 py-0.5 rounded"
              :class="control.auditScope === 'mine' ? 'bg-orange-700 text-white' : 'bg-gray-800 text-gray-400'"
            >按我</button>
            <button
              @click="setScope('all')"
              class="px-2 py-0.5 rounded"
              :class="control.auditScope === 'all' ? 'bg-orange-700 text-white' : 'bg-gray-800 text-gray-400'"
            >全部操作者</button>
            <button @click="control.refreshRecords()" class="px-2 py-0.5 rounded bg-gray-800 text-gray-400">刷新</button>
          </div>
        </div>

        <div v-if="!control.records.length" class="text-xs text-gray-600 p-2">暂无下发记录</div>

        <div
          v-for="r in control.records.slice(0, 30)"
          :key="r.id"
          class="bg-gray-800 rounded p-2 mb-1.5 text-xs"
          :class="statusBorder(r.status)"
        >
          <div class="flex justify-between">
            <span class="text-gray-200">
              {{ r.pointName ?? `${r.deviceId}:${r.address}` }}
              <span class="text-gray-500">{{ r.unit }}</span>
            </span>
            <span :class="statusText(r.status)">{{ statusLabel(r.status) }}</span>
          </div>
          <div class="text-gray-400 mt-0.5">
            <span class="text-cyan-300">{{ r.operatorName }}</span>
            于 {{ new Date(r.createdAt).toLocaleString() }}
            把值改为
            <span class="text-orange-300">{{ formatValue(r.value, pointType(r)) }}</span>
            <span v-if="r.previousValue !== null" class="text-gray-500">
              （原 {{ formatValue(r.previousValue, pointType(r)) }}）
            </span>
          </div>
          <div v-if="r.retryOf" class="text-[10px] text-gray-600 mt-0.5">重试自 {{ r.retryOf }}</div>
          <div v-if="r.reason" class="text-[11px] mt-1" :class="r.status === 'success' ? 'text-green-400' : 'text-red-300'">
            {{ r.reason }}
          </div>
          <div v-if="r.retryable && r.status !== 'pending'" class="mt-1.5 flex gap-2">
            <button
              v-if="needsOnline(r)"
              @click="control.bringOnlineAndRetry(r)"
              class="bg-blue-800 hover:bg-blue-700 text-white rounded px-2 py-0.5 text-[11px]"
            >置设备在线并重试</button>
            <button
              v-else
              @click="control.retry(r)"
              class="bg-gray-700 hover:bg-gray-600 text-white rounded px-2 py-0.5 text-[11px]"
            >重试</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useControlStore } from '../store/control'
import type { PointInfo, WriteStatus, WriteRecord } from '../types'

const control = useControlStore()
const numberDraft = reactive<Record<string, string>>({})
const coilDraft = reactive<Record<string, string>>({})

watch(
  () => control.writablePoints,
  (pts) => {
    for (const p of pts) {
      if (!(p.key! in numberDraft)) numberDraft[p.key!] = String(p.value)
      if (!(p.key! in coilDraft)) coilDraft[p.key!] = p.value ? 'true' : 'false'
    }
  },
  { immediate: true },
)

function setScope(scope: 'mine' | 'all') {
  control.auditScope = scope
  void control.refreshRecords()
}

function pointType(r: WriteRecord): 'holding' | 'coil' {
  return control.points.find(p => p.key === r.pointKey)?.type ?? 'holding'
}

function formatValue(v: number | boolean, type: string) {
  if (type === 'coil') return v === true || v === 1 ? 'ON' : 'OFF'
  return typeof v === 'number' ? v : String(v)
}

function needsOnline(r: WriteRecord) {
  const point = control.points.find(p => p.key === r.pointKey)
  return r.status === 'failed' && r.retryable && point && !point.online
}

function statusLabel(s: WriteStatus) {
  return { pending: '下发中…', success: '成功', failed: '未生效', conflict: '冲突未生效' }[s]
}
function statusText(s: WriteStatus) {
  return {
    pending: 'text-yellow-400',
    success: 'text-green-400',
    failed: 'text-red-400',
    conflict: 'text-orange-400',
  }[s]
}
function statusBorder(s: WriteStatus) {
  return {
    pending: 'border-l-4 border-yellow-500',
    success: 'border-l-4 border-green-600',
    failed: 'border-l-4 border-red-600',
    conflict: 'border-l-4 border-orange-500',
  }[s]
}
</script>
