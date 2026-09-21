<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import RoomCheckinCard from '@/components/RoomCheckinCard.vue'
import RoomUsageCard from '@/components/RoomUsageCard.vue'
import { meetingRoomsApi, type RoomSchedule, type RoomEvent } from '@/api/meetingRooms'
import { watchPageRelease } from '@/utils/pageRelease'

const emit = defineEmits<{ 'theme-change': [theme: string] }>()
const props = defineProps<{ controlRoom?: string; controlToken?: string; controlTheme?: string; displayVersion?: string }>()
const route = useRoute()
const version = computed(() => props.displayVersion || (['v1', 'v2', 'v3', 'v4', 'v5'].includes(String(route.query.version)) ? String(route.query.version) : localStorage.getItem('argus_room_version')) || 'v4')
const isV2 = computed(() => version.value !== 'v1')
const isV3 = computed(() => ['v3', 'v4', 'v5'].includes(version.value))
const isV4 = computed(() => ['v4', 'v5'].includes(version.value))
const isV5 = computed(() => version.value === 'v5')
const storageKey = 'argus_room_display'
const token = ref(localStorage.getItem(storageKey) || '')
const input = ref('')
const snapshot = ref<RoomSchedule | null>(null)
const now = ref(Date.now())
const themeMode = computed(() => props.controlTheme || 'auto')
const timezone = computed(() => snapshot.value?.daylight?.timezone || 'Asia/Shanghai')
const daylightKnown = computed(() => !!snapshot.value?.daylight?.city && now.value < Date.parse(snapshot.value.daylight.valid_until))
const isLight = computed(() => themeMode.value === 'light' || (themeMode.value === 'auto' && daylightKnown.value && snapshot.value?.daylight?.windows.some(w => Date.parse(w.start) <= now.value && now.value < Date.parse(w.end))))
const themeLabel = computed(() => themeMode.value === 'auto' ? daylightKnown.value ? `${snapshot.value?.daylight?.city} · ${isLight.value ? '日间' : '夜间'}` : '城市待配置' : '手动预览')
watch(isLight, value => emit('theme-change', value ? 'light' : 'dark'), { immediate: true })
const failed = ref(false)
const message = ref('')
const pending = ref(false)
const abort = new AbortController()
let serverBase = Date.now()
let monotonicBase = performance.now()
const tick = () => { now.value = serverBase + performance.now() - monotonicBase }
let poll: ReturnType<typeof setInterval> | undefined
let clock: ReturnType<typeof setInterval> | undefined
let stopReleaseWatch: (() => void) | undefined
const bound = computed(() => !!token.value || !!props.controlRoom)
const fresh = computed(() => !failed.value && snapshot.value && now.value < Date.parse(snapshot.value.valid_until))
const allEvents = computed(() => snapshot.value?.events ?? [])
const dateKey = (value: number) => {
  const parts = new Intl.DateTimeFormat('en', { timeZone: timezone.value, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(value)
  return ['year', 'month', 'day'].map(type => parts.find(p => p.type === type)?.value).join('-')
}
const events = computed(() => allEvents.value.filter(e => dateKey(Date.parse(e.start_time)) <= dateKey(now.value) && dateKey(Date.parse(e.end_time) - 1) >= dateKey(now.value)))
const windowStart = computed(() => {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: timezone.value, minute: '2-digit', second: '2-digit' }).formatToParts(now.value)
  const part = (name: string) => Number(parts.find(p => p.type === name)?.value || 0)
  return Math.floor(now.value / 1000) * 1000 - (part('minute') * 60 + part('second')) * 1000 - 6 * 3600000
})
const ticks = computed(() => Array.from({ length: 7 }, (_, i) => windowStart.value + i * 2 * 3600000))
const timelineEvents = computed(() => allEvents.value.filter(e => Date.parse(e.end_time) > windowStart.value && Date.parse(e.start_time) < windowStart.value + 43200000))
const tickLabel = (value: number) => `${dateKey(value) < dateKey(now.value) ? '昨 ' : dateKey(value) > dateKey(now.value) ? '明 ' : ''}${time(value)}`
const current = computed(() => events.value.find(e => Date.parse(e.start_time) <= now.value && now.value < Date.parse(e.end_time)))
const futureEvents = computed(() => allEvents.value.filter(e => Date.parse(e.start_time) > now.value).sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time)))
const next = computed(() => isV3.value ? futureEvents.value[0] : events.value.find(e => Date.parse(e.start_time) > now.value))
const disabled = computed(() => snapshot.value?.room.enabled === false)
const state = computed(() => !fresh.value ? '状态暂不可确认' : disabled.value ? '会议室已停用' : current.value ? (isV3.value ? '使用中' : '正在使用') : next.value && Date.parse(next.value.start_time) - now.value <= 15 * 60000 ? '即将开始' : '空闲可用')
const accent = computed(() => !fresh.value || disabled.value ? '#94a3b8' : current.value ? '#EF4444' : state.value === '即将开始' ? '#F59E0B' : isLight.value ? '#059669' : '#34D399')
const terminalState = computed(() => props.controlRoom || !bound.value || !fresh.value || disabled.value ? 'unknown' : current.value ? 'busy' : state.value === '即将开始' ? 'soon' : 'free')
const active = computed(() => current.value ?? next.value)
const minutes = computed(() => active.value ? Math.max(0, Math.ceil((Date.parse(current.value ? active.value.end_time : active.value.start_time) - now.value) / 60000)) : 0)
const remainingEvents = computed(() => events.value.filter(e => Date.parse(e.end_time) > now.value))
const pastEvents = computed(() => events.value.filter(e => Date.parse(e.end_time) <= now.value))
const agendaEvents = computed(() => isV3.value ? futureEvents.value.slice(0, 2) : isV2.value ? [current.value, next.value].filter((event): event is RoomEvent => !!event) : fresh.value ? remainingEvents.value : events.value)
const progress = computed(() => current.value ? Math.min(100, Math.max(0, (now.value - Date.parse(current.value.start_time)) / (Date.parse(current.value.end_time) - Date.parse(current.value.start_time)) * 100)) : 0)
const time = (value: string | number) => new Date(value).toLocaleTimeString('zh-CN', { timeZone: timezone.value, hour: '2-digit', minute: '2-digit', hour12: false })
const date = computed(() => new Date(now.value).toLocaleDateString('zh-CN', { timeZone: timezone.value, year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }))
const lastSynced = computed(() => snapshot.value ? new Date(snapshot.value.synced_at).toLocaleString('zh-CN', { timeZone: timezone.value, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '')
const title = (event: RoomEvent) => event.summary || '已预约会议'
function position(value: string | number) {
  return Math.min(100, Math.max(0, (new Date(value).getTime() - windowStart.value) / 43200000 * 100))
}
function bar(event: RoomEvent) {
  const start = position(event.start_time)
  const end = position(event.end_time)
  return { left: `${start}%`, width: `${Math.max(0, end - start)}%` }
}
async function refresh() {
  if (!bound.value || pending.value || abort.signal.aborted) return
  pending.value = true
  try {
    const response = props.controlRoom ? await axios.get<{ data: RoomSchedule }>('/api/room-control/preview', { params: { room_id: props.controlRoom }, headers: { Authorization: `Bearer ${props.controlToken}` }, signal: abort.signal, timeout: 30000 }) : await meetingRoomsApi.display(token.value, abort.signal)
    if (!response.data.data) throw new Error('Missing schedule')
    serverBase = Date.parse(response.data.data.server_time)
    if (!Number.isFinite(serverBase)) throw new Error('Missing server clock')
    monotonicBase = performance.now(); tick()
    snapshot.value = response.data.data; failed.value = false; message.value = ''
  } catch (err) {
    if (axios.isCancel(err)) return
    failed.value = true
    message.value = '同步失败，正在重试'
    if (axios.isAxiosError(err) && (err.response?.status === 401 || err.response?.status === 403)) {
      if (!props.controlRoom) { token.value = ''; localStorage.removeItem(storageKey) }
      snapshot.value = null
      message.value = '凭证已失效，请重新绑定'
    }
    console.warn('Room display sync failed', axios.isAxiosError(err) ? err.response?.status : 'invalid response')
  } finally { pending.value = false }
}
function bind() {
  if (!/^room:omm_[a-zA-Z0-9]+:[A-Za-z0-9_-]{43}$/.test(input.value.trim())) { message.value = '请输入管理员提供的完整门牌凭证'; return }
  token.value = input.value.trim(); localStorage.setItem(storageKey, token.value); input.value = ''; refresh()
}
function visibility() { if (!document.hidden) { tick(); refresh() } }
onMounted(() => {
  if (!props.controlRoom) stopReleaseWatch = watchPageRelease(() => bound.value && !pending.value)
  refresh(); poll = setInterval(refresh, 15000); clock = setInterval(tick, 1000)
  document.addEventListener('visibilitychange', visibility)
})
onUnmounted(() => {
  stopReleaseWatch?.()
  abort.abort(); clearInterval(poll); clearInterval(clock)
  document.removeEventListener('visibilitychange', visibility)
})
</script>

<template>
  <main class="door" data-terminal-protocol="1" :data-terminal-state="terminalState" :class="[isLight ? 'theme-light' : 'theme-dark', { v2: isV2, v3: isV3, v4: isV4, v5: isV5 }]" :style="{ '--accent': accent }">
    <form v-if="!bound" class="binding" @submit.prevent="bind">
      <p class="eyebrow">ARGUS / MEETING ROOM</p><h1>绑定会议门牌</h1>
      <p>请输入管理员为这间会议室生成的设备凭证。</p>
      <input v-model="input" aria-label="设备凭证" type="password" autocomplete="off" placeholder="粘贴设备凭证" />
      <button type="submit">绑定并显示</button><p role="status">{{ message }}</p>
    </form>
    <template v-else>
      <header class="door-header">
        <div class="room-identity"><p class="eyebrow">ARGUS / MEETING ROOM </p>
          <h1 :title="snapshot?.room.name">{{ snapshot?.room.name || '正在获取会议室' }}</h1>
          <p class="capacity"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6m2 4a6 6 0 0 1 3 5v2"/></svg>{{ snapshot ? `可容纳 ${snapshot.room.capacity} 人` : '正在同步' }}</p></div>
        <div class="clock"><strong>{{ time(now) }}</strong><p>{{ date }}</p><span class="theme-control">{{ themeLabel }}</span></div>
      </header>
      <p v-if="snapshot && !fresh" class="history-warning" role="status">历史日程 · 最后同步 {{ lastSynced }} · 正在重试，当前状态待确认</p>
      <div class="content">
        <section class="current" :class="{ 'is-free': fresh && !disabled && !current, 'is-soon': state === '即将开始', 'with-checkin': (isV5 || (isV3 && !!snapshot?.checkin_qr)) && !disabled }">
          <div class="primary-info">
            <span class="status" :class="{ 'large-status': isV3 && ['使用中', '即将开始', '空闲可用'].includes(state) }" role="status"><i aria-hidden="true" /><span class="status-text">{{ state }}</span></span>
            <div class="primary-body">
            <template v-if="snapshot && !disabled">
              <div v-if="current || state === '即将开始'" class="hero">
                <p class="hero-label">{{ current ? '距本场结束还有' : '距下场开始还有' }}</p>
                <p class="countdown"><strong>{{ minutes }}</strong><span>分钟</span></p>
              </div>
              <div v-else class="hero">
                <template v-if="next"><p class="hero-label">{{ fresh ? '当前可用至' : '历史预约空档至' }}</p><p class="available-until">{{ time(next.start_time) }}</p></template>
                <h2 v-else class="all-free">{{ fresh ? '全天无后续预约' : '暂无可参考的后续预约' }}</h2>
              </div>
              <div v-if="active" class="meeting-detail">
                <p class="detail-label">{{ current ? '当前会议' : '下一场会议' }}</p>
                <h2 :title="title(active)">{{ title(active) }}</h2>
                <p class="meeting-time">{{ time(active.start_time) }} — {{ time(active.end_time) }}</p>
                <p class="organizer">组织者 · {{ active.organizer || '信息不可见' }}</p>
              </div>
              <div v-if="current" class="meeting-progress" role="progressbar" aria-label="本场会议进度" :aria-valuenow="Math.round(progress)" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${progress}%` }" /></div>
              <div v-else-if="fresh && !isV3" class="booking-guide"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-13 5h8"/></svg><div><strong>扫码预订</strong><p>预约入口待接入</p></div></div>
            </template>
            <template v-else><h2 class="unavailable">{{ disabled && fresh ? '暂不可使用' : '等待日程同步' }}</h2><p class="organizer">{{ message || '正在确认最新预约状态' }}</p></template>
            </div>
          </div>
          <RoomUsageCard v-if="isV5 && snapshot && !disabled" :key="snapshot.room.room_id" :room-id="snapshot.room.room_id" :room-name="snapshot.room.name" :timezone="timezone" :event="active" :now="now" :fresh="!!fresh" :preview="!!controlRoom" :control-token="controlToken" @changed="refresh" />
          <p v-else-if="snapshot?.usage_owner === 'v5' && !disabled" role="status">本房间使用 V5 确认，请切换到 V5 页面</p>
          <RoomCheckinCard v-else-if="isV3 && snapshot?.checkin_qr && !disabled" :dark="!isLight" :qr="snapshot.checkin_qr" :room-name="snapshot.room.name" />
        </section>
        <section class="agenda">
          <header class="agenda-header"><h3>{{ isV3 ? '后续会议' : isV2 ? '本场与下一场' : '今日安排' }} <span v-if="!fresh">· 上次同步数据</span></h3><span v-if="!isV2 && fresh && remainingEvents.length" class="agenda-count">{{ remainingEvents.length }} 场待完成</span></header>
          <div class="agenda-body">
            <article v-for="event in agendaEvents" :key="`${event.uid}:${event.original_time}:${event.start_time}`" :class="{ active: fresh && event === current, upcoming: fresh && event === next && state === '即将开始' }">
              <div class="event-top"><p><small v-if="isV3" class="event-day">{{ dateKey(Date.parse(event.start_time)) === dateKey(now) ? '今天' : new Date(event.start_time).toLocaleDateString('zh-CN', { timeZone: timezone, month: 'numeric', day: 'numeric' }) }}</small>{{ time(event.start_time) }} — {{ time(event.end_time) }}</p><span class="tag">{{ !fresh ? '预约' : event === current ? '进行中' : event === next ? '下一场' : '待开始' }}</span></div>
              <h4 :title="title(event)">{{ title(event) }}</h4><p class="event-organizer">组织者 · {{ event.organizer || '信息不可见' }}</p>
            </article>
            <div v-if="fresh && (isV3 ? !agendaEvents.length : !remainingEvents.length)" class="agenda-empty">
              <svg class="empty-art" viewBox="0 0 160 120" fill="none" aria-hidden="true"><rect x="38" y="23" width="84" height="78" rx="12" stroke="currentColor" stroke-width="2"/><path d="M38 46h84M58 14v18m44-18v18" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="m62 73 12 12 25-26" stroke="var(--accent)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <h4>{{ disabled ? '会议室已停用' : isV3 ? '暂无后续会议' : !events.length ? '今日全天空闲' : '今日会议已结束' }}</h4><p>{{ disabled ? '会议室当前已停用' : '为下一次交流，留出空间' }}</p>
              <div class="room-fact"><strong>{{ snapshot?.room.capacity || 0 }}</strong><span>人 · 会议空间</span></div>
            </div>
            <p v-else-if="!agendaEvents.length" class="pending-message">等待获取日程</p>
            <details v-if="!isV2 && fresh && pastEvents.length" class="history"><summary>已结束 · {{ pastEvents.length }} 场</summary><div v-for="event in pastEvents" :key="`${event.uid}:${event.start_time}`"><p>{{ time(event.start_time) }} — {{ time(event.end_time) }}</p><h4>{{ title(event) }}</h4><small>组织者 · {{ event.organizer || '信息不可见' }}</small></div></details>
          </div>

        </section>
      </div>
      <section class="timeline" aria-label="滚动12小时预约时间轴">
        <p class="timeline-label"><span>近 12 小时</span><span v-if="!isV2">预约时间轴</span><span v-else class="timeline-legend"><span><i />可约</span><span><i class="reserved" />已约</span><span><i class="finished" />已结束</span></span></p>
        <div class="track" :class="{ unknown: isV2 && (!fresh || disabled) }"><span v-for="event in timelineEvents" :key="`${event.uid}:${event.start_time}`" :style="bar(event)" :class="{ elapsed: Date.parse(event.end_time) <= now }" /><i :style="{ left: `${position(now)}%` }" /></div>
        <div class="ticks"><span v-for="value in ticks" :key="value">{{ tickLabel(value) }}</span></div>
      </section>
      <footer :class="{ stale: !fresh }"><span>{{ fresh ? '● 日程已同步' : '● 日程待更新' }} · 飞书预约日程{{ snapshot ? ` · ${time(snapshot.synced_at)}` : '' }}</span><span v-if="snapshot && !snapshot.titles_available">部分会议主题不可见</span></footer>
    </template>
  </main>
</template>

<style scoped>
.history-warning{flex-shrink:0;font-size:14px;line-height:1.5;color:var(--muted);border-left:3px solid #94a3b8;padding-left:10px}

.door{--surface:#1e293b;--text:#f8fafc;--muted:#a5b4c8;--subtle:#738197;--line:rgba(255,255,255,.08);--track:#243044;--shadow:none;min-height:100dvh;background:#0b0f19;color:var(--text);padding:clamp(24px,3vw,48px);font-family:Inter,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;display:flex;flex-direction:column;gap:24px;color-scheme:dark}
.door.theme-light{--surface:#fff;--text:#0f172a;--muted:#52627a;--subtle:#8491a3;--line:#e2e8f0;--track:#e7edf3;--shadow:0 8px 28px rgba(0,0,0,.04);background:#f8fafc;color-scheme:light}
.door-header{display:flex;justify-content:space-between;gap:32px;align-items:center;padding-bottom:20px;border-bottom:1px solid var(--line)}.room-identity{min-width:0}.eyebrow{font-size:12px;letter-spacing:2.5px;color:var(--muted);margin-bottom:10px}h1{font-size:clamp(40px,4.5vw,76px);font-weight:700;line-height:1.12;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:-1px}.capacity{display:flex;gap:10px;align-items:center;font-size:20px;color:var(--muted);margin-top:12px}.capacity svg{width:22px;height:22px}.clock{text-align:right;flex-shrink:0}.clock strong{font-size:clamp(48px,5.2vw,88px);font-weight:500;line-height:1;letter-spacing:-2px;font-variant-numeric:tabular-nums}.clock p{font-size:17px;color:var(--muted);margin-top:12px}.theme-control{display:block;color:var(--subtle);font-size:12px;margin-top:6px}
.content{display:grid;grid-template-columns:minmax(0,6fr) minmax(0,4fr);gap:clamp(24px,3vw,48px);flex:1;min-height:380px}.current{border-left:6px solid var(--accent);padding:clamp(20px,3vh,36px) clamp(24px,3vw,48px);display:flex;align-items:center;min-width:0}.primary-info{width:100%;display:flex;flex-direction:column;gap:clamp(20px,3vh,36px)}.status{display:flex;align-items:center;gap:14px;font-size:clamp(32px,2.8vw,40px);font-weight:600;line-height:1.2;color:var(--accent);background:none}.status i{display:block;width:12px;height:12px;border-radius:50%;background:var(--accent);flex-shrink:0}.hero-label{font-size:24px;color:var(--muted);margin-bottom:8px}.countdown{display:flex;align-items:baseline;gap:16px;line-height:1}.countdown strong,.available-until{font-size:clamp(64px,6.7vw,100px);font-weight:600;letter-spacing:-3px;font-variant-numeric:tabular-nums;line-height:1}.countdown span{font-size:28px;color:var(--muted)}.all-free{font-size:clamp(42px,4.2vw,64px);font-weight:600;line-height:1.3;max-width:9em}.detail-label{font-size:15px;color:var(--subtle);margin-bottom:8px}.meeting-detail h2{font-size:clamp(28px,2.7vw,42px);font-weight:600;line-height:1.25;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.meeting-time{font-size:clamp(24px,2.1vw,34px);font-variant-numeric:tabular-nums;margin-top:10px}.organizer{font-size:22px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}.meeting-progress{height:5px;border-radius:2px;background:var(--track);overflow:hidden}.meeting-progress span{display:block;height:100%;background:var(--accent)}.booking-guide{display:flex;align-items:center;gap:16px;border-top:1px solid var(--line);padding-top:22px;margin-top:4px}.booking-guide svg{width:32px;height:32px;color:var(--accent);flex-shrink:0}.booking-guide strong{font-size:21px;font-weight:500}.booking-guide p{font-size:16px;color:var(--muted);margin-top:4px}.unavailable{font-size:42px;font-weight:600}
.agenda{display:flex;flex-direction:column;min-width:0;min-height:0}.agenda-header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:20px}.agenda h3{font-size:26px;font-weight:600}.agenda h3 span{font-size:13px;color:var(--muted)}.agenda-count{font-size:14px;color:var(--subtle);white-space:nowrap}.agenda-body{flex:1;min-height:0;overflow:auto;max-height:clamp(400px,calc(100dvh - 380px),800px);scrollbar-width:thin;scrollbar-color:var(--line) transparent;display:flex;flex-direction:column;gap:16px}.agenda article{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:clamp(20px,2.2vw,32px);flex-shrink:0;position:relative;overflow:hidden}.agenda article.active:before,.agenda article.upcoming:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}.event-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.event-top p{font-size:clamp(22px,2.1vw,32px);font-weight:500;font-variant-numeric:tabular-nums;white-space:nowrap}.tag{font-size:14px;color:var(--muted);white-space:nowrap}.active .tag,.upcoming .tag{color:var(--accent)}.agenda h4{font-size:clamp(24px,2.1vw,32px);font-weight:500;line-height:1.3;overflow-wrap:anywhere;margin-top:12px}.event-organizer{font-size:19px;color:var(--muted);margin-top:12px}.agenda-empty{flex:1;min-height:320px;background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;text-align:center}.empty-art{width:160px;height:120px;color:var(--subtle);margin-bottom:8px}.agenda-empty h4{font-size:28px}.agenda-empty>p{font-size:17px;color:var(--muted);margin-top:12px}.room-fact{border-top:1px solid var(--line);padding-top:20px;margin-top:24px;color:var(--muted)}.room-fact strong{font-size:32px;font-weight:500;color:var(--text);margin-right:8px}.room-fact span{font-size:18px}.history{color:var(--muted);padding:8px 0}.history summary{cursor:pointer;font-size:16px;padding:8px}.history>div{padding:18px;border-bottom:1px solid var(--line)}.history h4{font-size:22px;margin:6px 0}.pending-message{color:var(--muted);padding:24px}
.timeline{border-top:1px solid var(--line);padding-top:16px}.timeline-label{display:flex;justify-content:space-between;font-size:13px;color:var(--subtle);margin-bottom:14px}.track{position:relative;height:22px;border-radius:4px;background:repeating-linear-gradient(to right,transparent 0,transparent calc(16.666% - 1px),var(--line) calc(16.666% - 1px),var(--line) 16.666%),var(--track)}.track>span{position:absolute;top:0;height:100%;background:var(--accent);border-radius:3px;opacity:.8}.track>span.elapsed{background:var(--subtle);opacity:.45}.track i{position:absolute;width:3px;top:-5px;bottom:-5px;background:var(--text);border-radius:2px}.ticks{display:flex;justify-content:space-between;color:var(--muted);font-size:14px;margin-top:12px;font-variant-numeric:tabular-nums}footer{display:flex;justify-content:space-between;gap:16px;color:var(--subtle);font-size:12px}footer.stale{color:var(--muted)}
.binding{margin:auto;max-width:560px;width:100%;display:flex;flex-direction:column;gap:20px}.binding input{background:var(--surface);border:1px solid var(--line);padding:16px;border-radius:10px;color:var(--text)}.binding button{padding:14px;background:#4f46e5;border-radius:10px;color:white;font-size:18px}
@media(min-width:701px) and (max-height:900px){.door{gap:16px;padding-top:24px;padding-bottom:20px}.door-header{padding-bottom:16px}.content{min-height:360px}.current{padding-top:16px;padding-bottom:16px}.primary-info{gap:16px}.detail-label{display:none}.booking-guide div{display:flex;align-items:baseline;gap:12px}.booking-guide p{margin:0;font-size:14px}.hero-label{font-size:22px}.countdown strong,.available-until{font-size:64px}.meeting-detail h2{font-size:28px}.agenda-body{max-height:calc(100dvh - 360px)}.agenda-header{margin-bottom:16px}.agenda article{padding:20px}.event-organizer{font-size:18px}.booking-guide{padding-top:16px}.timeline{padding-top:12px}}
@media(max-width:700px){.door{padding:24px;gap:24px}.door-header{gap:16px;align-items:start;flex-direction:column}h1{font-size:40px;white-space:normal;overflow-wrap:anywhere}.clock{text-align:left}.clock strong{font-size:48px}.content{grid-template-columns:1fr}.current{padding:16px 0 16px 20px}.primary-info{gap:24px}.countdown strong{font-size:64px}.agenda-body{max-height:none}.event-top p{font-size:22px}.agenda article{padding:20px}.timeline-label{font-size:12px}.ticks{font-size:11px}.all-free{font-size:40px}footer{flex-wrap:wrap}}
</style>

<style scoped src="./roomDisplayV2.css"></style>

<style scoped>
.door.v3:after{content:"";position:fixed;inset:0;border:clamp(6px,.65vw,12px) solid var(--accent);pointer-events:none;z-index:60}.v3 .event-day{display:block;font-size:14px;color:var(--muted);margin-bottom:5px}.v3 .status,.v3 .with-checkin .status{font-size:clamp(28px,3.4cqw,44px)}.v3 .content{min-height:480px}.v3 .current.with-checkin{display:grid;grid-template-columns:minmax(0,1fr) clamp(180px,20cqw,300px);gap:clamp(16px,2.4cqw,36px);align-items:center;padding-right:0}.v3 .with-checkin .primary-info{min-width:0}.v3 .with-checkin .meeting-detail h2{font-size:clamp(22px,2.6cqw,36px)}.v3 .with-checkin .meeting-time{font-size:clamp(18px,2.2cqw,30px)}.v3 .with-checkin .countdown{flex-wrap:wrap;gap:8px}.v3 .with-checkin .countdown strong,.v3 .with-checkin .available-until{font-size:clamp(42px,6cqw,90px)}
@container(max-aspect-ratio:1/1){.v3 .content{grid-template-rows:minmax(400px,1.2fr) minmax(260px,1fr)}.v3 .current.with-checkin{grid-template-columns:minmax(0,1fr) clamp(180px,32cqw,260px);padding-right:12px}}
@media(max-width:600px){.v3 .current.with-checkin{grid-template-columns:1fr;padding-right:16px}.v3 .content{min-height:1080px;grid-template-rows:auto auto}.v3 .with-checkin .primary-info{padding-bottom:8px}.v3 .current.with-checkin :deep(.checkin-card){width:min(100%,240px);justify-self:center}}

/* Keep the existing status bottom edge and the following content in place. */
.v3 .current{border-left-color:transparent}.v3 .large-status{height:calc(clamp(28px,3.4cqw,44px) * 1.2);flex-shrink:0;align-items:flex-end;overflow:visible}.v3 .large-status .status-text{font-size:clamp(42px,6cqw,90px);line-height:1.2;font-weight:600;white-space:nowrap}.v3 .large-status i{margin-bottom:calc(clamp(42px,6cqw,90px) * .6 - 6px)}.v3 .countdown strong,.v3 .available-until{font-size:clamp(42px,6cqw,90px)}
@media(max-width:600px){.v3 .primary-info{padding-top:24px}}
/* Landscape terminals fit the viewport; inner panels retain their own scrolling. */
@media(min-width:701px) and (min-height:701px) and (orientation:landscape){.v3 .content{min-height:0}}
</style>

<style scoped>
/* V4 retains the V3 feature set; physical side lights replace the perimeter frame. */
.door.v4:after{content:none;border:0}
@media(min-width:701px) and (orientation:landscape){
  .v4 .agenda-header{margin-bottom:10px}
  .v4 .agenda-body{gap:12px}
  .v4 .agenda article{padding:12px 20px;border-radius:14px}
  .v4 .event-top p{font-size:28px;line-height:1.2}
  .v4 .event-day{font-size:13px;line-height:16px;margin-bottom:4px}
  .v4 .agenda h4{font-size:26px;line-height:1.25;margin-top:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .v4 .event-organizer{font-size:18px;line-height:1.3;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}
/* 1080p at Android density 240 has a 1280×720 CSS viewport. */
@media(min-width:701px) and (min-height:701px) and (max-height:760px) and (orientation:landscape){
  .v4 .agenda-body{gap:8px}
  .v4 .agenda article{padding-top:8px;padding-bottom:8px}
}
</style>


<style scoped>
.primary-body{display:contents}
/* V5 shares two grid rows: headings, then full-height content panels. */
@media(min-width:1000px) and (min-height:600px) and (orientation:landscape){
  .v5 .content{grid-template-columns:minmax(0,1.2fr) minmax(260px,.95fr) minmax(0,1.15fr);grid-template-rows:auto minmax(0,1fr);column-gap:clamp(18px,2.2cqw,32px);row-gap:18px;align-items:end;min-height:0}
  .v5 .current.with-checkin,.v5 .primary-info,.v5 .agenda{display:contents}
  .v5 .status{grid-column:1;grid-row:1;align-self:end;align-items:baseline;height:auto;line-height:1;margin:0;gap:10px}
  .v5 .large-status .status-text{font-size:clamp(42px,5.4cqw,72px);line-height:1}
  .v5 .large-status i{width:10px;height:10px;margin:0;align-self:center}
  .v5 .primary-body{grid-column:1;grid-row:2;align-self:stretch;min-height:0;display:flex;flex-direction:column;gap:12px;overflow:auto;padding:0 12px 0 0}
  .v5 .primary-body .meeting-progress{margin-top:auto;flex-shrink:0}
  .v5 .primary-body .countdown strong,.v5 .primary-body .available-until{font-size:clamp(42px,5.4cqw,72px)}
  .v5 .primary-body .meeting-detail h2{font-size:clamp(22px,2.4cqw,32px)}
  .v5 :deep(.usage-card){display:contents}
    .v5 .agenda-header h3{font-size:clamp(22px,2.3cqw,30px);line-height:1.2;font-weight:600}
  .v5 :deep(.usage-body){grid-column:2;grid-row:2;align-self:stretch;min-height:0;height:100%}
  .v5 .agenda-header{grid-column:3;grid-row:1;align-self:end;margin:0;line-height:1.2}
  .v5 .agenda-body{grid-column:3;grid-row:2;align-self:stretch;min-height:0}
  .v5 .agenda-empty{border-radius:16px}
}
</style>
