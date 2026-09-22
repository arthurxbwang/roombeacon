import axios from 'axios'
interface ApiEnvelope<T> { code?: number; message?: string; data?: T }

export interface MeetingRoom { room_id: string; name: string; capacity: number; enabled: boolean }
export interface RoomEvent {
  uid: string; original_time: number; start_time: string; end_time: string
  organizer: string | null; summary: string | null
}
export interface RoomSchedule {
  display_preferences?: {theme_mode:'auto'|'light';language:'zh-CN'|'en'} | null
  room: MeetingRoom; events: RoomEvent[]; synced_at: string; valid_until: string
  checkin_qr?: string | null
  usage_owner?: 'official' | 'v5'
  titles_available: boolean
  server_time: string
  daylight?: { city: string | null; timezone: string; windows: { start: string; end: string }[]; valid_until: string }
}
export const meetingRoomsApi = {
  display: (token: string, signal: AbortSignal) => axios.get<ApiEnvelope<RoomSchedule>>('/api/meeting-rooms/display', {
    headers: { Authorization: `Bearer ${token}` }, signal, timeout: 30000,
  }),
}
