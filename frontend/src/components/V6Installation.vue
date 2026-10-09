<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import axios from 'axios'
import {management,type ManagedDevice} from '@/api/management'
import {installationBase as base,installationError,installState,installError,type InstallJob,type InstallOverview} from '@/api/installation'
import V6InstallAcceptance from './V6InstallAcceptance.vue'
import V6QuickInstall from './V6QuickInstall.vue'
import V6DeviceHealth from './V6DeviceHealth.vue'
const props=defineProps<{editable:boolean;devices:ManagedDevice[]}>()
const emit=defineEmits<{device:[string];changed:[]}>()
const abort=new AbortController(),data=ref<InstallOverview>({executors:[],releases:[],jobs:[]})
const busy=ref(false),loading=ref(false),error=ref(''),info=ref(''),credential=ref(''),executorName=ref('')
const manifestText=ref(''),releaseId=ref(''),executorId=ref(''),targetText=ref(''),preview=ref(false),requestId=ref('')
const associateJob=ref<InstallJob|null>(null),code=ref(''),identityChecked=ref(false),acceptJob=ref<InstallJob|null>(null)
const resolveJob=ref<{job:InstallJob;action:'retry'|'resolve'}|null>(null),stopped=ref(false)
let timer:ReturnType<typeof setInterval>|undefined
const validExecutors=computed(()=>data.value.executors.filter(e=>!e.revoked&&e.expires>Date.now()/1000))
const release=computed(()=>data.value.releases.find(r=>r.id===releaseId.value))
const targets=computed(()=>targetText.value.trim().split('\n').filter(Boolean).map(line=>{const [ip,serial,port='5555',...extra]=line.trim().split(/[\s,，]+/);return {ip,serial,port:Number(port),extra}}))
const targetsValid=computed(()=>targets.value.length>0&&targets.value.length<=100&&targets.value.every(t=>/^\d{1,3}(\.\d{1,3}){3}$/.test(t.ip)&&/^[A-Za-z0-9._-]{1,100}$/.test(t.serial||'')&&Number.isInteger(t.port)&&t.port>0&&t.port<=65535&&!t.extra.length))
const selectedAccept=computed(()=>data.value.jobs.find(j=>j.id===acceptJob.value?.id))
const acceptanceDevice=computed(()=>props.devices.find(d=>d.id===selectedAccept.value?.device_id))
const jobDevice=(id:string)=>props.devices.find(d=>d.id===id)
const releaseName=(id:string)=>{const r=data.value.releases.find(r=>r.id===id);return r?`${r.manifest.version_name} (${r.manifest.version_code})`:'版本未找到'}
async function load(){
 if(loading.value||abort.signal.aborted)return
 loading.value=true
 try{data.value=await management<InstallOverview>('GET',base,abort.signal)}catch(e){if(!axios.isCancel(e)){error.value=installationError(e);data.value.jobs.forEach(j=>j.device_ready=false)}}finally{loading.value=false}
}
async function act(fn:()=>Promise<unknown>){busy.value=true;error.value='';info.value='';try{await fn();info.value='操作已保存。';await load();emit('changed')}catch(e){if(!axios.isCancel(e))error.value=installationError(e)}finally{busy.value=false}}
async function registerExecutor(){await act(async()=>{const value=await management<{id:string;token:string}>('POST',base+'/executors',abort.signal,{name:executorName.value});credential.value=value.token;executorId.value=value.id;executorName.value=''})}
async function registerRelease(){let manifest;try{manifest=JSON.parse(manifestText.value)}catch{error.value='请粘贴助手生成的有效 JSON 清单';return}await act(async()=>{const value=await management<{id:string}>('POST',base+'/releases',abort.signal,manifest);releaseId.value=value.id;manifestText.value=''})}
function prepare(){preview.value=true;requestId.value=crypto.randomUUID()}
async function submit(){await act(async()=>{await management('POST',base+'/batches',abort.signal,{request_id:requestId.value,executor_id:executorId.value,release_id:releaseId.value,targets:targets.value.map(({ip,serial,port})=>({ip,serial,port}))});preview.value=false;targetText.value=''})}
async function associate(){if(!associateJob.value)return;const job=associateJob.value;await act(async()=>{await management('POST',`${base}/jobs/${job.id}/associate`,abort.signal,{revision:job.revision,code:code.value.replace(/\s/g,'').toUpperCase(),physical_identity_confirmed:identityChecked.value});associateJob.value=null})}
async function resolve(){if(!resolveJob.value)return;const {job,action}=resolveJob.value;await act(async()=>{await management('POST',`${base}/jobs/${job.id}/${action}`,abort.signal,{revision:job.revision,previous_executor_stopped:stopped.value});resolveJob.value=null})}
onMounted(()=>{load();timer=setInterval(()=>{if(!document.hidden)load()},10000)})
onUnmounted(()=>{abort.abort();clearInterval(timer);credential.value=''})
</script>
<template>
 <section class="v6-card installation"><div class="v6-toolbar"><div><h2>首装与交付</h2><p>输入联网设备的 IP，检测通过后确认初始化；安装完成后继续配置会议室。</p></div><button class="secondary" @click="load">刷新安装任务</button></div>
  <p v-if="error" class="v6-error" role="alert">{{error}}</p><p v-if="info" class="v6-info" role="status">{{info}}</p>
  <V6QuickInstall v-if="editable" @changed="load();emit('changed')" />
  <details v-if="editable" class="advanced"><summary>高级设置与现场助手</summary>
   <p>后台已能连接设备时，无需登记现场助手。</p>
   <p>以下是备用的现场电脑安装方式：仅在后台无法访问设备网络时使用。登记电脑后取得临时授权，再在现场电脑运行安装助手，由它领取任务并安装；仅登记不会执行安装。</p>
   <p>这里的 APK 清单供现场助手使用，不会设置后台直连使用的默认安装包。</p>
  <div class="install-grid">
   <details><summary>1. 登记现场助手</summary><form @submit.prevent="registerExecutor"><label>电脑名称<input v-model="executorName" required maxlength="80" placeholder="例如：交付电脑 1" /></label><button :disabled="busy">生成一天有效的助手凭证</button></form><div v-if="credential"><p>凭证仅展示一次，供现场助手隐藏输入。关闭页面后不再显示。</p><code class="credential">{{credential}}</code><button class="secondary" @click="credential=''">已保存，隐藏凭证</button></div>
    <p v-for="e in data.executors" :key="e.id">{{e.name}} · {{e.revoked?'已撤销':e.expires<Date.now()/1000?'已过期':'有效'}} <button v-if="!e.revoked" class="secondary" :disabled="busy" @click="act(()=>management('POST',`${base}/executors/${e.id}/revoke`,abort.signal,{}))">撤销 {{e.name}}</button></p><small>撤销会停止后续领取；已经启动的 ADB 操作须在现场核实。</small>
   </details>
   <details><summary>2. 登记已批准的正式 APK</summary><p>先用现场助手 inspect-apk 生成清单，再粘贴下方。APK 文件保存在现场电脑，安装前会复核签名、摘要与适用型号。</p><form @submit.prevent="registerRelease"><label>APK 清单 JSON<textarea v-model="manifestText" required rows="5" maxlength="10000" /></label><button :disabled="busy">登记正式 APK 清单</button></form></details>
  </div>
  <form v-if="editable" class="install-create" @submit.prevent="prepare"><h3>3. 创建首装批次</h3><div class="install-grid"><label>现场助手<select v-model="executorId" aria-label="现场助手" required :disabled="preview"><option value="" disabled>请选择</option><option v-for="e in validExecutors" :key="e.id" :value="e.id">{{e.name}}</option></select></label><label>正式 APK<select v-model="releaseId" aria-label="正式 APK" required :disabled="preview"><option value="" disabled>请选择</option><option v-for="r in data.releases" :key="r.id" :value="r.id">{{releaseName(r.id)}} · {{r.manifest.models.join(' / ')}} · {{r.manifest.sha256.slice(0,8)}}</option></select></label></div>
   <label>设备清单（每行 IP、序列号、可选 ADB 端口）<textarea v-model="targetText" :disabled="preview" rows="4" required maxlength="20000" placeholder="10.0.51.10 SERIAL001 5555" /></label><p>序列号按到货记录或厂家工具核对。仅支持内网 IPv4，每批最多 100 台。</p>
   <button v-if="!preview" :disabled="busy||!targetsValid||!executorId||!releaseId">检查安装范围</button>
   <div v-else class="install-preview"><h3>确认安装 {{targets.length}} 台</h3><p>助手：{{data.executors.find(e=>e.id===executorId)?.name}} · APK：{{releaseName(releaseId)}}</p><p class="hash">文件 SHA-256：{{release?.manifest.sha256}}<br />签名 SHA-256：{{release?.manifest.certificate_sha256}}</p><ul><li v-for="t in targets" :key="t.serial">{{t.ip}}:{{t.port}} · {{t.serial}}</li></ul><p>助手只对序列号和型号核对一致的设备执行首装。已有其他 APK 时停止，保留数据。</p><button type="button" :disabled="busy" @click="submit">确认创建安装任务</button><button type="button" class="secondary" :disabled="busy" @click="preview=false">返回修改</button></div>
  </form>
  </details>
  <section class="install-records"><h3>安装任务与交付记录</h3><p class="records-description">显示最近 1000 条；人工现场验收、配置回执和页面运行状态分别展示。</p>
  <div class="v6-table-wrap"><table><thead><tr><th>连接目标 / SN</th><th>APK / 助手</th><th>进度</th><th>设备 / 交付</th><th>操作</th></tr></thead><tbody><tr v-for="job in data.jobs" :key="job.id"><td>{{job.ip}}:{{job.port}}<small>{{job.serial}}</small></td><td>{{releaseName(job.release_id)}}<small>{{job.executor_id==='server'?'后台直接安装':data.executors.find(e=>e.id===job.executor_id)?.name}}</small></td><td>{{installState(job.state)}}<small v-if="job.error" class="v6-error">{{installError(job.error)}}</small></td><td>{{job.device_code||'等待关联短码'}}<small v-if="job.device_id">{{job.device_ready?'当前设备满足配置验收条件':'当前离线、未配置或待处理'}}</small><V6DeviceHealth v-if="job.device_id" :device="jobDevice(job.device_id)" compact /><small v-if="job.state==='accepted'">{{job.acceptance_current?'已保存此配置的现场验收':'配置或身份已变化，须重新验收'}}</small><small v-if="job.acceptance.location">{{job.acceptance.location}} · {{job.acceptance.switch_port}}</small></td><td>
   <button v-if="job.device_id" class="secondary" @click="emit('device',job.device_id)">{{editable?'房间配置':'查看配置'}}</button>
   <template v-if="editable"><button v-if="job.state==='queued'" class="secondary" :disabled="busy" @click="act(()=>management('POST',`${base}/jobs/${job.id}/cancel`,abort.signal,{revision:job.revision}))">取消排队</button>
    <button v-if="job.state==='installed'" class="secondary" :disabled="busy" @click="associateJob=job;code='';identityChecked=false">关联屏幕短码</button>
    <button v-if="['associated','accepted'].includes(job.state)" class="secondary" :disabled="busy" @click="acceptJob=job">现场验收</button>
    <button v-if="job.executor_id!=='server'&&['failed','uncertain'].includes(job.state)" class="secondary" :disabled="busy" @click="resolveJob={job,action:'retry'};stopped=false">核实后重试</button>
    <small v-if="job.executor_id==='server'&&job.state==='failed'">核实设备后，重新输入 IP 检测。</small>
    <button v-if="job.state==='uncertain'" class="secondary" :disabled="busy" @click="resolveJob={job,action:'resolve'};stopped=false">结束待核实任务</button>
   </template></td></tr></tbody></table></div><p v-if="!data.jobs.length" class="v6-empty">尚无首装任务</p></section>
 </section>
 <div v-if="associateJob" class="v6-backdrop"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="关联屏幕短码"><button class="secondary" :disabled="busy" @click="associateJob=null">关闭</button><h2>关联 {{associateJob.ip}} · {{associateJob.serial}}</h2><form @submit.prevent="associate"><label>屏幕六位短码<input v-model="code" required maxlength="8" /></label><label class="install-check"><input v-model="identityChecked" type="checkbox" />已核对这一台实物的序列号与屏幕短码</label><p v-if="error" class="v6-error" role="alert">{{error}}</p><button :disabled="busy||!identityChecked">确认设备关联</button></form></section></div>
 <div v-if="resolveJob" class="v6-backdrop"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="核实安装结果"><button class="secondary" :disabled="busy" @click="resolveJob=null">关闭</button><h2>{{resolveJob.action==='retry'?'核实后重试':'结束待核实任务'}}</h2><p>{{resolveJob.job.ip}} · {{resolveJob.job.serial}}</p><p>先检查现场 APK 与启动结果，确认原安装进程已停止。执行期限结束后才能操作；结束后可重新检测设备。</p><label class="install-check"><input v-model="stopped" type="checkbox" />我已核实现场结果并确认原安装进程已停止</label><p v-if="error" class="v6-error" role="alert">{{error}}</p><button :disabled="busy||!stopped" @click="resolve">确认{{resolveJob.action==='retry'?'重试':'结束'}}</button></section></div>
 <V6InstallAcceptance v-if="selectedAccept" :key="selectedAccept.id" :job="selectedAccept" :device="acceptanceDevice" @close="acceptJob=null" @changed="load();emit('changed')" />
</template>
<style scoped>
.installation{padding:24px;min-width:0}
.installation > .v6-toolbar{padding:0;align-items:flex-start;margin-bottom:28px;gap:16px}
.installation > .v6-toolbar > div{min-width:0;flex:1 1 400px}
.installation > .v6-toolbar > button{flex-shrink:0;white-space:nowrap}
.installation h2,.installation h3{margin:0 0 10px}
.installation p{line-height:1.7}
.installation > .v6-toolbar p,.records-description{color:#718096;font-size:14px}
.install-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:start}
.install-grid > *{min-width:0}
.installation label{display:grid;gap:8px;margin:14px 0}
.installation textarea{width:100%;resize:vertical;box-sizing:border-box;padding:10px;border:1px solid #ccd5e2;border-radius:8px}
.installation details,.install-create,.install-preview{border:1px solid #dce3ed;border-radius:10px;padding:16px;margin:12px 0;min-width:0}
.installation details{max-width:none;font-size:14px}
.installation details.advanced{margin:24px 0;background:#fafbfd}
.installation details details,.install-create{background:white}
.installation summary{cursor:pointer;font-weight:600;line-height:1.6}
.installation summary:focus-visible{outline:2px solid #3159d7;outline-offset:5px;border-radius:3px}
.installation details button{margin:4px 8px 4px 0}
.install-records{border-top:1px solid #e7ecf3;padding-top:24px;margin-top:28px;min-width:0}
.records-description{margin-bottom:16px}
.install-records .v6-table-wrap{border:1px solid #e7ecf3;border-radius:8px}
.installation .v6-empty{padding:40px 16px;margin:0}
.hash,.credential{overflow-wrap:anywhere}
.credential{display:block;padding:12px;background:#eef4fa}
.install-check{display:flex;gap:10px;margin:18px 0}
.install-check input{width:auto}
.installation small{display:block}
@media(max-width:800px){.install-grid{grid-template-columns:1fr;gap:12px}}
@media(max-width:600px){
 .installation{padding:18px}
 .installation > .v6-toolbar{margin-bottom:24px}
 .installation details,.install-create,.install-preview{padding:12px}
 .install-records{margin-top:24px;padding-top:20px}
}
</style>
