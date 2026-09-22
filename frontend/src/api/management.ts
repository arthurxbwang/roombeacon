import axios from 'axios'
export interface DeviceConfig { version: 'v4'|'v5'|'v6'; portrait: boolean; room_light: boolean; node_id: 'central'; reload: number }
export interface ManagedDevice {
  id: string; code: string; status: string; room_id: string; revision: number; reported_revision: number
  online: boolean; last_seen: number; error: string; config: DeviceConfig
  metadata: { model?: string; serial?: string; apk?: string; android?: string; network?: string; light_supported?: boolean
    interfaces?: { name: string; mac: string; addresses: string[] }[] }
}
export interface Manager { subject: string; name: string; role: 'admin'|'viewer'; csrf: string }
export interface Room { room_id: string; name: string; region: string; location: string }
export const defaultConfig: DeviceConfig = { version: 'v6', portrait: false, room_light: true, node_id: 'central', reload: 0 }
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
    if (error.response?.status === 422) return '请检查会议室与配置内容'
  }
  return '服务暂不可用，请稍后重试'
}
export const networkLabel = (value?: string) => ({wifi:'Wi-Fi',ethernet:'有线 / PoE',offline:'无网络',other:'其他网络'}[value || ''] || '未知')
export const statusLabel = (value: string) => ({pending:'待激活',active:'已激活',revoked:'已撤销'}[value] || value)
