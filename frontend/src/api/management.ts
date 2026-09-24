import axios from 'axios'
export interface DeviceConfig { version: 'v4'|'v5'|'v6'; portrait: boolean; room_light: boolean; node_id: 'central'; reload: number; theme_mode: 'auto'|'light'; language: 'zh-CN'|'en'; device_profile: string }
export interface ConfigTemplate {id:string;name:string;revision:number;config:DeviceConfig}
export interface ManagedDevice {
  id: string; code: string; status: string; room_id: string; revision: number; reported_revision: number
  online: boolean; last_seen: number; error: string; config: DeviceConfig
  metadata: { model?: string; firmware?: string; config_schema?: number; serial?: string; apk?: string; android?: string; network?: string; light_supported?: boolean
    screen?:{pixel_width?:number;pixel_height?:number;viewport_width?:number;viewport_height?:number;dpr?:number}
    interfaces?: { name: string; mac: string; addresses: string[] }[] }
}
export interface Manager { subject: string; name: string; role: 'admin'|'viewer'; csrf: string }
export interface Room { room_id: string; name: string; region: string; location: string; region_id?:string; location_nodes?:{id:string;name:string}[] }
export const defaultConfig: DeviceConfig = { version: 'v6', portrait: false, room_light: true, node_id: 'central', reload: 0, theme_mode: 'auto', language: 'zh-CN', device_profile: 'auto' }
export async function management<T>(method: string, url: string, signal: AbortSignal, data?: unknown, headers?: Record<string,string>) {
  const response = await axios.request<{data:T}>({method,url,signal,data,headers,timeout:15000})
  return response.data.data
}
export function managementError(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) return '登录已失效，请重新登录'
    if (error.response?.status === 403) return '当前账号尚未授权或没有此操作权限'
    if (error.response?.status === 409) return '配置已变化，请刷新后重新操作'
    if (error.response?.status === 429) return '操作过于频繁，请稍后重试'
    if (error.response?.status === 422) return typeof error.response.data?.message === 'string' ? error.response.data.message : '请检查会议室与配置内容'
  }
  return '服务暂不可用，请稍后重试'
}
export const networkLabel = (value?: string) => ({wifi:'Wi-Fi',ethernet:'有线 / PoE',offline:'无网络',other:'其他网络'}[value || ''] || '未知')
export const statusLabel = (value: string) => ({pending:'待激活',active:'已激活',revoked:'已撤销'}[value] || value)

export interface DeviceProfile { id: string; name: string; model: string; firmware: string; pins: {red:number;green:number;blue:number}|null; active_level: number|null }
export function profileMismatch(config: DeviceConfig, device: ManagedDevice, profiles: DeviceProfile[]) {
  if (['auto','generic'].includes(config.device_profile)) return ''
  const profile = profiles.find(p=>p.id===config.device_profile)
  return profile && profile.model===device.metadata.model ? '' : '型号不同，二次确认后可强制下发'
}
export function profileNotice(config: DeviceConfig) {
  return ['auto','generic'].includes(config.device_profile) ? '通用／旧配置，不限定设备型号' : '型号相同，可正常下发'
}
export function profileCapabilityNotice(config: DeviceConfig, device: ManagedDevice) {
  return config.room_light && !['auto','generic'].includes(config.device_profile) && (device.metadata.config_schema || 1)<2
    ? '可下发配置；模板灯控需升级 APK 0.6.2 后生效' : ''
}
// Confirmation is scoped to this publish request, never saved into a template.
export function confirmModelOverride(config: DeviceConfig, devices: ManagedDevice[], profiles: DeviceProfile[], action='下发模板') {
  const mismatches=devices.filter(d=>profileMismatch(config,d,profiles))
  if(!mismatches.length)return false
  const profile=profiles.find(p=>p.id===config.device_profile)
  const targets=mismatches.slice(0,10).map(d=>`${d.code}：${d.metadata.model || '未上报型号'}`).join('\n')
  return window.confirm(`${action}：${profile?.name || config.device_profile}（${profile?.model || '未指定'}）\n${mismatches.length} 台设备型号不同：\n${targets}${mismatches.length>10?'\n…其余 '+(mismatches.length-10)+' 台':''}\n将按模板应用显示与灯控配置，显示比例或灯色可能不同。确认强制下发？`) ? true : null
}
