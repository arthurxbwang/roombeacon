<script setup lang="ts">
import {computed,ref} from 'vue'
import {type Room,type ManagedDevice} from '@/api/management'
import {stateLabel,templateName,type CatalogTemplate,type Configuration} from '@/api/configuration'
import {emptyScope,matchesScope,roomMatches} from '@/composables/roomScope'
import V6RoomFilter from './V6RoomFilter.vue'
const props=defineProps<{rooms:Room[];devices:ManagedDevice[];catalog:CatalogTemplate[];configuration:Configuration;focus?:string}>()
const emit=defineEmits<{device:[id:string];preview:[id:string];qualification:[room:Room]}>()
const scope=ref(emptyScope()),query=ref(''),software=ref(''),hardware=ref(''),status=ref('')
const roomDevices=(id:string)=>props.devices.filter(d=>d.room_id===id&&d.status!=='revoked')
const result=(id:string)=>props.configuration.deployments.find(d=>d.id===props.configuration.devices[id]?.deployment_id)
const rows=computed(()=>props.rooms.filter(r=>matchesScope(r,scope.value)&&roomMatches(r,query.value)&&(!props.focus||r.room_id===props.focus)&&
 (!software.value||props.configuration.rooms[r.room_id]?.software_id===software.value)&&
 (!hardware.value||roomDevices(r.room_id).some(d=>props.configuration.devices[d.id]?.hardware_id===hardware.value))&&
 (!status.value||(status.value==='unassigned'?!roomDevices(r.room_id).length:status.value==='offline'?roomDevices(r.room_id).some(d=>!d.online):roomDevices(r.room_id).some(d=>result(d.id)?.state!=='applied')))))
</script>
<template>
 <section class="v6-card"><div class="v6-toolbar"><input v-model="query" aria-label="搜索会议室" placeholder="搜索名称或位置" /><select v-model="software" aria-label="按软件模板筛选"><option value="">全部软件模板</option><option v-for="t in catalog.filter(t=>t.kind==='software')" :key="t.id" :value="t.id">{{t.name}}</option></select><select v-model="hardware" aria-label="按硬件模板筛选"><option value="">全部硬件模板</option><option v-for="t in catalog.filter(t=>t.kind==='hardware')" :key="t.id" :value="t.id">{{t.name}}</option></select><select v-model="status" aria-label="会议室部署状态"><option value="">全部部署状态</option><option value="unassigned">未部署设备</option><option value="offline">有离线设备</option><option value="pending">配置待复核</option></select></div>
  <V6RoomFilter :rooms="rooms" v-model="scope" /><p class="v6-list-count">{{rows.length}} / {{rooms.length}} 间会议室</p>
  <div class="v6-table-wrap"><table><thead><tr><th>会议室 / 完整位置</th><th>软件模板</th><th>对应硬件设备与安装模板</th><th>房间规则</th><th>操作</th></tr></thead><tbody><tr v-for="r in rows" :key="r.room_id"><td><strong>{{r.name}}</strong><small>{{r.location||r.region}}</small></td><td>{{templateName(catalog,configuration.rooms[r.room_id]?.software_id,configuration.rooms[r.room_id]?.software_version)}}</td><td><div v-for="d in roomDevices(r.room_id)" :key="d.id" class="v6-room-device"><button class="secondary" @click="emit('device',d.id)">{{d.code}}</button> {{d.metadata.model}} · {{d.online?'在线':'离线'}}<small>{{templateName(catalog,configuration.devices[d.id]?.hardware_id,configuration.devices[d.id]?.hardware_version)}}</small><small>{{result(d.id)?stateLabel(result(d.id)!.state):'历史配置待关联'}}{{configuration.rooms[r.room_id]?.controller_id===d.id?' · 业务主控':''}}</small></div><span v-if="!roomDevices(r.room_id).length" class="v6-muted">尚未部署设备</span></td><td><template v-if="configuration.rooms[r.room_id]">{{configuration.rooms[r.room_id].rules.owner==='v5'?'RoomBeacon 签到':'官方签到'}}<small>{{stateLabel(configuration.rooms[r.room_id].policy_state)}}</small><small v-if="configuration.rooms[r.room_id].error" class="v6-error">{{configuration.rooms[r.room_id].error}}</small></template><span v-else>现有房间规则</span></td><td><button class="secondary" @click="emit('preview',r.room_id)">查看门牌</button><button class="secondary" @click="emit('qualification',r)">规则与房间核验</button></td></tr></tbody></table></div>
  <p v-if="!rows.length" class="v6-empty">没有匹配的会议室，请调整筛选条件。</p>
 </section>
</template>
