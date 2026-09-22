<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { management, managementError, networkLabel, statusLabel, type ManagedDevice, type Room, type DeviceConfig } from '@/api/management'
const props = defineProps<{ device: ManagedDevice; rooms: Room[]; editable: boolean }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const room = ref(''), status = ref(''), config = ref<DeviceConfig>({...props.device.config})
const revision = ref(0), busy = ref(false), error = ref('')
const history = ref<{revision:number;room_id:string;status:string;config:DeviceConfig}[]>([])
const abort = new AbortController()
watch(() => props.device.id, () => reset(), {immediate:true})
function reset() {
  room.value = props.device.room_id; status.value = props.device.status
  config.value = {...props.device.config}; revision.value = props.device.revision; error.value=''; history.value=[]
}
async function run(action: () => Promise<unknown>) {
  if(busy.value) return
  busy.value=true; error.value=''
  try { await action(); emit('changed'); emit('close') } catch(e) { error.value=managementError(e) } finally { busy.value=false }
}
function save() {
  if(status.value==='active' && !room.value) {error.value='请先分配会议室'; return}
  if(status.value==='revoked' && !window.confirm('撤销后设备将停止读取会议数据，确认撤销？')) return
  run(() => management('PUT', '/api/v6/admin/devices/'+props.device.id, abort.signal,
    {expected_revision:revision.value,room_id:room.value,status:status.value,config:config.value}))
}
async function loadHistory() {
  try { history.value=await management('GET',`/api/v6/admin/devices/${props.device.id}/history`,abort.signal) }
  catch(e) {error.value=managementError(e)}
}
function rollback(value: number) {
  if(window.confirm(`将历史版本 ${value} 发布为新配置？`)) run(() => management('POST',
    `/api/v6/admin/devices/${props.device.id}/rollback`,abort.signal,{expected_revision:revision.value,revision:value}))
}
onUnmounted(() => abort.abort())
</script>
<template>
  <div class="v6-backdrop" @click.self="emit('close')"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="设备详情">
    <header><div><p class="v6-eyebrow">设备 · {{ statusLabel(device.status) }}</p><h2>{{ device.code.slice(0,3) }} {{ device.code.slice(3) }}</h2></div><button class="secondary" @click="emit('close')">关闭</button></header>
    <dl class="v6-facts"><div><dt>型号</dt><dd>{{ device.metadata.model || '未上报' }}</dd></div><div><dt>SN</dt><dd>{{ device.metadata.serial || '系统未提供' }}</dd></div><div><dt>网络</dt><dd>{{ networkLabel(device.metadata.network) }}</dd></div><div><dt>APK / Android</dt><dd>{{ device.metadata.apk || '—' }} / {{ device.metadata.android || '—' }}</dd></div></dl>
    <div class="v6-interfaces" v-for="nic in device.metadata.interfaces || []" :key="nic.name"><strong>{{ nic.name }}</strong><span>MAC {{ nic.mac || '系统未提供' }}</span><span>{{ nic.addresses.join(' · ') }}</span></div>
    <p class="v6-muted">期望版本 {{ device.revision }} · 已应用 {{ device.reported_revision }} · {{ device.online ? '在线' : '离线' }}</p>
    <p v-if="device.error" class="v6-error">设备回执：{{ device.error }}</p>
    <form @submit.prevent="save"><fieldset :disabled="!editable || busy">
      <label>设备状态<select v-model="status"><option value="pending">待激活</option><option value="active">已激活</option><option value="revoked">已撤销</option></select></label>
      <label>分配会议室<select v-model="room"><option value="">请选择会议室</option><option v-for="r in rooms" :key="r.room_id" :value="r.room_id">{{ r.region }} · {{ r.name }} {{ r.location }}</option></select></label>
      <div class="v6-form-row"><label>显示方案<select v-model="config.version"><option value="v6">V6 自动适配房间方案</option><option value="v4">V4 官方签到</option><option value="v5">V5 确认使用</option></select></label><label>屏幕方向<select v-model="config.portrait"><option :value="false">横屏</option><option :value="true">竖屏</option></select></label></div>
      <label class="v6-check"><input type="checkbox" v-model="config.room_light" />同步侧边灯<span v-if="!device.metadata.light_supported">（当前型号未报告灯控支持）</span></label>
      <p class="v6-muted">连接主服务器。Wi-Fi 与有线切换无需重新激活。</p>
      <button v-if="editable" :disabled="busy">{{ busy ? '正在发布…' : '保存并下发' }}</button>
    </fieldset></form>
    <div class="v6-actions"><button class="secondary" @click="loadHistory">配置历史</button><button v-if="editable" class="secondary" :disabled="busy" @click="run(() => management('POST', '/api/v6/admin/devices/'+device.id+'/reload',abort.signal,{expected_revision:revision}))">远程刷新</button><button class="secondary" @click="reset">重置编辑</button></div>
    <ul class="v6-history"><li v-for="h in history" :key="h.revision">版本 {{ h.revision }} · {{ statusLabel(h.status) }} · {{ h.config.version.toUpperCase() }}<button v-if="editable && h.status==='active' && device.status==='active' && h.revision!==revision" class="secondary" @click="rollback(h.revision)">回退至此配置</button></li></ul>
    <p v-if="error" class="v6-error" role="alert">{{ error }}</p>
  </section></div>
</template>
