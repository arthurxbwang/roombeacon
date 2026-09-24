<script setup lang="ts">
import {computed,onUnmounted,ref} from 'vue'
import {management,managementError,type ManagedDevice,type Room} from '@/api/management'
import {hardwareDefaults,softwareDefaults,type CatalogTemplate,type HardwareSpec,type SoftwareSpec} from '@/api/configuration'
import HardwareTemplateFields from './HardwareTemplateFields.vue'
import SoftwareTemplateFields from './SoftwareTemplateFields.vue'
import RoomDisplay from '@/pages/RoomDisplay.vue'
const props=defineProps<{kind:'hardware'|'software';catalog:CatalogTemplate[];devices:ManagedDevice[];rooms:Room[];editable:boolean}>()
const emit=defineEmits<{changed:[];device:[id:string];room:[id:string]}>()
const label=computed(()=>props.kind==='hardware'?'硬件安装模板':'软件模板')
const items=computed(()=>props.catalog.filter(t=>t.kind===props.kind&&(!t.archived||showArchived.value)))
const showArchived=ref(false),query=ref(''),identity=ref(''),revision=ref(0),name=ref(''),editing=ref(false)
const hardware=ref(hardwareDefaults()),software=ref(softwareDefaults()),error=ref(''),info=ref(''),busy=ref(false),detail=ref('')
const selected=computed(()=>props.catalog.find(t=>t.id===detail.value))
const visible=computed(()=>items.value.filter(t=>`${t.name} ${JSON.stringify(t.spec)}`.toLowerCase().includes(query.value.toLowerCase())))
const testDevice=ref(''),testVersion=ref(1),testResult=ref('passed'),testNotes=ref(''),colors=ref(false),off=ref(false),orientation=ref(false)
const previewRoom=ref(''),previewTheme=ref('light'),previewing=ref(false)
const abort=new AbortController()
function draftChanged(t:CatalogTemplate){const v=t.versions[0];return !!v&&(t.name!==v.name||JSON.stringify(t.spec)!==JSON.stringify(v.spec))}
function edit(t?:CatalogTemplate,copy=false){
 identity.value=copy?'':t?.id||'';revision.value=copy?0:t?.revision||0;name.value=t?`${t.name}${copy?' · 副本':''}`:''
 hardware.value=JSON.parse(JSON.stringify(t?.kind==='hardware'?t.spec:hardwareDefaults()))
 software.value=JSON.parse(JSON.stringify(t?.kind==='software'?t.spec:softwareDefaults()))
 editing.value=true;error.value='';info.value='';previewing.value=false
}
async function run(action:()=>Promise<unknown>,message:string){if(busy.value)return;busy.value=true;error.value='';info.value='';try{await action();info.value=message;emit('changed')}catch(e){error.value=managementError(e)}finally{busy.value=false}}
async function save(){await run(async()=>{const row=await management<CatalogTemplate>(identity.value?'PUT':'POST','/api/v6/admin/catalog'+(identity.value?'/'+identity.value:''),abort.signal,{kind:props.kind,name:name.value,spec:props.kind==='hardware'?hardware.value:software.value,expected_revision:revision.value});identity.value=row.id;revision.value=row.revision;editing.value=false;detail.value=row.id},'草稿已保存。发布版本后可在设备台账选择部署。')}
function publish(t:CatalogTemplate){run(()=>management('POST',`/api/v6/admin/catalog/${t.id}/publish`,abort.signal,{expected_revision:t.revision}),'模板版本已发布，现有设备保持原版本。请在设备台账选择部署。')}
function archive(t:CatalogTemplate){if(window.confirm(`归档“${t.name}”？历史版本与记录会保留。`))run(()=>management('POST',`/api/v6/admin/catalog/${t.id}/archive`,abort.signal,{expected_revision:t.revision}),'模板已归档。')}
function inspect(t:CatalogTemplate){detail.value=t.id;testVersion.value=t.published_version||1;testDevice.value='';testNotes.value='';colors.value=false;off.value=false;orientation.value=false}
function record(){if(!selected.value)return;run(()=>management('POST',`/api/v6/admin/catalog/${selected.value!.id}/tests`,abort.signal,{version:testVersion.value,device_id:testDevice.value,result:testResult.value,notes:testNotes.value,colors:colors.value,off:off.value,orientation:orientation.value}),'测试记录已保存并关联到该版本。')}
onUnmounted(()=>abort.abort())
</script>
<template>
 <section class="v6-card v6-presets">
  <div class="v6-template-heading"><div><h2>{{label}}</h2><p class="v6-muted">{{kind==='hardware'?'管理型号、安装方向、接线及实测记录。':'管理页面样式、背景、语言和会议室业务规则。'}} 草稿 → 发布版本 → 选择设备部署。</p></div><button v-if="editable" @click="edit()">新建{{label}}</button></div>
  <p v-if="error" class="v6-error" role="alert">{{error}}</p><p v-if="info" class="v6-info" role="status">{{info}}</p>
  <div class="v6-toolbar"><input v-model="query" :aria-label="`搜索${label}`" placeholder="搜索名称、型号或参数" /><label class="v6-check"><input v-model="showArchived" type="checkbox" />包含已归档</label></div>
  <form v-if="editing" class="v6-template-editor" @submit.prevent="save"><h3>{{identity?'编辑草稿':'新建模板'}}</h3><fieldset :disabled="busy"><label>模板名称<input v-model="name" required maxlength="80" /></label><HardwareTemplateFields v-if="kind==='hardware'" v-model="hardware" /><SoftwareTemplateFields v-else v-model="software" /><div class="v6-actions"><button>保存草稿</button><button type="button" class="secondary" @click="editing=false">取消编辑</button></div></fieldset>
   <div v-if="kind==='software'" class="v6-preview-controls"><label>预览会议室<select aria-label="预览会议室" v-model="previewRoom"><option value="">选择真实会议室预览</option><option v-for="r in rooms" :key="r.room_id" :value="r.room_id">{{r.region}} · {{r.name}}</option></select></label><label>预览日夜<select aria-label="预览日夜" v-model="previewTheme"><option value="light">白天</option><option value="dark">夜间</option></select></label><button type="button" class="secondary" :disabled="!previewRoom" @click="previewing=!previewing">{{previewing?'收起预览':'预览当前草稿'}}</button><p class="v6-muted">预览读取缓存日程，操作按钮不可用；不保存房间规则。</p></div>
  </form>
  <div v-if="previewing&&editing" class="v6-template-live-preview"><RoomDisplay :key="previewRoom" :control-room="previewRoom" control-token="@session" :control-theme="previewTheme" :display-version="software.rules.owner==='v5'?'v5':'v4'" :template-preferences="software" /></div>
  <div class="v6-template-grid"><article v-for="t in visible" :key="t.id" class="v6-template-item"><h3>{{t.name}}</h3><p v-if="draftChanged(t)&&!t.archived" class="v6-info">草稿有修改，尚未发布</p><p>{{t.archived?'已归档':t.published_version?`已发布 v${t.published_version}`:'草稿 · 尚未发布'}}</p><p v-if="kind==='hardware'">{{(t.spec as HardwareSpec).model||'通用屏幕'}} · {{(t.spec as HardwareSpec).portrait?'竖屏':'横屏'}} · {{(t.spec as HardwareSpec).room_light?'有灯控':'无灯控'}}</p><p v-else>{{(t.spec as SoftwareSpec).language==='en'?'English':'中文'}} · {{(t.spec as SoftwareSpec).rules.owner==='v5'?'RoomBeacon 签到':'官方签到'}} · {{(t.spec as SoftwareSpec).theme_mode==='auto'?'自动日夜':(t.spec as SoftwareSpec).theme_mode==='light'?'固定白天':'固定夜间'}}</p><p>{{kind==='hardware'?`${t.devices.length} 台设备`:`${t.rooms.length} 间会议室`}}正在使用</p><div class="v6-actions"><button class="secondary" @click="inspect(t)">版本与使用范围</button><template v-if="editable"><button v-if="!t.archived" class="secondary" @click="edit(t)">编辑</button><button class="secondary" @click="edit(t,true)">复制</button><button v-if="!t.archived" :disabled="busy" @click="publish(t)">发布版本</button><button v-if="!t.archived" class="secondary" :disabled="busy" @click="archive(t)">归档</button></template></div></article></div>
  <p v-if="!visible.length" class="v6-empty">尚无匹配模板。{{editable?'点击上方按钮新建。':''}}</p>
  <section v-if="selected" class="v6-catalog-detail"><div class="v6-template-heading"><h3>{{selected.name}} · 版本与使用范围</h3><button class="secondary" @click="detail=''">收起详情</button></div>
   <table><thead><tr><th>发布版本</th><th>名称</th><th>发布时间</th></tr></thead><tbody><tr v-for="v in selected.versions" :key="v.version"><td>v{{v.version}}</td><td>{{v.name}}</td><td>{{new Date(v.created_at*1000).toLocaleString()}}</td></tr></tbody></table>
   <div v-if="kind==='hardware'"><h3>关联设备</h3><p v-for="d in selected.devices" :key="d.id"><button class="secondary" @click="emit('device',d.id)">{{d.code}} · v{{d.version}}</button> {{rooms.find(r=>r.room_id===d.room_id)?.name||'未分配'}}</p><p v-if="!selected.devices.length" class="v6-muted">暂无设备使用。</p><h3>版本测试记录</h3><p v-if="selected.source==='verified-profile'" class="v6-muted">初始接线来自已有样机校准资料；其他设备与固件需独立核验。</p><p v-for="t in selected.tests" :key="t.id">v{{t.version}} · {{t.value.device_code}} · {{t.value.result==='passed'?'通过':'失败'}} · {{t.value.notes}}</p><p v-if="!selected.tests.length" class="v6-muted">尚未登记本模板的设备测试记录。</p>
    <form v-if="editable&&selected.published_version&&!selected.archived" @submit.prevent="record"><h3>登记实测结果</h3><label>测试版本<select aria-label="测试版本" v-model.number="testVersion"><option v-for="v in selected.versions" :key="v.version" :value="v.version">v{{v.version}}</option></select></label><label>实际测试设备<select aria-label="实际测试设备" v-model="testDevice" required><option value="">请选择</option><option v-for="d in devices" :key="d.id" :value="d.id">{{d.code}} · {{d.metadata.model}}</option></select></label><label>测试结果<select aria-label="测试结果" v-model="testResult"><option value="passed">通过</option><option value="failed">失败</option></select></label><label class="v6-check"><input v-model="colors" type="checkbox" />灯色／无灯控核验</label><label class="v6-check"><input v-model="off" type="checkbox" />全灭／无灯控核验</label><label class="v6-check"><input v-model="orientation" type="checkbox" />安装方向与显示核验</label><label>测试说明<textarea v-model="testNotes" required minlength="5" maxlength="2000" /></label><button :disabled="busy">保存测试记录</button></form>
   </div><div v-else><h3>应用会议室</h3><p v-for="r in selected.rooms" :key="r.room_id"><button class="secondary" @click="emit('room',r.room_id)">{{r.room_name}} · v{{r.version}}</button> {{r.location}}</p><p v-if="!selected.rooms.length" class="v6-muted">暂无会议室使用。</p></div>
  </section>
 </section>
</template>
