<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import axios from 'axios'
import {management,type ManagedDevice} from '@/api/management'
import {installationBase,installationError,type InstallJob} from '@/api/installation'
import V6DeviceHealth from './V6DeviceHealth.vue'
const props=defineProps<{job:InstallJob;device?:ManagedDevice}>()
const emit=defineEmits<{close:[];changed:[]}>()
const abort=new AbortController(),busy=ref(false),error=ref(''),location=ref(''),port=ref('')
const checks=ref<string[]>([])
const items=[{id:'screen_and_fresh_data',label:'房间、方向和画面正确，业务数据新鲜'},
 {id:'lighting',label:'灯色与实际状态一致（无灯型号已核对不适用）'},
 {id:'cold_boot',label:'首次断电上电后，APK 自动启动且身份与配置保持'},
 {id:'adb_closed',label:'已手动关闭网络 ADB，并从现场电脑验证无法连接'},
 {id:'poe_recovery_adb_stays_closed',label:'关闭 ADB 后再次 PoE 真断电，页面、灯控恢复且 ADB 仍关闭'}]
const canSave=computed(()=>props.job.device_ready&&props.device?.reported_revision===props.device?.revision&&checks.value.length===items.length&&location.value.trim()&&port.value.trim())
watch(()=>[props.job.revision,props.device?.revision],()=>{checks.value=[];error.value='配置或验收记录已变化，请重新逐项核验。'})
async function save(){
 if(!canSave.value||!props.device)return
 busy.value=true;error.value=''
 try{await management('POST',`${installationBase}/jobs/${props.job.id}/accept`,abort.signal,{revision:props.job.revision,device_revision:props.device.revision,location:location.value.trim(),switch_port:port.value.trim(),...Object.fromEntries(checks.value.map(c=>[c,true]))});emit('changed');emit('close')}
 catch(e){if(!axios.isCancel(e))error.value=installationError(e)}finally{busy.value=false}
}
onUnmounted(()=>abort.abort())
</script>
<template>
 <div class="v6-backdrop" @click.self="!busy&&emit('close')"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="现场交付验收">
  <button class="secondary" :disabled="busy" @click="emit('close')">关闭</button><h2>现场交付验收 · {{job.device_code}}</h2>
  <p>逐项完成实物核验后勾选。这份记录由验收人员确认；安装成功和管理心跳不能代替现场检查。</p>
  <V6DeviceHealth :device="device" />
  <p v-if="!job.device_ready" class="v6-error">设备须在线、已分配房间、配置回执一致且无错误；已上报页面状态的设备还须页面正常且业务数据有效。</p>
  <form @submit.prevent="save"><label class="install-field">安装位置<input v-model="location" required maxlength="160" /></label><label class="install-field">交换机与物理端口<input v-model="port" required maxlength="160" placeholder="现场已核对的交换机名称 / 端口" /></label>
   <label v-for="item in items" :key="item.id" class="install-check"><input v-model="checks" type="checkbox" :value="item.id" />{{item.label}}</label>
   <p v-if="error" class="v6-error" role="alert">{{error}}</p><button :disabled="busy||!canSave">保存现场验收记录</button>
  </form>
 </section></div>
</template>
<style scoped>
.install-field{display:grid;gap:8px;margin:16px 0}.install-check{display:flex;align-items:flex-start;gap:10px;margin:18px 0}.install-check input{width:auto;flex:none;margin-top:4px}
</style>
