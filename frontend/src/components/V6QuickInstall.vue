<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import axios from 'axios'
import {installationBase as base,installationError,type ApkManifest} from '@/api/installation'
import {management} from '@/api/management'
interface ServerStatus {probe_ready:boolean;blocker:string;port:number;apk_configured:boolean}
interface Probe {id:string;ip:string;port:number;serial:string;model:string;android:string;existing:boolean;manifest:ApkManifest|null;can_initialize:boolean;blocker:string;expires:number}
const emit=defineEmits<{changed:[]}>()
const abort=new AbortController(),ip=ref(''),busy=ref(''),error=ref(''),info=ref('')
const server=ref<ServerStatus|null>(null),probe=ref<Probe|null>(null),now=ref(Date.now()/1000)
const expired=computed(()=>!!probe.value&&probe.value.expires<=now.value)
let timer:ReturnType<typeof setInterval>|undefined
watch(ip,()=>{probe.value=null;error.value='';info.value=''})
async function load(){
 try{server.value=await management<ServerStatus>('GET',base+'/server',abort.signal)}catch(e){if(!axios.isCancel(e))error.value=installationError(e)}
}
async function detect(){
 busy.value='probe';error.value='';info.value='';probe.value=null
 try{
  await load()
  if(!server.value?.probe_ready){error.value=server.value?.blocker||'无法读取后台安装设置，请稍后重试';return}
  const response=await axios.post<{data:Probe}>(base+'/probe',{ip:ip.value.trim(),port:server.value.port},{signal:abort.signal,timeout:120000})
  probe.value=response.data.data;now.value=Date.now()/1000
 }catch(e){if(!axios.isCancel(e))error.value=installationError(e)}finally{busy.value=''}
}
async function initialize(){
 if(!probe.value||expired.value)return
 busy.value='initialize';error.value=''
 try{
  await management('POST',base+'/initialize',abort.signal,{probe_id:probe.value.id,confirmed:true})
  info.value='初始化任务已提交。请在下方查看进度；完成后核对屏幕短码，再配置会议室。'
  probe.value=null;emit('changed')
 }catch(e){if(!axios.isCancel(e))error.value=installationError(e)}finally{busy.value=''}
}
onMounted(()=>{load();timer=setInterval(()=>{now.value=Date.now()/1000},1000)})
onUnmounted(()=>{abort.abort();clearInterval(timer)})
</script>
<template>
 <section class="quick-install" aria-label="设备初始化">
  <ol class="steps"><li>输入设备 IP</li><li>检测设备</li><li>确认初始化</li></ol>
  <form @submit.prevent="detect"><label for="install-ip">设备 IP</label><div class="ip-row"><input id="install-ip" v-model="ip" required maxlength="15" inputmode="decimal" autocomplete="off" placeholder="例如：10.0.51.221" :disabled="!!busy" /><button :disabled="!!busy||!ip.trim()">{{busy==='probe'?'正在检测…':'检测设备'}}</button></div></form>
  <p class="hint">设备联网并开启网络 ADB 后，输入 IP 即可检测。</p>
  <p v-if="server&&!server.probe_ready" class="v6-info" role="status">{{server.blocker}} <button class="secondary" @click="load">重新检查设置</button></p>
  <p v-if="server?.probe_ready&&!server.apk_configured" class="v6-error" role="alert">后台尚未准备默认安装包，设备检测仍可使用。无需登记现场助手，请联系后台维护人员准备安装包。</p>
  <p v-if="error" class="v6-error" role="alert">{{error}}</p>
  <p v-if="info" class="v6-info" role="status">{{info}}</p>
  <div v-if="probe" class="result">
   <h3>已连接到设备</h3><dl><dt>IP 地址</dt><dd>{{probe.ip}}:{{probe.port}}</dd><dt>设备型号</dt><dd>{{probe.model}}</dd><dt>序列号</dt><dd>{{probe.serial}}</dd><dt>Android 版本</dt><dd>{{probe.android||'未提供'}}</dd><dt v-if="probe.manifest">安装版本</dt><dd v-if="probe.manifest">{{probe.manifest.version_name}}</dd></dl>
   <p v-if="probe.blocker" :class="probe.existing?'v6-info':'v6-error'" role="status">{{probe.blocker}}</p>
   <template v-if="probe.can_initialize"><p>确认后将安装并启动门牌应用。请核对上方设备信息。</p><p v-if="expired" role="status" class="v6-error">检测结果已过期，请重新检测设备。</p><button :disabled="!!busy||expired" @click="initialize">{{busy==='initialize'?'正在提交…':'确认初始化'}}</button></template>
  </div>
 </section>
</template>
<style scoped>
.quick-install{max-width:760px;min-width:0;margin:0}
.steps{display:flex;flex-wrap:wrap;gap:16px 28px;list-style:none;padding:0;margin:0 0 24px;color:#536173;counter-reset:step}
.steps li{display:flex;align-items:center;gap:8px;font-size:14px;counter-increment:step}
.steps li::before{content:counter(step);display:grid;place-items:center;width:24px;height:24px;flex-shrink:0;border-radius:50%;background:#edf2ff;color:#3159d7;font-size:12px;font-weight:600}
.ip-row{display:flex;align-items:center;gap:12px;margin-top:10px}
.ip-row input{flex:1;min-width:0;padding:12px;border:1px solid #ccd5e2;border-radius:8px;height:44px;box-sizing:border-box}
.ip-row button{height:44px;white-space:nowrap}
.hint{color:#68778b;font-size:13px;line-height:1.7;margin:10px 0 0}
.result{margin-top:20px;padding:20px;background:#f6f8fc;border:1px solid #dce3ed;border-radius:12px}
.result h3{margin:0 0 16px}
.result dl{display:grid;grid-template-columns:110px 1fr;gap:10px;font-size:14px}
.result dt{color:#68778b}
.result dd{margin:0;overflow-wrap:anywhere}
.result p{line-height:1.7;margin-top:16px}
.quick-install button{flex-shrink:0}
@media(max-width:600px){
 .steps{gap:12px 18px}
 .steps li{font-size:12px;gap:6px}
 .steps li::before{width:20px;height:20px}
 .ip-row{align-items:stretch;flex-direction:column;gap:10px}
 .ip-row input{flex:auto}
 .ip-row button{align-self:flex-start}
 .result{padding:16px}
 .result dl{grid-template-columns:90px minmax(0,1fr)}
}
</style>
