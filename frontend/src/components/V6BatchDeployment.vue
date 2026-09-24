<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {management,managementError,type ManagedDevice} from '@/api/management'
import type {CatalogTemplate,Configuration} from '@/api/configuration'
const props=defineProps<{devices:ManagedDevice[];catalog:CatalogTemplate[];configuration:Configuration}>()
const emit=defineEmits<{changed:[]}>()
const hardwareId=ref(''),softwareId=ref(''),replace=ref(false),confirmed=ref(false),busy=ref(false),error=ref('')
const hardwareVersion=ref(1),softwareVersion=ref(1)
const hardware=computed(()=>props.catalog.filter(t=>t.kind==='hardware'&&!t.archived&&t.published_version))
const software=computed(()=>props.catalog.filter(t=>t.kind==='software'&&!t.archived&&t.published_version))
const selectedHardware=computed(()=>hardware.value.find(t=>t.id===hardwareId.value)),selectedSoftware=computed(()=>software.value.find(t=>t.id===softwareId.value))
const review=ref<{devices:{code:string;room_name:string;hardware:string}[]}|null>(null),body=ref<Record<string,unknown>|null>(null)
const abort=new AbortController()
watch([hardwareId,softwareId,hardwareVersion,softwareVersion,replace,confirmed,()=>props.devices.map(d=>d.id).join(',')],()=>{review.value=null;body.value=null})
async function run(publish=false){if(busy.value)return;busy.value=true;error.value='';try{
 if(publish){await management('POST','/api/v6/admin/deployment-batches',abort.signal,body.value);emit('changed')}
 else {const data={devices:Object.fromEntries(props.devices.map(d=>[d.id,d.revision])),room_revisions:Object.fromEntries(props.devices.map(d=>[d.room_id,props.configuration.rooms[d.room_id]?.revision||0])),hardware_id:hardwareId.value,hardware_version:hardwareVersion.value,software_id:softwareId.value,software_version:softwareVersion.value,replace_room_software:replace.value,confirm_model_mismatch:confirmed.value};review.value=await management('POST','/api/v6/admin/deployment-batches/preview',abort.signal,data);body.value=data}
 }catch(e){error.value=managementError(e)}finally{busy.value=false}}
onUnmounted(()=>abort.abort())
</script>
<template><section class="v6-batch"><strong>已选 {{devices.length}} 台设备</strong><p class="v6-muted">保留各设备当前会议室，统一应用下列模板。最多 100 台。</p><div class="v6-form-row"><label>批量硬件模板<select v-model="hardwareId" aria-label="批量硬件模板" @change="hardwareVersion=selectedHardware?.published_version||1"><option value="">选择硬件模板</option><option v-for="t in hardware" :key="t.id" :value="t.id">{{t.name}}</option></select></label><label>硬件版本<select v-model.number="hardwareVersion" aria-label="批量硬件版本"><option v-for="v in selectedHardware?.versions||[]" :key="v.version" :value="v.version">v{{v.version}}</option></select></label><label>批量软件模板<select v-model="softwareId" aria-label="批量软件模板" @change="softwareVersion=selectedSoftware?.published_version||1"><option value="">选择软件模板</option><option v-for="t in software" :key="t.id" :value="t.id">{{t.name}}</option></select></label><label>软件版本<select v-model.number="softwareVersion" aria-label="批量软件版本"><option v-for="v in selectedSoftware?.versions||[]" :key="v.version" :value="v.version">v{{v.version}}</option></select></label></div><label class="v6-check"><input v-model="replace" type="checkbox" />允许更换会议室的软件模板，并更新同房间的其他关联设备</label><label class="v6-check"><input v-model="confirmed" type="checkbox" />已核对不同型号的设备，确认按所选硬件配置部署</label><button :disabled="busy||!hardwareId||!softwareId||devices.length>100" @click="run()">检查批量部署</button><p v-if="error" role="alert" class="v6-error">{{error}}</p><div v-if="review" class="v6-deployment-review"><h3>实际影响 {{review.devices.length}} 台设备</h3><p v-for="d in review.devices" :key="d.code">{{d.code}} · {{d.room_name}} · {{d.hardware}}</p><button :disabled="busy" @click="run(true)">确认批量部署</button></div></section></template>
