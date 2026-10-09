<script setup lang="ts">
import {onUnmounted,ref} from 'vue'
import {management,managementError,type ManagedDevice} from '@/api/management'
const props=defineProps<{device:ManagedDevice;roomName:string}>()
const emit=defineEmits<{close:[];deleted:[]}>()
const abort=new AbortController(),busy=ref(false),error=ref('')
async function remove(){
 if(busy.value)return
 busy.value=true;error.value=''
 try{
  await management('DELETE',`/api/v6/admin/devices/${props.device.id}`,abort.signal,
   {expected_revision:props.device.revision,confirm_code:props.device.code})
  emit('deleted')
 }catch(e){if(!abort.signal.aborted)error.value=managementError(e)}finally{busy.value=false}
}
onUnmounted(()=>abort.abort())
</script>
<template>
 <div class="v6-backdrop" @click.self="!busy&&emit('close')"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="确认删除设备">
  <header><h2>确认删除设备？</h2><button class="secondary" :disabled="busy" @click="emit('close')">取消</button></header>
  <p>设备：<strong>{{device.code.slice(0,3)}} {{device.code.slice(3)}}</strong></p><p>会议室：{{roomName}}</p>
  <p>删除后设备将从台账移除，旧凭证立即失效。若它是会议室主控，需要重新选择主控设备。配置与操作历史保留。</p>
  <p v-if="device.online" class="v6-error">该设备当前在线，删除后将停止读取会议室数据。</p>
  <p v-if="error" class="v6-error" role="alert">{{error}}</p>
  <div class="v6-actions"><button class="secondary" :disabled="busy" @click="emit('close')">保留设备</button><button class="v6-danger" :disabled="busy" @click="remove">{{busy?'正在删除…':'确认删除'}}</button></div>
 </section></div>
</template>
