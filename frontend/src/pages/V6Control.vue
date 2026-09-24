<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import axios from 'axios'
import V6RoomFilter from '@/components/V6RoomFilter.vue'
import V6Catalog from '@/components/V6Catalog.vue'
import V6BatchDeployment from '@/components/V6BatchDeployment.vue'
import V6DeploymentPanel from '@/components/V6DeploymentPanel.vue'
import V6RoomsTable from '@/components/V6RoomsTable.vue'
import V6Audit,{type AuditEntry} from '@/components/V6Audit.vue'
import RoomUsageControl from '@/components/RoomUsageControl.vue'
import {emptyScope,matchesScope,normalized} from '@/composables/roomScope'
import {emptyConfiguration,stateLabel,templateName,type CatalogTemplate,type Configuration} from '@/api/configuration'
import {management,managementError,networkLabel,statusLabel,type ManagedDevice,type Manager,type Room} from '@/api/management'
import RoomDisplay from './RoomDisplay.vue'
import './v6Control.css'
const abort=new AbortController()
const user=ref<Manager|null>(null),error=ref(''),info=ref(''),busy=ref(false),checking=ref(true)
const awaitingPermission=ref(false),usageRoom=ref<Room|null>(null)
const devices=ref<ManagedDevice[]>([]),rooms=ref<Room[]>([]),selectedId=ref('')
const selected=computed(()=>devices.value.find(d=>d.id===selectedId.value))
const search=ref(''),filter=ref('all'),tab=ref('devices'),feishu=ref(false),preview=ref(''),roomFocus=ref('')
const users=ref<{subject:string;name:string;role:string}[]>([]),logs=ref<AuditEntry[]>([])
const catalog=ref<CatalogTemplate[]>([]),configuration=ref<Configuration>(emptyConfiguration())
const scope=ref(emptyScope()),checked=ref<string[]>([])
const batchDevices=computed(()=>devices.value.filter(d=>checked.value.includes(d.id)))
const editable=computed(()=>user.value?.role==='admin')
const pending=computed(()=>devices.value.filter(d=>d.status==='pending').length)
const online=computed(()=>devices.value.filter(d=>d.online&&d.status==='active').length)
const filtered=computed(()=>devices.value.filter(d=>{
 const r=rooms.value.find(r=>r.room_id===d.room_id)
 const i=configuration.value.devices[d.id],c=configuration.value.rooms[d.room_id]
 return (filter.value==='all'||d.status===filter.value)&&matchesScope(r,scope.value)&&normalized(`${d.code} ${d.metadata.serial||''} ${d.metadata.model||''} ${d.metadata.interfaces?.map(i=>i.mac).join(' ')||''} ${r?.name||''} ${r?.region||''} ${r?.location||''} ${templateName(catalog.value,i?.hardware_id,i?.hardware_version)} ${templateName(catalog.value,c?.software_id,c?.software_version)}`).includes(normalized(search.value))
}))
watch(filtered,()=>{checked.value=checked.value.filter(id=>filtered.value.some(d=>d.id===id&&d.status==='active'))})
const roomName=(id:string)=>{const r=rooms.value.find(r=>r.room_id===id);return r?`${r.region} · ${r.name}`:'未分配'}
const deployment=(id:string)=>configuration.value.deployments.find(d=>d.id===configuration.value.devices[id]?.deployment_id)
let timer:ReturnType<typeof setInterval>|undefined,loading=false
async function load(){
 if(!user.value||loading||abort.signal.aborted)return
 loading=true
 try{
  const [list,directory,templates,assignments]=await Promise.all([
   management<ManagedDevice[]>('GET','/api/v6/admin/devices',abort.signal),
   management<Room[]>('GET','/api/room-control/rooms',abort.signal),
   management<CatalogTemplate[]>('GET','/api/v6/admin/catalog',abort.signal),
   management<Configuration>('GET','/api/v6/admin/configuration',abort.signal)])
  devices.value=list;rooms.value=directory;catalog.value=templates;configuration.value=assignments
  if(tab.value==='users'&&editable.value)users.value=await management('GET','/api/v6/auth/users',abort.signal)
  if(tab.value==='audit')logs.value=await management('GET','/api/v6/admin/audit',abort.signal)
 }catch(e){if(!axios.isCancel(e))error.value=managementError(e)}finally{loading=false}
}
async function identify(){
 awaitingPermission.value=false
 try{user.value=await management<Manager>('GET','/api/v6/auth/me',abort.signal);axios.defaults.headers.common['X-RB-CSRF']=user.value.csrf;await load()}
 catch(e){if(axios.isAxiosError(e)&&e.response?.status===403){awaitingPermission.value=true;error.value='飞书身份已识别，等待管理员授予管理员或只读权限。授权后请重新登录。'}}
 finally{checking.value=false}
}
async function logout(){try{await management('POST','/api/v6/auth/logout',abort.signal,{}, {'X-RB-Logout':'1'});user.value=null;awaitingPermission.value=false;devices.value=[];selectedId.value='';preview.value='';error.value='';delete axios.defaults.headers.common['X-RB-CSRF']}catch(e){error.value=managementError(e)}}
async function operate(action:()=>Promise<unknown>){busy.value=true;error.value='';info.value='';try{await action();info.value='操作已保存。';await load()}catch(e){error.value=managementError(e)}finally{busy.value=false}}
async function switchTab(value:string){tab.value=value;roomFocus.value='';await load()}
function inspectRoom(id:string){roomFocus.value=id;tab.value='rooms'}
onMounted(async()=>{
 if(new URLSearchParams(location.search).has('login_error'))error.value='飞书登录未完成，请重试；首次登录请确认员工在应用与通讯录可用范围内。'
 try{feishu.value=(await management<{feishu:boolean}>('GET','/api/v6/auth/options',abort.signal)).feishu}catch{error.value='V6 管理服务暂不可用'}
 await identify();timer=setInterval(()=>{if(!document.hidden)load()},15000)
})
onUnmounted(()=>{abort.abort();clearInterval(timer);delete axios.defaults.headers.common['X-RB-CSRF']})
</script>
<template>
 <div v-if="preview&&user" class="v6-preview"><nav><button @click="preview=''">返回 V6 后台</button><span>会议室预览 · {{roomName(preview)}}</span></nav><RoomDisplay :key="preview" :control-room="preview" control-token="@session" display-version="v6" /></div>
 <main v-else class="v6-control">
  <header class="v6-top"><a class="v6-brand" href="/control"><span class="v6-logo">B</span><div>RoomBeacon <b>V6</b><small>会议灯塔 · 集中管理</small></div></a><div v-if="user" class="v6-account"><span>{{user.name}} · {{editable?'管理员':'只读'}}</span><button class="secondary" @click="logout">退出登录</button></div></header>
  <section v-if="!user" class="v6-login"><p class="v6-eyebrow">ROOMBEACON CONTROL</p><h1>飞书登录会议灯塔</h1><p class="v6-muted">使用企业飞书账号，统一管理会议门牌。</p><p v-if="checking">正在检查登录状态…</p><template v-else><a v-if="feishu" class="v6-primary-link" href="/api/v6/auth/feishu/start">飞书扫码 / 快捷登录</a><p v-else class="v6-muted">飞书登录暂不可用，请联系管理员。</p><p v-if="feishu" class="v6-muted v6-login-hint">在飞书授权页扫码，或使用已登录的飞书账号快捷进入。</p><button v-if="awaitingPermission" class="v6-text" @click="logout">退出登录</button></template><p class="v6-error" role="alert">{{error}}</p></section>
  <template v-else>
   <section class="v6-heading"><div><p class="v6-eyebrow">中央管理 · 主服务器</p><h1>设备与部署</h1><p class="v6-muted">选择硬件安装模板、软件模板与会议室，检查后部署。</p></div><button class="secondary" @click="load">刷新状态</button></section>
   <section class="v6-stats"><article><span>设备总数</span><strong>{{devices.length}}</strong></article><article><span>待激活</span><strong>{{pending}}</strong></article><article><span>在线运行</span><strong>{{online}}</strong></article><article><span>会议室</span><strong>{{rooms.length}}</strong></article></section>
   <nav class="v6-tabs"><button v-for="t in [{id:'devices',label:'设备台账'},{id:'rooms',label:'会议室'},{id:'software',label:'软件模板'},{id:'hardware',label:'硬件安装模板'},...(editable?[{id:'users',label:'账号权限'}]:[]),{id:'audit',label:'操作记录'}]" :key="t.id" :class="{active:tab===t.id}" @click="switchTab(t.id)">{{t.label}}</button></nav>
   <p v-if="error" class="v6-error" role="alert">{{error}}</p><p v-if="info" class="v6-info" role="status">{{info}}</p>
   <section v-if="tab==='devices'" class="v6-card"><div class="v6-toolbar"><input v-model="search" aria-label="搜索设备" placeholder="搜索设备、型号、地区、会议室或模板" /><select v-model="filter" aria-label="设备状态"><option value="all">全部设备</option><option value="pending">待激活</option><option value="active">已激活</option><option value="revoked">已撤销</option></select></div><V6RoomFilter :rooms="rooms" v-model="scope" unassigned />
    <div class="v6-table-wrap"><table><thead><tr><th v-if="editable">选择</th><th>设备 / 型号</th><th>硬件安装模板</th><th>软件模板</th><th>会议室</th><th>状态 / 网络</th><th>部署回执</th><th>操作</th></tr></thead><tbody><tr v-for="d in filtered" :key="d.id"><td v-if="editable"><input v-model="checked" type="checkbox" :value="d.id" :disabled="d.status!=='active'" :aria-label="'选择 '+d.code" /></td><td><strong class="v6-code">{{d.code.slice(0,3)}} {{d.code.slice(3)}}</strong><small>{{d.metadata.model||'型号未上报'}} · SN {{d.metadata.serial||'未上报'}}</small><small v-for="nic in d.metadata.interfaces?.filter(n=>n.mac)" :key="nic.name">{{nic.name}} {{nic.mac}}</small></td><td>{{templateName(catalog,configuration.devices[d.id]?.hardware_id,configuration.devices[d.id]?.hardware_version)}}</td><td>{{templateName(catalog,configuration.rooms[d.room_id]?.software_id,configuration.rooms[d.room_id]?.software_version)}}</td><td>{{roomName(d.room_id)}}<small>{{rooms.find(r=>r.room_id===d.room_id)?.location}}</small></td><td><span class="v6-badge" :class="{online:d.online}">{{statusLabel(d.status)}} · {{d.online?'在线':'离线'}}</span><small>{{networkLabel(d.metadata.network)}}</small></td><td><span :class="{'v6-error':!!d.error}">{{deployment(d.id)?stateLabel(deployment(d.id)!.state):d.error?'应用异常':d.reported_revision===d.revision?'当前配置已应用 · 待关联模板':'等待设备应用'}}</span><small>{{d.reported_revision}} / {{d.revision}}</small></td><td><button class="secondary" @click="selectedId=d.id">{{editable?'配置与部署':'查看'}}</button></td></tr></tbody></table></div>
    <V6BatchDeployment v-if="editable&&checked.length" :devices="batchDevices" :catalog="catalog" :configuration="configuration" @changed="checked=[];load()" /><div v-if="!filtered.length" class="v6-empty"><h3>{{devices.length?'没有匹配的设备':'等待设备连接'}}</h3><p>{{devices.length?'请调整地区、位置或搜索条件。':'门牌联网后会自动出现在这里，使用屏幕上的唯一码核对设备。'}}</p></div>
   </section>
   <template v-if="tab==='rooms'"><button v-if="roomFocus" class="secondary" @click="roomFocus=''">查看全部会议室</button><V6RoomsTable :rooms="rooms" :devices="devices" :catalog="catalog" :configuration="configuration" :focus="roomFocus" @device="selectedId=$event" @preview="preview=$event" @qualification="usageRoom=$event" /></template>
   <V6Catalog v-show="tab==='software'" kind="software" :catalog="catalog" :devices="devices" :rooms="rooms" :editable="editable" @changed="load" @device="selectedId=$event" @room="inspectRoom" />
   <V6Catalog v-show="tab==='hardware'" kind="hardware" :catalog="catalog" :devices="devices" :rooms="rooms" :editable="editable" @changed="load" @device="selectedId=$event" @room="inspectRoom" />
   <section v-if="tab==='users'&&editable" class="v6-card v6-table-wrap"><table><thead><tr><th>飞书用户</th><th>权限</th><th>操作</th></tr></thead><tbody><tr v-for="u in users" :key="u.subject"><td>{{u.name}}<small>{{u.subject.slice(0,12)}}</small></td><td>{{{admin:'管理员',viewer:'只读',pending:'待授权',disabled:'已停用'}[u.role]||u.role}}</td><td><button v-for="role in ['admin','viewer','disabled']" :key="role" class="secondary" :disabled="busy||u.subject===user.subject||u.role===role" @click="operate(()=>management('PUT','/api/v6/auth/users/'+u.subject,abort.signal,{role}))">{{{admin:'授予管理员',viewer:'设为只读',disabled:'停用'}[role]}}</button></td></tr></tbody></table><p v-if="!users.length" class="v6-empty">用户首次飞书登录后，会出现在待授权列表。</p></section>
   <V6Audit v-if="tab==='audit'" :logs="logs" />
   <footer class="v6-footer">RoomBeacon · 模板版本与部署结果可追溯</footer>
  </template>
  <div v-if="usageRoom" class="v6-backdrop" @click.self="usageRoom=null"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="会议室规则"><button class="secondary" @click="usageRoom=null">关闭</button><RoomUsageControl :key="usageRoom.room_id" :room-id="usageRoom.room_id" :room-name="usageRoom.name" token="@session" :read-only="!editable" :template-managed="!!configuration.rooms[usageRoom.room_id]" /></section></div>
  <V6DeploymentPanel v-if="selected" :device="selected" :rooms="rooms" :catalog="catalog" :configuration="configuration" :initial-scope="scope" :editable="editable" @close="selectedId=''" @changed="load" />
 </main>
</template>
