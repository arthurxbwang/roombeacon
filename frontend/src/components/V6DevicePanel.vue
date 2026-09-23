<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import V6RoomFilter from './V6RoomFilter.vue'
import {emptyScope,matchesScope,roomMatches,type RoomScope} from '@/composables/roomScope'
import type {ConfigTemplate} from '@/api/management'
import { defaultConfig, confirmModelOverride, profileNotice, profileCapabilityNotice, profileMismatch, type DeviceProfile, management, managementError, networkLabel, statusLabel, type ManagedDevice, type Room, type DeviceConfig } from '@/api/management'
const props = defineProps<{ device: ManagedDevice; rooms: Room[]; templates:ConfigTemplate[]; initialScope:RoomScope; editable: boolean; profiles: DeviceProfile[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const room = ref(''), status = ref(''), config = ref<DeviceConfig>({...props.device.config})
const scope=ref(emptyScope()), search=ref(''), templateId=ref('')
const filteredRooms=computed(()=>props.rooms.filter(r=>matchesScope(r,scope.value)&&roomMatches(r,search.value)))
const chosenTemplate=ref<ConfigTemplate|null>(null)
watch(filteredRooms,()=>{if(room.value&&!filteredRooms.value.some(r=>r.room_id===room.value))room.value=''})
function chooseTemplate(){const t=props.templates.find(t=>t.id===templateId.value);chosenTemplate.value=t?{...t,config:{...t.config}}:null;config.value={...defaultConfig,...(chosenTemplate.value?.config||props.device.config)}}
const revision = ref(0), busy = ref(false), error = ref('')
const history = ref<{revision:number;room_id:string;status:string;config:DeviceConfig}[]>([])
const abort = new AbortController()
const mismatch=computed(()=>profileMismatch(config.value,props.device,props.profiles))
watch(() => props.device.id, () => reset(), {immediate:true})
function reset() {
  scope.value={region:props.initialScope.region==='@unassigned'?'':props.initialScope.region,path:[...props.initialScope.path]};search.value='';templateId.value='';chosenTemplate.value=null
  room.value = props.device.room_id; status.value = props.device.status
  config.value = {...defaultConfig,...props.device.config}; revision.value = props.device.revision; error.value=''; history.value=[]
}
async function run(action: () => Promise<unknown>) {
  if(busy.value) return
  busy.value=true; error.value=''
  try { await action(); emit('changed'); emit('close') } catch(e) { error.value=managementError(e) } finally { busy.value=false }
}
function save() {
  if(busy.value)return
  if(status.value==='active' && !room.value) {error.value='请先分配会议室'; return}
  if(status.value==='revoked' && !window.confirm('撤销后设备将停止读取会议数据，确认撤销？')) return
  const confirmed=status.value==='active' ? confirmModelOverride(config.value,[props.device],props.profiles) : false
  if(confirmed===null)return
  run(() => management('PUT', '/api/v6/admin/devices/'+props.device.id, abort.signal,
    {expected_revision:revision.value,room_id:room.value,status:status.value,config:config.value,confirm_model_mismatch:confirmed,...(chosenTemplate.value?{template_id:chosenTemplate.value.id,template_revision:chosenTemplate.value.revision}:{})}))
}
async function loadHistory() {
  try { history.value=await management('GET',`/api/v6/admin/devices/${props.device.id}/history`,abort.signal) }
  catch(e) {error.value=managementError(e)}
}
function rollback(value: number) {
  if(busy.value)return
  const entry=history.value.find(h=>h.revision===value)
  if(!entry)return
  const confirmed=confirmModelOverride({...defaultConfig,...entry.config},[props.device],props.profiles,`回退到历史版本 ${value}`)
  if(confirmed===null || (!confirmed && !window.confirm(`将历史版本 ${value} 发布为新配置？`)))return
  run(() => management('POST', `/api/v6/admin/devices/${props.device.id}/rollback`,abort.signal,
    {expected_revision:revision.value,revision:value,confirm_model_mismatch:confirmed}))
}
onUnmounted(() => abort.abort())
</script>
<template>
  <div class="v6-backdrop" @click.self="emit('close')"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="设备详情">
    <header><div><p class="v6-eyebrow">设备 · {{ statusLabel(device.status) }}</p><h2>{{ device.code.slice(0,3) }} {{ device.code.slice(3) }}</h2></div><button class="secondary" @click="emit('close')">关闭</button></header>
    <dl class="v6-facts"><div><dt>型号</dt><dd>{{ device.metadata.model || '未上报' }}</dd></div><div><dt>SN</dt><dd>{{ device.metadata.serial || '系统未提供' }}</dd></div><div><dt>网络</dt><dd>{{ networkLabel(device.metadata.network) }}</dd></div><div><dt>APK / Android</dt><dd>{{ device.metadata.apk || '—' }} / {{ device.metadata.android || '—' }}</dd></div></dl>
    <div class="v6-interfaces" v-for="nic in device.metadata.interfaces || []" :key="nic.name"><strong>{{ nic.name }}</strong><span>MAC {{ nic.mac || '系统未提供' }}</span><span>{{ nic.addresses.join(' · ') }}</span></div>
    <p class="v6-muted">设备固件：{{ device.metadata.firmware || '未上报' }}</p>
    <p class="v6-muted">期望版本 {{ device.revision }} · 已应用 {{ device.reported_revision }} · {{ device.online ? '在线' : '离线' }}</p>
    <p v-if="device.error" class="v6-error">设备回执：{{ device.error }}</p>
    <form @submit.prevent="save"><fieldset :disabled="!editable || busy">
      <label>设备状态<select v-model="status"><option value="pending">待激活</option><option value="active">已激活</option><option value="revoked">已撤销</option></select></label>
      <V6RoomFilter :rooms="rooms" v-model="scope" />
      <label>会议室关键词<input v-model="search" aria-label="会议室关键词" placeholder="输入会议室名称或位置" /></label>
      <label>分配会议室<select aria-label="分配会议室" v-model="room"><option value="">请选择会议室</option><option v-for="r in filteredRooms" :key="r.room_id" :value="r.room_id">{{ r.region }} · {{ r.name }} {{ r.location }}</option></select></label>
      <p class="v6-muted">当前筛选 {{filteredRooms.length}} 间会议室。</p>
      <label>硬件安装模板<select v-model="templateId" aria-label="硬件安装模板" @change="chooseTemplate"><option value="">保留当前设备配置</option><option v-for="t in templates" :key="t.id" :value="t.id">{{t.name}} · 第 {{t.revision}} 版</option></select></label>
      <p class="v6-muted">{{config.portrait?'竖屏':'横屏'}} · 灯控{{config.room_light?'开启':'关闭'}} · {{config.version.toUpperCase()}} 页面。方向与灯控在配置模板中编辑。</p>
      <p class="v6-muted">会议室的签到与释放规则由会议室业务方案决定。</p>
      <p class="v6-muted">{{ mismatch || profileNotice(config) }}</p>
      <p v-if="profileCapabilityNotice(config,device)" class="v6-muted">{{ profileCapabilityNotice(config,device) }}</p>
      <p class="v6-muted">连接主服务器。Wi-Fi 与有线切换无需重新激活。</p>
      <button v-if="editable" :disabled="busy">{{ busy ? '正在发布…' : '保存并下发' }}</button>
    </fieldset></form>
    <div class="v6-actions"><button class="secondary" @click="loadHistory">配置历史</button><button v-if="editable" class="secondary" :disabled="busy" @click="run(() => management('POST', '/api/v6/admin/devices/'+device.id+'/reload',abort.signal,{expected_revision:revision}))">远程刷新</button><button class="secondary" @click="reset">重置编辑</button></div>
    <ul class="v6-history"><li v-for="h in history" :key="h.revision">版本 {{ h.revision }} · {{ statusLabel(h.status) }} · {{ h.config.version.toUpperCase() }}<button v-if="editable && h.status==='active' && device.status==='active' && h.revision!==revision" class="secondary" @click="rollback(h.revision)">回退至此配置</button></li></ul>
    <p v-if="error" class="v6-error" role="alert">{{ error }}</p>
  </section></div>
</template>
