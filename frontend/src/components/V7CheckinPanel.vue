<script setup lang="ts">
import { computed } from 'vue'
import brand from '@/assets/room-checkin-brand.gif'
import type { UsageState } from '@/api/roomUsage'
import { useDisplayText } from '@/utils/displayLanguage'

const props = defineProps<{ state: UsageState | null; now: number; fresh: boolean; available: boolean; canConfirm: boolean; pending: boolean; label: string }>()
const emit = defineEmits<{ confirm: [] }>()
const t = useDisplayText()
const ready = computed(() => props.available && props.fresh && props.state?.enabled && props.state.policy.owner === 'v5' && props.state.policy.mode !== 'off')
const record = computed(() => ready.value ? props.state?.record : null)
const protectedBooking = computed(() => record.value?.state === 'blocked')
const protection = computed(() => {
  if (!record.value || !['pending', 'waiting', 'blocked'].includes(record.value.state)) return ''
  if (protectedBooking.value) return ''
  if (props.state?.policy.mode === 'observe') return '观察模式 · 仅记录，不自动释放'
  if (props.state?.paused) return '自动释放已由管理员暂停'
  if (!record.value.verified || !props.state?.policy.native_policy_cleared || !props.state.policy.release_verified) return '正在核验预约，暂不自动释放'
  if (props.state?.release_enabled !== true) return '自动释放尚未启用'
  return ''
})
const countdown = computed(() => {
  const item = record.value
  if (!item || !props.canConfirm || !['pending', 'waiting', 'blocked'].includes(item.state)) return null
  const start = Date.parse(item.occurrence.start_time)
  const limit = Math.min(Date.parse(item.release_at || item.deadline), Date.parse(item.occurrence.end_time))
  const before = props.now < start
  const end = before ? Math.min(start, limit) : limit
  const seconds = Math.ceil((end - props.now) / 1000)
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  const duration = before ? props.state!.policy.early_minutes * 60 : item.state === 'waiting' ? props.state!.policy.release_delay_seconds : props.state!.policy.grace_minutes * 60
  return { phase: before ? 'before' : 'after',
    label: before ? '距离会议开始' : protectedBooking.value || protection.value ? '签到剩余时间' : item.state === 'waiting' ? '释放前补签到 · 剩余' : '未签到将释放 · 剩余',
    text: `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`,
    progress: Math.min(100, Math.max(0, seconds / Math.max(1, duration) * 100)) }
})
const status = computed(() => {
  if (record.value?.state === 'confirmed') return '已签到'
  if (record.value && ['pending', 'waiting', 'blocked'].includes(record.value.state) && props.now >= Date.parse(record.value.release_at || record.value.deadline)) return protectedBooking.value || protection.value ? '签到窗口已结束' : '正在同步释放状态'
  if (protection.value && record.value?.state === 'waiting') return '确认状态待同步'
  return props.label
})
</script>

<template>
  <section class="v7-checkin" :data-phase="countdown?.phase || 'status'" aria-label="V7 签到">
    <div class="v7-brand" aria-hidden="true"><img :src="brand" alt="" /></div>
    <div v-if="countdown" class="v7-countdown">
      <span class="v7-caption">{{ t(countdown.label) }}</span>
      <strong role="timer" aria-live="off" :aria-label="t(countdown.label)">{{ countdown.text }}</strong>
      <div class="v7-progress" aria-hidden="true"><span :style="{ width: `${countdown.progress}%` }" /></div>
    </div>
    <h4 v-else class="v7-status" role="status">{{ t(status) }}</h4>
    <p v-if="protection" class="v7-protection">{{ t(protection) }}</p>
    <button v-if="countdown" type="button" class="v7-button" :disabled="pending || !canConfirm" @click="emit('confirm')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
      <span>{{ t(pending ? '正在提交…' : '立即签到') }}</span>
    </button>
  </section>
</template>

<style scoped>
.v7-checkin{--checkin-tone:#aa790b;--checkin-bar:#ddb129;display:flex;flex-direction:column;align-items:center;width:min(100%,350px);gap:16px;margin:auto;color:var(--text);text-align:center}
.v7-checkin[data-phase=after]{--checkin-tone:#c26c27;--checkin-bar:#e4933c}
.v7-brand{position:relative;width:min(100%,240px);aspect-ratio:750/350;overflow:hidden;mix-blend-mode:multiply;flex-shrink:0}
.v7-brand img{display:block;width:100%;height:auto;transform:translateY(-1%);filter:saturate(.58)}
.v7-countdown{display:flex;flex-direction:column;gap:10px;width:100%}
.v7-caption{color:var(--checkin-tone);font-size:clamp(14px,1.35cqw,18px);line-height:1.4}
.v7-countdown strong{font-size:clamp(44px,4.9cqw,64px);font-weight:650;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:.02em}
[data-phase=after] .v7-countdown strong{color:var(--checkin-tone)}
.v7-progress{height:4px;background:var(--track);border-radius:3px;overflow:hidden;margin-top:4px}
.v7-progress span{display:block;height:100%;background:var(--checkin-bar)}
.v7-button{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;min-height:66px;border:0;border-radius:999px;padding:14px 18px;background:#cb1932;color:#fff;box-shadow:0 6px 18px #c9203120;font-size:clamp(22px,2.1cqw,28px);font-weight:650;line-height:1.2;cursor:pointer}
.v7-button svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
.v7-button:disabled{opacity:.65;cursor:wait;box-shadow:none}.v7-button:not(:disabled):active{background:#a71428}.v7-button:focus-visible{outline:3px solid var(--checkin-bar);outline-offset:4px}
.v7-status{font-size:clamp(18px,2cqw,26px);line-height:1.4}.v7-protection{font-size:14px;line-height:1.5;color:var(--muted)}
:global(.theme-dark .v7-brand){mix-blend-mode:screen}:global(.theme-dark .v7-brand img){filter:invert(1) hue-rotate(180deg) saturate(.4)}
:global(.theme-dark .v7-checkin){--checkin-tone:#edc967}:global(.theme-dark .v7-checkin[data-phase=after]){--checkin-tone:#f4ac68}
@media(max-height:700px) and (orientation:landscape){.v7-checkin{gap:10px}.v7-brand{max-width:180px}.v7-button{min-height:54px}.v7-countdown strong{font-size:44px}}
@media(prefers-reduced-motion:reduce){.v7-brand img{visibility:hidden}.v7-brand:after{content:'ThunderSoft';position:absolute;inset:0;display:grid;place-items:center;font-style:italic;font-weight:700;font-size:24px;color:#bc4c59}}
</style>
