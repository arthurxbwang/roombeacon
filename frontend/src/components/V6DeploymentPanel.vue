<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {management,managementError,type ManagedDevice,type Room} from '@/api/management'
import {stateLabel,templateName,type CatalogTemplate,type Configuration,type Deployment,type HardwareSpec} from '@/api/configuration'
import {emptyScope,matchesScope,roomMatches,type RoomScope} from '@/composables/roomScope'
import V6RoomFilter from './V6RoomFilter.vue'
import {configurationChanges} from '@/utils/configurationText'
const props=defineProps<{device:ManagedDevice;rooms:Room[];catalog:CatalogTemplate[];configuration:Configuration;initialScope:RoomScope;editable:boolean}>()
const emit=defineEmits<{close:[];changed:[]}>()
const abort=new AbortController(),busy=ref(false),error=ref(''),info=ref('')
const scope=ref(emptyScope()),search=ref(''),room=ref(''),hardwareId=ref(''),softwareId=ref(''),hardwareVersion=ref(1),softwareVersion=ref(1)
const replaceRoom=ref(false),confirmed=ref(false),controller=ref(true),revision=ref(0)
const preview=ref<{room:{name:string};software:string;devices:{code:string;hardware:string;before:Record<string,unknown>;after:Record<string,unknown>}[]}|null>(null)
const previewBody=ref<Record<string,unknown>|null>(null)
const hardware=computed(()=>props.catalog.filter(t=>t.kind==='hardware'&&!t.archived&&t.published_version))
const software=computed(()=>props.catalog.filter(t=>t.kind==='software'&&!t.archived&&t.published_version))
const chosenHardware=computed(()=>hardware.value.find(t=>t.id===hardwareId.value))
const chosenSoftware=computed(()=>software.value.find(t=>t.id===softwareId.value))
const hardwareSpec=computed(()=>chosenHardware.value?.versions.find(v=>v.version===hardwareVersion.value)?.spec as HardwareSpec|undefined)
const roomConfig=computed(()=>props.configuration.rooms[room.value])
const installation=computed(()=>props.configuration.devices[props.device.id])
const history=computed(()=>props.configuration.deployments.filter(d=>d.device_id===props.device.id))
const filteredRooms=computed(()=>props.rooms.filter(r=>matchesScope(r,scope.value)&&roomMatches(r,search.value)))
const conflict=computed(()=>roomConfig.value&&(roomConfig.value.software_id!==softwareId.value||roomConfig.value.software_version!==softwareVersion.value))
function reset(){const i=props.configuration.devices[props.device.id],r=props.configuration.rooms[props.device.room_id];revision.value=props.device.revision;room.value=props.device.room_id;hardwareId.value=i?.hardware_id||'';hardwareVersion.value=i?.hardware_version||1;softwareId.value=r?.software_id||'';softwareVersion.value=r?.software_version||1;controller.value=!r||r.controller_id===props.device.id;scope.value=props.initialScope.region==='@unassigned'?emptyScope():JSON.parse(JSON.stringify(props.initialScope));replaceRoom.value=false;confirmed.value=false;preview.value=null;previewBody.value=null}
watch(()=>props.device.id,reset,{immediate:true})
watch([room,hardwareId,softwareId,hardwareVersion,softwareVersion,replaceRoom,confirmed,controller],()=>{preview.value=null;previewBody.value=null})
watch(filteredRooms,()=>{if(room.value&&!filteredRooms.value.some(r=>r.room_id===room.value))room.value=''})
function chooseHardware(){hardwareVersion.value=chosenHardware.value?.published_version||1;confirmed.value=false}
function chooseSoftware(){softwareVersion.value=chosenSoftware.value?.published_version||1}
function useRoom(){if(roomConfig.value){softwareId.value=roomConfig.value.software_id;softwareVersion.value=roomConfig.value.software_version;replaceRoom.value=false}}
function payload(){return {device_id:props.device.id,expected_revision:revision.value,room_id:room.value,hardware_id:hardwareId.value,hardware_version:hardwareVersion.value,software_id:softwareId.value,software_version:softwareVersion.value,expected_room_revision:roomConfig.value?.revision||0,replace_room_software:replaceRoom.value,confirm_model_mismatch:confirmed.value,control_device:controller.value}}
async function run(action:()=>Promise<unknown>){if(busy.value)return;busy.value=true;error.value='';try{await action()}catch(e){error.value=managementError(e)}finally{busy.value=false}}
function check(){run(async()=>{const body=payload();preview.value=await management('POST','/api/v6/admin/deployments/preview',abort.signal,body);previewBody.value=body})}
function deploy(){if(!previewBody.value)return;run(async()=>{await management('POST','/api/v6/admin/deployments',abort.signal,previewBody.value);emit('changed');emit('close')})}
function adopt(){run(async()=>{await management('POST',`/api/v6/admin/devices/${props.device.id}/adopt`,abort.signal,{expected_revision:revision.value});emit('changed');emit('close')})}
function reload(){run(async()=>{await management('POST',`/api/v6/admin/devices/${props.device.id}/reload`,abort.signal,{expected_revision:revision.value});emit('changed');emit('close')})}
function changeStatus(status:'pending'|'revoked'){if(!window.confirm(status==='revoked'?'撤销后设备将停止读取会议室数据，确认撤销？':'暂停部署后设备将回到等待配置页面，确认暂停？'))return;run(async()=>{await management('POST',`/api/v6/admin/devices/${props.device.id}/status`,abort.signal,{expected_revision:revision.value,status});emit('changed');emit('close')})}
function restore(d:Deployment){hardwareId.value=d.hardware_id;hardwareVersion.value=d.hardware_version;softwareId.value=d.software_id;softwareVersion.value=d.software_version;room.value=d.room_id;scope.value=emptyScope();search.value='';info.value='已选择历史版本组合，请核对会议室影响范围并重新检查部署。'}
onUnmounted(()=>abort.abort())
</script>
<template>
 <div class="v6-backdrop" @click.self="emit('close')"><section class="v6-panel v6-deployment-panel" role="dialog" aria-modal="true" aria-label="设备部署">
  <header><div><p class="v6-eyebrow">设备配置与部署</p><h2>{{device.code}}</h2></div><button class="secondary" @click="emit('close')">关闭</button></header>
  <dl class="v6-facts"><div><dt>型号 / 固件</dt><dd>{{device.metadata.model||'未上报'}}<small>{{device.metadata.firmware}}</small></dd></div><div><dt>APK / 网络状态</dt><dd>{{device.metadata.apk||'未上报'}} · {{device.online?'在线':'离线'}}</dd></div><div><dt>当前硬件模板</dt><dd>{{templateName(catalog,installation?.hardware_id,installation?.hardware_version)}}</dd></div><div><dt>当前软件模板</dt><dd>{{templateName(catalog,configuration.rooms[device.room_id]?.software_id,configuration.rooms[device.room_id]?.software_version)}}</dd></div></dl>
  <p class="v6-muted">网页视口：{{device.metadata.screen?.viewport_width?`${device.metadata.screen.viewport_width} × ${device.metadata.screen.viewport_height}，DPR ${device.metadata.screen.dpr}`:'设备尚未上报'}}</p><p v-if="!installation" class="v6-muted">历史配置尚未关联模板。转换将按当前参数建立模板，不改变设备运行配置。</p><button v-if="!installation&&device.status==='active'&&editable" class="secondary" :disabled="busy" @click="adopt">转换当前配置为模板</button>
  <p v-if="device.error" class="v6-error">设备回执：{{device.error}}</p><p v-if="error" class="v6-error" role="alert">{{error}}</p><p v-if="info" class="v6-info">{{info}}</p>
  <form @submit.prevent="check"><fieldset :disabled="!editable||busy">
   <h3>1 · 选择硬件安装模板</h3><label>硬件安装模板<select aria-label="硬件安装模板" v-model="hardwareId" required @change="chooseHardware"><option value="">请选择已发布硬件模板</option><option v-for="t in hardware" :key="t.id" :value="t.id">{{t.name}}</option></select></label><label v-if="chosenHardware">硬件版本<select aria-label="硬件版本" v-model.number="hardwareVersion"><option v-for="v in chosenHardware.versions" :key="v.version" :value="v.version">v{{v.version}} · {{v.name}}</option></select></label>
   <p v-if="hardwareSpec" class="v6-muted">{{hardwareSpec.portrait?'竖屏':'横屏'}} · {{hardwareSpec.width?`${hardwareSpec.width} × ${hardwareSpec.height}`:'面板尺寸未记录'}} · {{hardwareSpec.room_light?`GPIO 红 ${hardwareSpec.pins.red} / 绿 ${hardwareSpec.pins.green} / 蓝 ${hardwareSpec.pins.blue}，${hardwareSpec.active_level?'高':'低'}电平点亮`:'无灯控'}}</p>
   <label v-if="hardwareSpec?.model&&hardwareSpec.model!==device.metadata.model" class="v6-check"><input v-model="confirmed" type="checkbox" />已核对设备型号差异，确认使用此安装配置</label>
   <h3>2 · 选择软件模板</h3><label>软件模板<select aria-label="软件模板" v-model="softwareId" required @change="chooseSoftware"><option value="">请选择已发布软件模板</option><option v-for="t in software" :key="t.id" :value="t.id">{{t.name}}</option></select></label><label v-if="chosenSoftware">软件版本<select aria-label="软件版本" v-model.number="softwareVersion"><option v-for="v in chosenSoftware.versions" :key="v.version" :value="v.version">v{{v.version}} · {{v.name}}</option></select></label>
   <p v-if="!software.length" class="v6-muted">请先在“软件模板”中新建并发布版本。</p>
   <h3>3 · 选择会议室</h3><V6RoomFilter :rooms="rooms" v-model="scope" /><label>会议室关键词<input v-model="search" placeholder="名称或位置" /></label><label>分配会议室<select aria-label="分配会议室" v-model="room" required><option value="">请选择会议室</option><option v-for="r in filteredRooms" :key="r.room_id" :value="r.room_id">{{r.name}} · {{r.location}}</option></select></label><p class="v6-muted">当前筛选 {{filteredRooms.length}} 间会议室。</p>
   <div v-if="conflict" class="v6-wiring"><p>房间当前使用 {{templateName(catalog,roomConfig?.software_id,roomConfig?.software_version)}}。</p><button type="button" class="secondary" @click="useRoom">沿用该会议室软件模板</button><label class="v6-check"><input v-model="replaceRoom" type="checkbox" />更换该会议室软件模板，并更新其所有已关联设备</label></div>
   <label class="v6-check"><input v-model="controller" type="checkbox" />作为该会议室业务主控设备（其他设备仅展示）</label>
   <h3>4 · 检查并部署</h3><button :disabled="busy||!hardwareId||!softwareId||!room">检查兼容性与变更范围</button>
  </fieldset></form>
  <section v-if="preview" class="v6-deployment-review"><h3>即将部署到 {{preview.room.name}}</h3><p>软件：{{preview.software}}</p><article v-for="d in preview.devices" :key="d.code"><strong>设备 {{d.code}} · {{d.hardware}}</strong><p v-for="change in configurationChanges(d.before,d.after)" :key="change">{{change}}</p><p v-if="!configurationChanges(d.before,d.after).length">设备参数保持当前值，更新模板关联和部署记录。</p></article><p class="v6-muted">共影响 {{preview.devices.length}} 台设备；离线设备保持等待，实际回执后才显示生效。</p><button v-if="editable" :disabled="busy" @click="deploy">确认部署</button></section>
  <div class="v6-actions"><button v-if="editable" class="secondary" :disabled="busy" @click="reload">远程刷新</button><button class="secondary" @click="reset">重置编辑</button><button v-if="editable&&device.status==='active'" class="secondary" :disabled="busy" @click="changeStatus('pending')">暂停部署</button><button v-if="editable&&device.status!=='revoked'" class="secondary" :disabled="busy" @click="changeStatus('revoked')">撤销设备</button></div>
  <section class="v6-catalog-detail"><h3>部署历史与回退</h3><article v-for="d in history" :key="d.id" class="v6-template-item"><strong>{{stateLabel(d.state)}} · {{new Date(d.created_at*1000).toLocaleString()}}</strong><p>{{d.value.hardware_name}} v{{d.hardware_version}} / {{d.value.software_name}} v{{d.software_version}}</p><p>{{d.value.room_name}} · {{d.value.location}}</p><p v-if="d.error" class="v6-error">{{d.error}}</p><button v-if="editable" class="secondary" @click="restore(d)">选择此版本组合回退</button></article><p v-if="!history.length" class="v6-muted">还没有新的模板部署记录。</p></section>
 </section></div>
</template>
