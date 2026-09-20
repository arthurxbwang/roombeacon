import axios from 'axios'

export interface UsagePolicy {
  owner: 'official' | 'v5'; release_delay_seconds: number
  mode: 'off' | 'observe' | 'auto'; early_minutes: number; grace_minutes: number
  native_policy_cleared: boolean; release_verified: boolean; revision: string
}
export interface UsageRecord {
  id: string; state: string; reason: string; deadline: string; verified: boolean
  occurrence: { uid: string; original_time: number; start_time: string; end_time: string }
  release_at?: string; challenge_id?: string
}
export interface UsageState {
  room_id: string; enabled: boolean; policy: UsagePolicy; paused: boolean
  server_time: string; valid_until: string; record: UsageRecord | null; can_confirm: boolean; can_end: boolean
  target_id: string | null
}
export const usageLabels: Record<string, string> = {
  pending: '请确认使用', confirmed: '已确认使用', observed: '已超时 · 仅记录',
  end_requested: '正在安排提前结束', releasing: '正在释放预约', released: '本次预约已释放',
  blocked: '自动释放已暂停', uncertain: '释放结果待核实', failed: '释放未成功',
  waiting: '尚未确认 · 即将释放', checking: '正在核验释放条件',
}
export function usageRequest<T>(method: string, path: string, token: string, signal: AbortSignal, data?: unknown) {
  return axios.request<{ data: T }>({ method, url: path, data, signal,
    headers: { Authorization: `Bearer ${token}` }, timeout: 10000 }).then(r => r.data.data)
}
export function usageError(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 503) return 'V5 功能尚未启用，预约展示不受影响'
    if (error.response?.status === 404) return '当前服务器尚未支持 V5，预约展示不受影响'
    if (error.response?.status === 401) return '操作凭证已失效，请重新绑定'
    if (error.response?.status === 409) return '预约或规则已变化，请刷新后核对'
  }
  return '操作结果待核实，请等待重新同步'
}
