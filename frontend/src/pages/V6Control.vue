<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import axios from 'axios'
import V6ConfigFields from '@/components/V6ConfigFields.vue'
import V6DevicePanel from '@/components/V6DevicePanel.vue'
import RoomDisplay from './RoomDisplay.vue'
import {defaultConfig,confirmModelOverride,profileNotice,profileCapabilityNotice,profileMismatch,type DeviceProfile,management,managementError,networkLabel,statusLabel,type DeviceConfig,type ManagedDevice,type Manager,type Room} from '@/api/management'
import './v6Control.css'
const abort=new AbortController()
const user=ref<Manager|null>(null), error=ref(''), info=ref(''), busy=ref(false), checking=ref(true)
const awaitingPermission=ref(false)
const devices=ref<ManagedDevice[]>([]), rooms=ref<Room[]>([]), selected=ref<ManagedDevice|null>(null)
const search=ref(''), filter=ref('all'), tab=ref('devices'), feishu=ref(false), preview=ref('')
const users=ref<{subject:string;name:string;role:string}[]>([]), logs=ref<{id:number;time:number;actor:string;action:string;target:string;detail?:{model_override?:boolean}}[]>([])
const templates=ref<{id:string;name:string;config:DeviceConfig}[]>([]), templateName=ref(''), templateId=ref('')
const draftConfig=ref<DeviceConfig>({...defaultConfig,device_profile:'bx68'}), checked=ref<string[]>([])
const profiles=ref<DeviceProfile[]>([])
const selectedTemplate=computed(()=>templates.value.find(t=>t.id===templateId.value))
const batchTargets=computed(()=>devices.value.filter(d=>checked.value.includes(d.id)))
const batchMismatches=computed(()=>selectedTemplate.value ? batchTargets.value.filter(d=>profileMismatch({...defaultConfig,...selectedTemplate.value!.config},d,profiles.value)) : [])
const batchCapability=computed(()=>selectedTemplate.value ? batchTargets.value.map(d=>profileCapabilityNotice({...defaultConfig,...selectedTemplate.value!.config},d)).find(Boolean) || '' : '')
const profileName=(config:DeviceConfig)=>profiles.value.find(p=>p.id===config.device_profile)?.name || '旧模板 · 未指定型号'
const editable=computed(() => user.value?.role==='admin')
const pending=computed(() => devices.value.filter(d => d.status==='pending').length)
const online=computed(() => devices.value.filter(d => d.online && d.status==='active').length)
const filtered=computed(() => devices.value.filter(d => (filter.value==='all'||d.status===filter.value) &&
  `${d.code} ${d.metadata.serial} ${d.metadata.model} ${d.metadata.interfaces?.map(i=>i.mac).join(' ')} ${roomName(d.room_id)}`.toLowerCase().includes(search.value.replace(/ /g,'').toLowerCase())))
const roomName=(id:string) => {const r=rooms.value.find(r=>r.room_id===id);return r?`${r.region} · ${r.name}`:'未分配'}
let timer:ReturnType<typeof setInterval>|undefined
let loading=false
async function load() {
  if(!user.value||loading||abort.signal.aborted)return
  loading=true
  try {
    const [list,directory,presets,catalog]=await Promise.all([
      management<ManagedDevice[]>('GET','/api/v6/admin/devices',abort.signal),
      management<Room[]>('GET','/api/room-control/rooms',abort.signal),
      management<typeof templates.value>('GET','/api/v6/admin/templates',abort.signal),
      management<DeviceProfile[]>('GET','/api/v6/admin/device-profiles',abort.signal)])
    devices.value=list;rooms.value=directory;templates.value=presets;profiles.value=catalog
    checked.value=checked.value.filter(id=>list.some(d=>d.id===id&&d.status==='active'))
    if(tab.value==='users'&&editable.value)users.value=await management('GET','/api/v6/auth/users',abort.signal)
    if(tab.value==='audit')logs.value=await management('GET','/api/v6/admin/audit',abort.signal)
  }catch(e){if(!axios.isCancel(e))error.value=managementError(e)}finally{loading=false}
}
async function identify() {
  awaitingPermission.value=false
  try {
    user.value=await management<Manager>('GET','/api/v6/auth/me',abort.signal)
    axios.defaults.headers.common['X-RB-CSRF']=user.value.csrf
    await load()
  }catch(e){if(axios.isAxiosError(e)&&e.response?.status===403){awaitingPermission.value=true;error.value='飞书身份已识别，等待管理员授予管理员或只读权限。授权后请重新登录。'}}
  finally{checking.value=false}
}
async function logout(){
  try{await management('POST','/api/v6/auth/logout',abort.signal,{}, {'X-RB-Logout':'1'});user.value=null;awaitingPermission.value=false;devices.value=[];preview.value='';error.value='';delete axios.defaults.headers.common['X-RB-CSRF']}
  catch(e){error.value=managementError(e)}
}
async function operate(action:()=>Promise<unknown>){
  busy.value=true;error.value='';info.value=''
  try{await action();info.value='操作已保存，设备应用后会更新回执。';await load()}
  catch(e){error.value=managementError(e)}finally{busy.value=false}
}
async function switchTab(value:string){tab.value=value;await load()}
function publishBatch(){
  if(busy.value)return
  if(!selectedTemplate.value){error.value='请选择配置模板';return}
  const config={...defaultConfig,...selectedTemplate.value.config}
  const targets=Object.fromEntries(batchTargets.value.map(d=>[d.id,d.revision]))
  if(!Object.keys(targets).length){error.value='请先选择已激活设备';return}
  const confirmed=confirmModelOverride(config,batchTargets.value,profiles.value)
  if(confirmed===null)return
  operate(()=>management('POST','/api/v6/admin/batch-config',abort.signal,
    {devices:targets,config,confirm_model_mismatch:confirmed}))
}
function copyTemplate(t:typeof templates.value[number]){templateName.value=t.name+' · 副本';draftConfig.value={...defaultConfig,...t.config};if(draftConfig.value.device_profile==='auto'){draftConfig.value.device_profile='generic';draftConfig.value.room_light=false}}
onMounted(async()=>{
  if(new URLSearchParams(location.search).has('login_error'))error.value='飞书登录未完成，请重试；首次登录请确认员工在应用与通讯录可用范围内。'
  try{feishu.value=(await management<{feishu:boolean}>('GET','/api/v6/auth/options',abort.signal)).feishu}catch{error.value='V6 管理服务暂不可用'}
  await identify();timer=setInterval(()=>{if(!document.hidden)load()},15000)
})
onUnmounted(()=>{abort.abort();clearInterval(timer);delete axios.defaults.headers.common['X-RB-CSRF']})
</script>
<template>
  <div v-if="preview && user" class="v6-preview"><nav><button @click="preview=''">返回 V6 后台</button><span>会议室预览 · {{ roomName(preview) }}</span></nav><RoomDisplay :key="preview" :control-room="preview" control-token="@session" display-version="v6" /></div>
  <main v-else class="v6-control">
    <header class="v6-top"><a class="v6-brand" href="/control"><span class="v6-logo">B</span><div>RoomBeacon <b>V6</b><small>会议灯塔 · 集中管理</small></div></a><div v-if="user" class="v6-account"><span>{{ user.name }} · {{ editable ? '管理员' : '只读' }}</span><button class="secondary" @click="logout">退出登录</button></div></header>
    <section v-if="!user" class="v6-login"><p class="v6-eyebrow">ROOMBEACON CONTROL</p><h1>飞书登录会议灯塔</h1><p class="v6-muted">使用企业飞书账号，统一管理会议门牌。</p><p v-if="checking">正在检查登录状态…</p><template v-else><a v-if="feishu" class="v6-primary-link" href="/api/v6/auth/feishu/start">飞书扫码 / 快捷登录</a><p v-else class="v6-muted">飞书登录暂不可用，请联系管理员。</p><p v-if="feishu" class="v6-muted v6-login-hint">在飞书授权页扫码，或使用已登录的飞书账号快捷进入。</p><button v-if="awaitingPermission" class="v6-text" @click="logout">退出登录</button></template><p class="v6-error" role="alert">{{ error }}</p></section>
    <template v-else>
      <section class="v6-heading"><div><p class="v6-eyebrow">中央管理 · 主服务器</p><h1>设备与部署</h1><p class="v6-muted">从这里分配会议室，配置会自动送达门牌。</p></div><button class="secondary" @click="load">刷新状态</button></section>
      <section class="v6-stats"><article><span>设备总数</span><strong>{{ devices.length }}</strong></article><article><span>待激活</span><strong>{{ pending }}</strong></article><article><span>在线运行</span><strong>{{ online }}</strong></article><article><span>会议室</span><strong>{{ rooms.length }}</strong></article></section>
      <nav class="v6-tabs"><button v-for="t in [{id:'devices',label:'设备台账'},{id:'rooms',label:'会议室'},{id:'templates',label:'配置模板'},...(editable?[{id:'users',label:'账号权限'}]:[]),{id:'audit',label:'操作记录'}]" :key="t.id" :class="{active:tab===t.id}" @click="switchTab(t.id)">{{ t.label }}</button></nav>
      <p v-if="error" class="v6-error" role="alert">{{ error }}</p><p v-if="info" class="v6-info" role="status">{{ info }}</p>
      <section v-if="tab==='devices'" class="v6-card"><div class="v6-toolbar"><input v-model="search" aria-label="搜索设备" placeholder="搜索唯一码、SN、MAC 或会议室" /><select v-model="filter" aria-label="设备状态"><option value="all">全部设备</option><option value="pending">待激活</option><option value="active">已激活</option><option value="revoked">已撤销</option></select></div>
        <div class="v6-table-wrap"><table><thead><tr><th v-if="editable">选择</th><th>唯一码 / 型号</th><th>资产信息</th><th>会议室</th><th>状态 / 网络</th><th>配置回执</th><th>操作</th></tr></thead><tbody><tr v-for="d in filtered" :key="d.id"><td v-if="editable"><input type="checkbox" v-model="checked" :value="d.id" :disabled="d.status!=='active'" :aria-label="'选择 '+d.code" /></td><td><strong class="v6-code">{{ d.code.slice(0,3) }} {{ d.code.slice(3) }}</strong><small>{{ d.metadata.model || '未上报型号' }}</small></td><td><span>SN {{ d.metadata.serial || '系统未提供' }}</span><small v-for="nic in d.metadata.interfaces?.filter(n=>n.mac)" :key="nic.name">{{ nic.name }} {{ nic.mac }}</small></td><td>{{ roomName(d.room_id) }}</td><td><span class="v6-badge" :class="{online:d.online}">{{ statusLabel(d.status) }} · {{ d.online?'在线':'离线' }}</span><small>{{ networkLabel(d.metadata.network) }}</small></td><td><span :class="{'v6-error':!!d.error}">{{ d.error?'应用异常':d.reported_revision===d.revision?'已生效':'待设备应用' }}</span><small>{{ d.reported_revision }} / {{ d.revision }}</small></td><td><button class="secondary" @click="selected=d">{{ editable?'配置':'查看' }}</button></td></tr></tbody></table><div v-if="!filtered.length" class="v6-empty"><h3>等待设备连接</h3><p>门牌启动并联网后会自动出现在这里，使用屏幕上的唯一码核对设备。</p></div></div>
        <div v-if="editable && checked.length" class="v6-batch"><strong>已选 {{ checked.length }} 台</strong><select v-model="templateId"><option value="">选择配置模板</option><option v-for="t in templates" :value="t.id" :key="t.id">{{ t.name }} · {{ profileName(t.config) }}</option></select><button :disabled="busy||!selectedTemplate" @click="publishBatch">批量下发</button><span v-if="selectedTemplate" class="v6-muted">{{ batchMismatches.length ? `${batchTargets.length-batchMismatches.length} 台型号相同，${batchMismatches.length} 台型号不同，二次确认后可强制下发` : profileNotice(selectedTemplate.config) }}</span><span v-if="batchCapability" class="v6-muted">{{ batchCapability }}</span></div>
      </section>
      <section v-if="tab==='rooms'" class="v6-card"><div class="v6-room-grid"><button v-for="r in rooms" :key="r.room_id" class="v6-room" @click="preview=r.room_id"><small>{{ r.region }} · {{ r.location }}</small><strong>{{ r.name }}</strong><span>查看门牌 →</span></button></div></section>
      <section v-if="tab==='templates'" class="v6-card v6-presets"><h2>配置模板</h2><p class="v6-muted">按设备型号保存显示、语言与灯控设置。批量下发保留每台设备的会议室绑定。</p>
        <ul class="v6-template-list"><li v-for="t in templates" :key="t.id"><strong>{{ t.name }}</strong><p>{{ profileName(t.config) }} · {{ t.config.version.toUpperCase() }} · {{ t.config.portrait?'竖屏':'横屏' }}</p><p>{{ t.config.theme_mode==='light'?'始终白天':'自动昼夜' }} · {{ t.config.language==='en'?'English':'简体中文' }} · 灯控{{ t.config.room_light?'开启':'关闭' }}</p><button v-if="editable" class="secondary" @click="copyTemplate(t)">复制调整</button></li></ul>
        <form v-if="editable" @submit.prevent="operate(()=>management('POST','/api/v6/admin/templates',abort.signal,{name:templateName.trim(),config:draftConfig}))"><fieldset :disabled="busy"><label>模板名称<input v-model="templateName" required maxlength="80" pattern=".*\S.*" /></label><V6ConfigFields v-model="draftConfig" :profiles="profiles" /><button :disabled="busy||!profiles.length">保存模板</button></fieldset></form>
      </section>
      <section v-if="tab==='users' && editable" class="v6-card v6-table-wrap"><table><thead><tr><th>飞书用户</th><th>权限</th><th>操作</th></tr></thead><tbody><tr v-for="u in users" :key="u.subject"><td>{{ u.name }}<small>{{ u.subject.slice(0,12) }}</small></td><td>{{ {admin:'管理员',viewer:'只读',pending:'待授权',disabled:'已停用'}[u.role] || u.role }}</td><td><button v-for="role in ['admin','viewer','disabled']" :key="role" class="secondary" :disabled="busy || u.subject===user.subject || u.role===role" @click="operate(()=>management('PUT','/api/v6/auth/users/'+u.subject,abort.signal,{role}))">{{ {admin:'授予管理员',viewer:'设为只读',disabled:'停用'}[role] }}</button></td></tr></tbody></table><p v-if="!users.length" class="v6-empty">用户首次飞书登录后，会出现在待授权列表。</p></section>
      <section v-if="tab==='audit'" class="v6-card v6-table-wrap"><table><thead><tr><th>时间</th><th>操作者</th><th>操作</th><th>目标</th></tr></thead><tbody><tr v-for="log in logs" :key="log.id"><td>{{ new Date(log.time*1000).toLocaleString() }}</td><td>{{ log.actor.slice(0,16) }}</td><td>{{ log.action }}<small v-if="log.detail?.model_override">已确认型号差异 · 强制下发</small></td><td>{{ log.target.slice(0,16) }}</td></tr></tbody></table></section>
      <footer class="v6-footer">RoomBeacon V6 · 配置自动同步 · Wi-Fi 与有线统一管理</footer>
    </template>
    <V6DevicePanel v-if="selected" :device="selected" :rooms="rooms" :editable="editable" :profiles="profiles" @close="selected=null" @changed="load" />
  </main>
</template>
