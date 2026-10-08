import type {ManagedDevice,PageHealth} from '@/api/management'

const pageLabels:Record<PageHealth['state'],string>={
 unknown:'未上报页面状态，请升级 APK',offline:'设备离线，页面状态未确认',stale:'页面回执已过期',
 waiting:'等待配置',loading:'页面加载中',ready:'页面运行正常',failed:'页面运行异常',paused:'页面已暂停'
}
const errors:Record<PageHealth['error'],string>={
 '':'',network:'网页连接失败',http:'网页请求失败',tls:'网页安全连接失败',renderer:'网页渲染进程异常',
 timeout:'网页加载超时',unresponsive:'网页响应超时',initialization:'网页初始化失败',blocked:'网页访问被阻止'
}
export function deviceHealth(device?:ManagedDevice){
 const health=device?.page_health
 const state=device&&!device.online?'offline':health?.state||'unknown'
 const page=state==='ready'&&health?.terminal_state==='unknown'?'页面已加载 · 数据待确认':pageLabels[state]||pageLabels.unknown
 const light=state==='offline'?'灯控状态未确认':state==='stale'?'灯控回执已过期':
  ({disabled:'灯控未启用',unknown:'灯控状态未确认',ok:'灯控正常',failed:'灯控异常'}[health?.light_state||'unknown'])
 const age=health?.age_seconds
 return {page,light,error:state==='failed'?errors[health?.error||'']:'',
  pageProblem:['failed','offline','stale'].includes(state),lightProblem:state==='stale'||state==='offline'||health?.light_state==='failed',
  age:typeof age==='number'&&Number.isFinite(age)&&age>=0?`${Math.floor(age)} 秒前`:'未上报',
  release:health?.page_release||'未上报',webview:health?.webview||'未上报'}
}
