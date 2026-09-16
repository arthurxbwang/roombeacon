<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import RoomDisplay from './RoomDisplay.vue'
interface Room { room_id: string; name: string; region: string; location: string; floor: string; capacity: number }
const previewTheme = ref('dark')
const themeMode = ref('auto')
const savedVersion = localStorage.getItem('argus_room_version')
const displayVersion = ref(savedVersion && ['v1', 'v2', 'v3'].includes(savedVersion) ? savedVersion : 'v2')
watch(displayVersion, value => localStorage.setItem('argus_room_version', value))
const fullscreen = ref(false)
const fullscreenError = ref('')
function syncFullscreen() { fullscreen.value = !!document.fullscreenElement }
async function toggleFullscreen() {
  fullscreenError.value = ''
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen()
    else fullscreenError.value = '此浏览器不支持网页全屏，请使用浏览器全屏或添加到主屏幕'
  } catch (err) {
    console.warn('Room fullscreen request failed', err instanceof Error ? err.name : 'unknown')
    fullscreenError.value = '全屏未能开启，请使用浏览器全屏或添加到主屏幕'
  }
}

const key = 'argus_room_control'
const credential = ref(sessionStorage.getItem(key) || '')
const input = ref(''), selected = ref(''), region = ref(''), search = ref(''), error = ref('')
const rooms = ref<Room[]>([])
const ready = ref(false), loading = ref(false)
const abort = new AbortController()
const regions = computed(() => [...new Set(rooms.value.map(r => r.region))].sort((a,b) => a.localeCompare(b,'zh-CN')))
const filtered = computed(() => rooms.value.filter(r => (!region.value || r.region === region.value) && `${r.name} ${r.location}`.toLowerCase().includes(search.value.toLowerCase())))
const index = computed(() => filtered.value.findIndex(r => r.room_id === selected.value))
async function load() {
  if (!credential.value || loading.value) return
  loading.value = true; error.value = ''
  try {
    const response = await axios.get<{data: Room[]}>('/api/room-control/rooms', {headers:{Authorization:`Bearer ${credential.value}`},signal:abort.signal,timeout:120000})
    rooms.value = response.data.data; ready.value = true; sessionStorage.setItem(key,credential.value)
  } catch (err) {
    if (axios.isCancel(err)) return
    error.value = axios.isAxiosError(err) && err.response?.status === 401 ? '主控凭证无效，请重新输入' : '目录加载失败，请重试'
    ready.value = false; sessionStorage.removeItem(key)
  } finally { loading.value = false }
}
function login() { credential.value = input.value.trim(); input.value = ''; load() }
function logout() { sessionStorage.removeItem(key); credential.value = ''; selected.value = ''; rooms.value = []; ready.value = false }
function move(step:number) { const room = filtered.value[index.value+step]; if(room) selected.value = room.room_id }
onMounted(() => { load(); document.addEventListener('fullscreenchange', syncFullscreen); syncFullscreen() })
onUnmounted(() => { abort.abort(); document.removeEventListener('fullscreenchange', syncFullscreen) })
</script>
<template>
  <div v-if="selected && ready" class="preview-shell" :class="{ 'preview-v2': displayVersion !== 'v1' }">
    <nav class="preview-tools" :class="{ light: previewTheme === 'light' }" aria-label="预览切换"><button @click="selected = ''">← 返回主控</button><span>测试预览 · {{ index+1 }} / {{ filtered.length }}</span><select v-model="displayVersion" aria-label="门牌版本" class="version-switch"><option value="v1">V1 经典版</option><option value="v2">V2 自适应</option><option value="v3">V3 扫码签到</option></select><button @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '全屏' }}</button><div class="theme-switch" role="group" aria-label="日出日落测试"><button v-for="mode in [{id: 'auto', label: '自动'}, {id: 'light', label: '☀ 日间'}, {id: 'dark', label: '☾ 夜间'}]" :key="mode.id" :aria-pressed="themeMode === mode.id" @click="themeMode = mode.id">{{ mode.label }}</button></div><button :disabled="index <= 0" @click="move(-1)">上一间</button><button :disabled="index >= filtered.length-1" @click="move(1)">下一间</button><p v-if="fullscreenError" class="fullscreen-error" role="status">{{ fullscreenError }}</p></nav>
    <RoomDisplay :key="selected" :control-room="selected" :control-token="credential" :control-theme="themeMode" :display-version="displayVersion" @theme-change="previewTheme = $event" />
  </div>
  <main v-else class="control">
    <header><div><p>ARGUS · 测试工具</p><h1>会议门牌主控</h1><p>按地区查找会议室，直接预览真实日程。</p></div><button v-if="ready" @click="logout">退出主控</button></header>
    <form v-if="!ready" class="login" @submit.prevent="login"><label for="control-token">测试主控凭证</label><input id="control-token" v-model="input" type="password" autocomplete="off" placeholder="粘贴主控凭证" required /><button :disabled="loading">{{ loading ? '正在读取目录…' : '进入主控' }}</button><p role="alert">{{ error }}</p></form>
    <template v-else>
      <section class="filters"><label>地区 / 园区<select v-model="region"><option value="">全部地区</option><option v-for="item in regions" :key="item">{{ item }}</option></select></label><label>会议室 / 楼栋<input v-model="search" placeholder="输入名称或位置关键词" /></label><span>{{ filtered.length }} 间会议室</span></section>
      <div class="table-wrap"><table><thead><tr><th>地区 / 园区</th><th>会议室</th><th>楼层</th><th>容量</th><th>操作</th></tr></thead><tbody><tr v-for="room in filtered" :key="room.room_id"><td>{{ room.region }}</td><td><strong>{{ room.name }}</strong><small>{{ room.location }}</small></td><td>{{ room.floor }}</td><td>{{ room.capacity }} 人</td><td><button @click="selected = room.room_id">预览门牌</button></td></tr></tbody></table><p v-if="!filtered.length" class="empty">没有匹配的会议室，请调整筛选条件。</p></div>
    </template>
  </main>
</template>
<style scoped>
.control{min-height:100dvh;background:#f1f5f9;color:#0f172a;padding:clamp(20px,4vw,56px)}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}header p{color:#64748b}h1{font-size:32px;font-weight:700;margin:8px 0}button{background:#4f46e5;color:white;border-radius:8px;padding:10px 16px;white-space:nowrap}button:disabled{opacity:.4;cursor:not-allowed}input,select{background:white;border:1px solid #cbd5e1;padding:12px;border-radius:8px;color:#0f172a;width:100%}.login{max-width:480px;background:white;padding:28px;display:grid;gap:18px;border-radius:16px}.login p{color:#b91c1c}.filters{display:flex;align-items:end;gap:20px;margin-bottom:24px}.filters label{display:grid;gap:8px;min-width:230px}.filters span{padding-bottom:12px;color:#64748b}.table-wrap{overflow:auto;border:1px solid #e2e8f0;border-radius:12px;background:white}table{width:100%;text-align:left}th{background:#f8fafc;font-size:14px;color:#64748b}th,td{padding:16px;border-bottom:1px solid #e2e8f0}td small{display:block;max-width:560px;color:#64748b;margin-top:5px}.empty{padding:32px;color:#64748b}.preview-tools{display:flex;align-items:center;gap:12px;padding:10px 24px;background:#17243b;color:#cbd5e1}.preview-tools span{margin-right:auto;font-size:14px}.preview-tools.light{background:#f5f7fb;color:#475569;box-shadow:inset 0 -1px #e3e9f1}.preview-tools button{padding:7px 14px}.theme-switch{display:flex;border-radius:999px;padding:2px;background:#26364f}.theme-switch button{border-radius:999px;background:transparent;color:#cbd5e1;padding:5px 12px}.theme-switch button[aria-pressed="true"]{background:#4f46e5;color:white}.light .theme-switch{background:#e2e8f0}.light .theme-switch button:not([aria-pressed="true"]){color:#475569}.preview-shell :deep(.door){min-height:calc(100dvh - 58px);padding-top:12px;padding-bottom:12px;gap:12px}@media(max-width:700px){.filters{flex-direction:column;align-items:stretch}.preview-tools{flex-wrap:wrap;padding:10px}.preview-tools span{display:none}th,td{padding:12px}}
.preview-v2{height:100dvh;display:grid;grid-template-rows:auto minmax(0,1fr)}.preview-tools{flex-wrap:wrap}.preview-tools .version-switch{width:auto;padding:6px 10px;font-size:14px}.fullscreen-error{flex-basis:100%;font-size:13px}.preview-v2 :deep(.door.v2){height:100%;min-height:0}.preview-tools .theme-switch span{margin:0}
@media(max-width:900px){.preview-tools{gap:8px;padding:8px 12px}.preview-tools>span{display:none}.preview-tools button{padding:6px 10px}.theme-switch button{padding:5px 8px}}
</style>
