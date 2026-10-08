<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import axios from 'axios'
import {management,type ManagedDevice} from '@/api/management'
import {installationBase as base,installationError,installState,installError,type InstallJob,type InstallOverview} from '@/api/installation'
import V6InstallAcceptance from './V6InstallAcceptance.vue'
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
 <section class="v6-card installation"><div class="v6-toolbar"><div><h2>首装与交付</h2><p>联网后登记 IP 与实物序列号，由现场助手安装；关联屏幕短码后继续房间配置与验收。</p></div><button class="secondary" @click="load">刷新安装任务</button></div>
  <p v-if="error" class="v6-error" role="alert">{{error}}</p><p v-if="info" class="v6-info" role="status">{{info}}</p>
  <div v-if="editable" class="install-grid">
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
  <h3>安装任务与交付记录</h3><p>显示最近 1000 条；现场验收为人工记录，当前在线与配置回执单独展示。</p>
  <div class="v6-table-wrap"><table><thead><tr><th>连接目标 / SN</th><th>APK / 助手</th><th>进度</th><th>设备 / 交付</th><th>操作</th></tr></thead><tbody><tr v-for="job in data.jobs" :key="job.id"><td>{{job.ip}}:{{job.port}}<small>{{job.serial}}</small></td><td>{{releaseName(job.release_id)}}<small>{{data.executors.find(e=>e.id===job.executor_id)?.name}}</small></td><td>{{installState(job.state)}}<small v-if="job.error" class="v6-error">{{installError(job.error)}}</small></td><td>{{job.device_code||'等待关联短码'}}<small v-if="job.device_id">{{job.device_ready?'当前在线且配置已应用':'当前离线、未配置或待处理'}}</small><small v-if="job.state==='accepted'">{{job.acceptance_current?'已保存此配置的现场验收':'配置或身份已变化，须重新验收'}}</small><small v-if="job.acceptance.location">{{job.acceptance.location}} · {{job.acceptance.switch_port}}</small></td><td>
   <button v-if="job.device_id" class="secondary" @click="emit('device',job.device_id)">{{editable?'房间配置':'查看配置'}}</button>
   <template v-if="editable"><button v-if="job.state==='queued'" class="secondary" :disabled="busy" @click="act(()=>management('POST',`${base}/jobs/${job.id}/cancel`,abort.signal,{revision:job.revision}))">取消排队</button>
    <button v-if="job.state==='installed'" class="secondary" :disabled="busy" @click="associateJob=job;code='';identityChecked=false">关联屏幕短码</button>
    <button v-if="['associated','accepted'].includes(job.state)" class="secondary" :disabled="busy" @click="acceptJob=job">现场验收</button>
    <button v-if="['failed','uncertain'].includes(job.state)" class="secondary" :disabled="busy" @click="resolveJob={job,action:'retry'};stopped=false">核实后重试</button>
    <button v-if="job.state==='uncertain'" class="secondary" :disabled="busy" @click="resolveJob={job,action:'resolve'};stopped=false">结束待核实任务</button>
   </template></td></tr></tbody></table></div><p v-if="!data.jobs.length" class="v6-empty">尚无首装任务</p>
 </section>
 <div v-if="associateJob" class="v6-backdrop"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="关联屏幕短码"><button class="secondary" :disabled="busy" @click="associateJob=null">关闭</button><h2>关联 {{associateJob.ip}} · {{associateJob.serial}}</h2><form @submit.prevent="associate"><label>屏幕六位短码<input v-model="code" required maxlength="8" /></label><label class="install-check"><input v-model="identityChecked" type="checkbox" />已核对这一台实物的序列号与屏幕短码</label><p v-if="error" class="v6-error" role="alert">{{error}}</p><button :disabled="busy||!identityChecked">确认设备关联</button></form></section></div>
 <div v-if="resolveJob" class="v6-backdrop"><section class="v6-panel" role="dialog" aria-modal="true" aria-label="核实安装结果"><button class="secondary" :disabled="busy" @click="resolveJob=null">关闭</button><h2>{{resolveJob.action==='retry'?'核实后重试':'结束待核实任务'}}</h2><p>{{resolveJob.job.ip}} · {{resolveJob.job.serial}}</p><p>先检查现场 APK 与启动结果，并停止旧助手进程。执行期限结束后才能操作；结束任务不会卸载已经安装的 APK。</p><label class="install-check"><input v-model="stopped" type="checkbox" />我已核实现场结果并停止旧助手</label><p v-if="error" class="v6-error" role="alert">{{error}}</p><button :disabled="busy||!stopped" @click="resolve">确认{{resolveJob.action==='retry'?'重试':'结束'}}</button></section></div>
 <V6InstallAcceptance v-if="selectedAccept" :key="selectedAccept.id" :job="selectedAccept" :device="acceptanceDevice" @close="acceptJob=null" @changed="load();emit('changed')" />
</template>
<style scoped>
.installation h2,.installation h3{margin:12px 0}.install-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.installation label{display:grid;gap:8px;margin:14px 0}.installation textarea{width:100%;resize:vertical;box-sizing:border-box;padding:10px;border:1px solid #ccd5e2;border-radius:8px}.installation details,.install-create,.install-preview{border:1px solid #dce3ed;border-radius:10px;padding:16px;margin:12px 0}.installation summary{cursor:pointer;font-weight:600}.installation button{margin:4px}.hash,.credential{overflow-wrap:anywhere}.credential{display:block;padding:12px;background:#eef4fa}.install-check{display:flex;gap:10px;margin:18px 0}.install-check input{width:auto}.installation small{display:block}@media(max-width:800px){.install-grid{grid-template-columns:1fr}}
</style>
