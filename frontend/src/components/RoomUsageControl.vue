<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { usageError, usageLabels, usageRequest, type UsageState, type UsagePolicy } from '@/api/roomUsage'
const props = defineProps<{ roomId: string; roomName: string; token: string; readOnly?:boolean; templateManaged?:boolean }>()
const abort = new AbortController()
const usage = ref<UsageState | null>(null), audit = ref<{ time: string; action: string; state?: string; reason?: string; paused?: boolean; mode?: string }[]>([])
const policy = ref<UsagePolicy | null>(null)
const error = ref(''), notice = ref(''), busy = ref(false), verified = ref(false), writes = ref(false)
const path = `/api/room-control/usage/${props.roomId}`
async function load() {
  const result = await usageRequest<{ usage: UsageState; audit: typeof audit.value; global_audit: typeof audit.value; writes_enabled: boolean }>('GET', path, props.token, abort.signal)
  usage.value = result.usage; policy.value = { ...result.usage.policy }
  audit.value = [...result.audit, ...(result.global_audit || [])].sort((a, b) => b.time.localeCompare(a.time)).slice(0, 100)
  writes.value = result.writes_enabled
}
async function run(action: 'load' | 'save' | 'verify' | 'pause' | 'resume') {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (action === 'save' && policy.value) {
      if(props.readOnly)return
      if(props.templateManaged)await usageRequest('POST', '/api/v6/admin/rooms/'+props.roomId+'/qualification', props.token, abort.signal, {expected_revision:policy.value.revision,native_policy_cleared:policy.value.native_policy_cleared,release_verified:policy.value.release_verified})
      else await usageRequest('PUT',path+'/policy',props.token,abort.signal,policy.value)
    }
    if (action === 'verify' && usage.value?.record && verified.value) await usageRequest('POST', path + '/verify', props.token, abort.signal,
      { occurrence_id: usage.value.record.id, policy_revision: usage.value.policy.revision, non_recurring_verified: true })
    if (action === 'pause' || action === 'resume') await usageRequest('PUT', '/api/room-control/usage-pause', props.token, abort.signal, { paused: action === 'pause' })
    await load(); verified.value = false
    if (action !== 'load') notice.value = '已保存，请核对当前状态'
  } catch (err) { if (!abort.signal.aborted) error.value = usageError(err) }
  finally { busy.value = false }
}
onMounted(() => run('load'))
onUnmounted(() => abort.abort())
</script>
<template>
  <section class="usage-control" aria-label="V5 使用规则">
    <h2>V5 使用规则 · {{ roomName }}</h2><p>此处管理规则；门牌预览始终不可确认或释放预约。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <form v-if="policy" @submit.prevent="run('save')">
      <p v-if="templateManaged">业务参数由软件模板管理，修改参数请编辑模板并部署。这里记录本房间的核验结果。</p><fieldset :disabled="readOnly||templateManaged"><label>签到方案<select v-model="policy.owner" @change="policy.mode = 'off'"><option value="official">V4 · 飞书官方</option><option value="v5">V5 · 平板与服务器</option></select></label>
      <p>切换页面不会切换方案。V5 须关闭本房间官方未签到释放；回退 V4 需在飞书恢复原规则。</p>
      <label>运行模式<select v-model="policy.mode"><option value="off">关闭</option><option value="observe">观察 · 不释放</option><option value="auto">自动释放 · 仅已核验实例</option></select></label>
      <label>提前开放确认（分钟）<input v-model.number="policy.early_minutes" type="number" min="1" max="30" /></label>
      <label>开始后宽限（分钟）<input v-model.number="policy.grace_minutes" type="number" min="1" max="30" /></label>
      <label>待释放补确认（秒）<input v-model.number="policy.release_delay_seconds" type="number" min="30" max="300" /></label>
      </fieldset><label><input :disabled="readOnly" v-model="policy.native_policy_cleared" type="checkbox" />已关闭本房间飞书未签到自动释放</label>
      <label><input :disabled="readOnly" v-model="policy.release_verified" type="checkbox" />已在专用预约验证公开释放接口及影响范围</label>
      <button v-if="!readOnly" :disabled="busy">{{templateManaged?'保存房间核验':'保存房间规则'}}</button>
    </form>
    <template v-if="usage">
      <p>服务端写入：{{ writes ? '已开放' : '未开放' }} · 全局释放：{{ usage.paused ? '已暂停' : '未暂停' }}</p>
      <div v-if="!readOnly" class="buttons"><button :disabled="busy" @click="run('pause')">暂停所有房间释放</button><button :disabled="busy || !writes" @click="run('resume')">解除全局暂停</button></div>
      <div v-if="usage.record&&!readOnly" class="verify">
        <p>目标时间：{{ new Date(usage.record.occurrence.start_time).toLocaleString() }} — {{ new Date(usage.record.occurrence.end_time).toLocaleTimeString() }}</p>
        <p>{{ usageLabels[usage.record.state] }} · 单次预约核验：{{ usage.record.verified ? '已登记' : '未登记' }}</p>
        <label><input v-model="verified" type="checkbox" />我已核对这是一场允许释放的非重复预约</label>
        <button :disabled="busy || !verified" @click="run('verify')">仅登记当前实例</button>
      </div>
      <button :disabled="busy" @click="run('load')">刷新状态</button>
      <details><summary>最近操作（最多 100 条）</summary><ol><li v-for="(entry, i) in audit" :key="i">{{ entry.time }} · {{ entry.action }} · {{ entry.state }} · {{ entry.reason }} {{ entry.mode }} {{ entry.paused === undefined ? '' : entry.paused ? '全局暂停' : '解除全局暂停' }}</li></ol></details>
    </template>
  </section>
</template>
<style scoped>
.usage-control{margin-top:24px;padding:24px;background:white;border:1px solid #dbe2ea;border-radius:12px;color:#182536;display:grid;gap:14px}h2{font-size:22px;font-weight:600}form{display:grid;gap:12px;max-width:680px}label{display:flex;gap:10px;align-items:center}select,input[type=number]{border:1px solid #cbd5e1;border-radius:6px;padding:8px}button{padding:10px 14px;border-radius:8px;background:#4f46e5;color:white;width:fit-content}button:disabled{opacity:.4}.buttons{display:flex;gap:12px;flex-wrap:wrap}.verify{display:grid;gap:10px;padding:16px;border:1px solid #cbd5e1}li{font-size:12px;overflow-wrap:anywhere;margin-top:6px}[role=alert]{color:#b91c1c}
</style>
