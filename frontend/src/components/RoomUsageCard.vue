<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { usageError, usageLabels, usageRequest, type UsageState } from '@/api/roomUsage'
import type { RoomEvent } from '@/api/meetingRooms'

const props = defineProps<{ roomId: string; roomName: string; timezone: string; now: number; fresh: boolean; preview: boolean; controlToken?: string; event?: RoomEvent }>()
const emit = defineEmits<{ changed: [] }>()
const storageKey = `argus_room_usage_v5:${props.roomId}${props.preview ? ":control-test" : ""}`
const pendingKey = `${storageKey}:unresolved`
const sessionKey = `${storageKey}:session`
const sessionId = sessionStorage.getItem(sessionKey) || Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
if (!props.preview) sessionStorage.setItem(sessionKey, sessionId)
const unresolved = ref(localStorage.getItem(pendingKey) || '')
const token = ref(props.preview ? props.controlToken || '' : localStorage.getItem(storageKey) || '')
const testAllowed = ref(false), receipt = ref('')
const testing = computed(() => props.preview && testAllowed.value)
const input = ref(''), error = ref('')
const state = ref<UsageState | null>(null)
const pending = ref(false), failed = ref(false), ending = ref(false)
const abort = new AbortController()
let timer: ReturnType<typeof setInterval> | undefined
const record = computed(() => state.value?.record)
const matches = computed(() => !record.value || (props.event && props.event.uid === record.value.occurrence.uid &&
  props.event.original_time === record.value.occurrence.original_time &&
  Date.parse(props.event.start_time) === Date.parse(record.value.occurrence.start_time) &&
  Date.parse(props.event.end_time) === Date.parse(record.value.occurrence.end_time)))
const fresh = computed(() => props.fresh && matches.value && !failed.value && !!state.value && props.now < Date.parse(state.value.valid_until))
const canConfirm = computed(() => fresh.value && state.value?.policy.owner === 'v5' && state.value?.can_confirm && record.value && props.now < Date.parse(record.value.release_at || record.value.deadline))
const label = computed(() => props.preview && !testing.value ? 'V5 预览 · 操作不可用' : !token.value ? '确认使用尚未配置' :
  !fresh.value ? '确认状态待同步' : state.value?.policy.owner !== 'v5' ? '本房间使用官方方案，请切换到 V4' : state.value?.policy.mode === 'off' ? '确认使用已关闭' :
  record.value ? usageLabels[record.value.state] || '状态待核实' : props.preview && !state.value?.target_id ? '当前没有可签到的预约' : '等待下一场确认窗口')
const clock = (value: string) => new Date(value).toLocaleTimeString('zh-CN', { timeZone: props.timezone, hour: '2-digit', minute: '2-digit', hour12: false })
function markUnresolved(id: string) {
  unresolved.value = id
  if (id) localStorage.setItem(pendingKey, id)
  else localStorage.removeItem(pendingKey)
}
watch(() => props.fresh, value => {
  if (!value && !props.preview && record.value && ['pending', 'waiting', 'checking', 'end_requested'].includes(record.value.state)) markUnresolved(record.value.id)
})
function accept(result: UsageState) {
  if (!result || result.room_id !== props.roomId || !Number.isFinite(Date.parse(result.valid_until))) throw new Error('Invalid usage state')
  state.value = result
  if (result.record?.state === 'confirmed' || (result.target_id && result.target_id !== unresolved.value)) markUnresolved('')
}
async function health(operation?: 'submitting' | 'uncertain') {
  if (props.preview || !state.value || state.value.policy.owner !== 'v5' || state.value.policy.mode === 'off' || !props.fresh || !matches.value || document.hidden) return
  const status = operation || (unresolved.value === state.value.target_id ? 'uncertain' : 'ready')
  const result = await usageRequest<UsageState>('POST', '/api/meeting-rooms/usage/heartbeat', token.value, abort.signal, {
    protocol: 2, session_id: sessionId, occurrence_id: state.value.target_id, policy_revision: state.value.policy.revision,
    operation_state: status, challenge_id: status === 'ready' && record.value?.state === 'checking' ? record.value.challenge_id : null,
  })
  accept(result)
}
async function refresh() {
  if (!token.value || pending.value || document.hidden || abort.signal.aborted) return
  pending.value = true
  try {
    if (props.preview) {
      const result = await usageRequest<{ usage: UsageState; control_confirm_enabled: boolean; audit?: { time: string; action: string; state: string }[] }>('GET', `/api/room-control/usage/${props.roomId}`, token.value, abort.signal)
      receipt.value = result.audit?.find(item => ['control_confirm', 'confirm'].includes(item.action) && item.state === 'confirmed' && Number.isFinite(Date.parse(item.time)))?.time || ''
      accept(result.usage); testAllowed.value = result.control_confirm_enabled === true && result.usage.policy.owner === 'v5' && result.usage.policy.mode !== 'off'
    } else {
      const result = await usageRequest<UsageState>('GET', '/api/meeting-rooms/usage', token.value, abort.signal)
      accept(result)
      if (props.now < Date.parse(result.valid_until)) await health()
    }
    failed.value = false; error.value = ''
  } catch (err) {
    if (axios.isCancel(err)) return
    failed.value = true; error.value = usageError(err)
    if (record.value && ['pending', 'waiting', 'checking', 'end_requested'].includes(record.value.state)) markUnresolved(record.value.id)
    if (axios.isAxiosError(err) && err.response?.status === 401) {
      if (!props.preview) localStorage.removeItem(storageKey)
      token.value = ''; state.value = null; testAllowed.value = false
    }
  } finally { pending.value = false }
}
function bind() {
  const value = input.value.trim()
  if (!value.startsWith(`usage:${props.roomId}:`) || !/^usage:omm_[A-Za-z0-9]+:[A-Za-z0-9_-]{43}$/.test(value)) {
    error.value = '请输入本房间的 V5 操作凭证'; return
  }
  token.value = value; localStorage.setItem(storageKey, value); input.value = ''; refresh()
}
async function act(action: 'confirm' | 'end') {
  if (pending.value || !fresh.value || !record.value || !state.value || (props.preview && (!testing.value || !testAllowed.value || action !== 'confirm'))) return
  if (action === 'confirm' ? !canConfirm.value : !state.value.can_end) return
  pending.value = true; error.value = ''; ending.value = false
  markUnresolved(record.value.id)
  try {
    // A submitting/uncertain page cannot approve a release challenge.
    if (action === 'confirm') await health('submitting')
    const path = props.preview ? `/api/room-control/usage/${props.roomId}/confirm` : `/api/meeting-rooms/usage/${action}`
    const result = await usageRequest<UsageState>('POST', path, token.value, abort.signal,
      { occurrence_id: record.value!.id, policy_revision: state.value!.policy.revision, session_id: sessionId })
    accept(result)
    if (action === 'end' && result.record?.state === 'end_requested') markUnresolved('')
    failed.value = false; emit('changed')
  } catch (err) {
    if (!axios.isCancel(err)) { failed.value = true; error.value = usageError(err) }
  } finally { pending.value = false }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 10000) })
onUnmounted(() => { abort.abort(); clearInterval(timer) })
</script>

<template>
  <aside class="usage-card" aria-label="V5 确认使用">
    <p class="eyebrow">ROOMBEACON · V5</p>
    <h3 role="status">{{ label }}</h3>
    <p v-if="preview && testing" class="notice">主控签到测试 · 仅记录确认；自动释放仍需平板在线</p>
    <template v-if="(!preview || testing) && token && fresh && state?.policy.owner === 'v5' && state?.policy.mode !== 'off'">
      <p v-if="preview && record && canConfirm">点击「确认使用」后提交签到，显示「已确认使用」即成功</p>
      <p v-else-if="preview && !record">有预约且进入签到窗口后，才会显示签到按钮</p>
      <p v-else-if="preview && record?.state === 'confirmed'">服务器已保存本次签到</p>
      <p v-else-if="preview">当前预约不可签到，请核对下方状态</p>
      <p v-else-if="state?.policy.mode === 'observe'" class="notice">观察模式 · 仅记录，不自动释放</p>
      <p v-else-if="state?.paused" class="notice">自动释放已由管理员暂停</p>
      <p v-else class="notice">未在截止前确认，将按规则释放预约</p>
      <p v-if="record">确认截止 {{ clock(record.deadline) }}</p>
      <p v-if="record?.state === 'waiting' && record.release_at">{{ clock(record.release_at) }} 后核验释放，仍可补确认</p>
      <p v-if="record && now >= Date.parse(record.release_at || record.deadline) && ['pending', 'blocked'].includes(record.state)">已过确认截止时间，请使用下一场预约测试</p>
      <p v-if="record?.state === 'blocked'">本次预约受保护，恢复后也不会自动补释放</p>
      <button v-if="record && ['pending', 'waiting', 'blocked'].includes(record.state)" :disabled="!canConfirm || pending" @click="act('confirm')">{{ pending ? '正在提交…' : '确认使用' }}</button>
      <button v-if="!preview && state?.can_end && !ending" class="secondary" :disabled="pending" @click="ending = true">提前结束</button>
      <div v-if="ending && record" class="end-confirm" role="group" aria-label="确认提前结束">
        <p>释放 {{ roomName }} 本次 {{ clock(record.occurrence.start_time) }}—{{ clock(record.occurrence.end_time) }} 的预约？</p>
        <button :disabled="pending || !state?.can_end" @click="act('end')">确认释放本次预约</button>
        <button class="secondary" @click="ending = false">取消</button>
      </div>
    </template>
    <p v-if="preview && testAllowed && receipt" class="receipt">最近一次签到成功：{{ new Date(receipt).toLocaleString('zh-CN', { timeZone: timezone, hour12: false }) }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <details v-if="!preview && !token"><summary>管理员配置</summary><form @submit.prevent="bind">
      <input v-model="input" type="password" autocomplete="off" aria-label="V5 操作凭证" placeholder="本房间操作凭证" />
      <button>启用确认操作</button>
    </form></details>
    <p class="footnote">确认结果由 RoomBeacon 记录</p>
  </aside>
</template>

<style scoped>
.usage-card{width:100%;max-height:100%;overflow:auto;padding:20px;border:1px solid var(--line);border-radius:16px;background:var(--surface);color:var(--text);display:flex;flex-direction:column;gap:12px;align-self:center}
.eyebrow,.footnote,small{font-size:11px;color:var(--muted)}h3{font-size:24px;line-height:1.25;font-weight:600}p{font-size:14px;line-height:1.5}.notice{color:var(--muted)}button{width:100%;background:#4f46e5;color:white;border-radius:8px;padding:12px;font-size:17px}button:disabled{opacity:.4;cursor:not-allowed}.secondary{background:transparent;color:var(--text);border:1px solid var(--line)}form,.end-confirm{display:grid;gap:10px}input{width:100%;color:var(--text);background:transparent;border:1px solid var(--line);padding:10px;border-radius:6px}summary{font-size:12px;cursor:pointer}details form{margin-top:10px}[role=alert]{color:#e88862}
</style>
