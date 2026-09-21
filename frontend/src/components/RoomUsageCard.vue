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
const pending = ref(false), failed = ref(false)
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
    monitored_occurrence_ids: state.value.monitored_occurrence_ids || [],
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
async function confirm() {
  if (pending.value || !fresh.value || !record.value || !state.value || (props.preview && (!testing.value || !testAllowed.value))) return
  if (!canConfirm.value) return
  pending.value = true; error.value = ''
  markUnresolved(record.value.id)
  try {
    // A submitting/uncertain page cannot approve a release challenge.
    await health('submitting')
    const path = props.preview ? `/api/room-control/usage/${props.roomId}/confirm` : '/api/meeting-rooms/usage/confirm'
    const result = await usageRequest<UsageState>('POST', path, token.value, abort.signal,
      { occurrence_id: record.value!.id, policy_revision: state.value!.policy.revision, session_id: sessionId })
    accept(result)
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
    <div class="usage-body">
    <h4 class="usage-state" :class="record?.state" role="status">{{ label }}</h4>
    <p v-if="preview && testing" class="notice">主控签到测试 · 仅记录确认；自动释放仍需平板在线</p>
    <template v-if="(!preview || testing) && token && fresh && state?.policy.owner === 'v5' && state?.policy.mode !== 'off'">
      <p v-if="preview && record && canConfirm">点击签到，成功后显示「已确认使用」</p>
      <p v-else-if="preview && !record">有预约且进入签到窗口后，才会显示签到按钮</p>
      <p v-else-if="preview && record?.state === 'confirmed'">服务器已保存本次签到</p>
      <p v-else-if="preview">当前预约不可签到，请核对下方状态</p>
      <p v-else-if="record?.state === 'blocked'" class="notice">本次预约受保护，不会自动释放</p>
      <p v-else-if="record?.state === 'confirmed'" class="notice">本场预约已保留</p>
      <p v-else-if="state?.policy.mode === 'observe'" class="notice">观察模式 · 仅记录，不自动释放</p>
      <p v-else-if="state?.paused" class="notice">自动释放已由管理员暂停</p>
      <p v-else-if="record && !record.verified" class="notice">自动释放待管理员登记本次预约</p>
      <p v-else-if="record" class="notice">未签到将按规则释放预约</p>
      <p v-if="record && ['pending', 'waiting', 'blocked'].includes(record.state)">签到截止 {{ clock(record.deadline) }}</p>
      <p v-if="record?.state === 'waiting' && record.release_at">{{ clock(record.release_at) }} 后核验释放，仍可补确认</p>
      <p v-if="record && now >= Date.parse(record.release_at || record.deadline) && ['pending', 'blocked'].includes(record.state)">已过确认截止时间，请使用下一场预约测试</p>
      <button v-if="record && ['pending', 'waiting', 'blocked'].includes(record.state) && now < Date.parse(record.release_at || record.deadline)" :disabled="!canConfirm || pending" class="checkin-button" @click="confirm()"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg><span>{{ pending ? '正在提交…' : '签到' }}</span></button>
    </template>
    <p v-if="preview && testAllowed && receipt" class="receipt">最近一次签到成功：{{ new Date(receipt).toLocaleString('zh-CN', { timeZone: timezone, hour12: false }) }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <details v-if="!preview && !token"><summary>管理员配置</summary><form @submit.prevent="bind">
      <input v-model="input" type="password" autocomplete="off" aria-label="V5 操作凭证" placeholder="本房间操作凭证" />
      <button>启用确认操作</button>
    </form></details>
    </div>
  </aside>
</template>

<style scoped>
.usage-card{width:100%;min-width:0;max-height:100%;display:flex;flex-direction:column;gap:14px;color:var(--text);align-self:center}
.usage-body{display:flex;flex-direction:column;gap:12px;min-height:0;overflow:auto;padding:20px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-sizing:border-box}
.usage-state{font-size:19px;line-height:1.4;font-weight:600;overflow-wrap:anywhere}.usage-state:before{content:'';display:inline-block;width:7px;height:7px;border-radius:50%;background:#8ba8df;margin-right:8px;vertical-align:middle}.usage-state.blocked:before{background:#d6a352}.usage-state.confirmed:before{background:#34c89e}
p{font-size:14px;line-height:1.5}.notice{color:var(--muted)}
button{width:100%;background:#2563eb;color:#fff;border:1px solid transparent;border-radius:999px;padding:14px 22px;font-size:17px;line-height:1.3;font-weight:600;min-height:48px;flex-shrink:0}
.checkin-button{display:flex;align-items:center;justify-content:center;gap:10px;min-height:56px;margin-top:auto;box-shadow:0 5px 14px #2563eb24;cursor:pointer}.checkin-button svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}button:focus-visible{outline:3px solid #93b4ff;outline-offset:3px}.checkin-button:not(:disabled):active{background:#1d4ed8;box-shadow:none}
button:disabled{box-shadow:none;color:var(--subtle);background:transparent;border-color:var(--line);cursor:not-allowed}
form{display:grid;gap:10px}input{width:100%;color:var(--text);background:transparent;border:1px solid var(--line);padding:10px;border-radius:8px}summary{font-size:12px;cursor:pointer}details form{margin-top:10px}[role=alert]{color:#e88862}
@media(min-width:1000px) and (max-height:760px) and (orientation:landscape){.usage-body{padding:16px;gap:10px}.usage-state{font-size:18px}}
</style>
