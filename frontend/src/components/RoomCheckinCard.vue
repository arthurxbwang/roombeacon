<script setup lang="ts">
import brand from '@/assets/room-checkin-brand.gif'
defineProps<{ qr: string; roomName: string; dark: boolean }>()
</script>

<template>
  <aside class="checkin-card" :class="{ 'dark-brand': dark }" aria-label="飞书扫码签到">
    <div class="brand-art" aria-hidden="true"><img :src="brand" alt="" /></div>
    <div class="checkin-content">
      <p class="checkin-eyebrow">THUNDERSOFT · CHECK IN</p>
      <div class="qr-frame"><img class="checkin-qr" :src="qr" :alt="`${roomName}会议室飞书签到二维码`" /></div>
      <strong>飞书扫码签到</strong>
      <p>打开飞书扫一扫</p>
      <small>签到结果请以飞书页面为准</small>
    </div>
  </aside>
</template>

<style scoped>
.checkin-card{min-width:0;overflow:hidden;border:0;background:transparent;box-shadow:none;align-self:center;position:relative}
.brand-art{position:relative;width:100%;aspect-ratio:750/355;overflow:hidden;background:transparent;opacity:.8;mix-blend-mode:multiply}
.brand-art>img{display:block;width:100%;height:auto;filter:saturate(.4);transform:translateY(-1%)}
.checkin-content{text-align:center;padding:14px 16px 18px;background:transparent}
.checkin-eyebrow{font-size:9px;letter-spacing:1.4px;color:var(--subtle);margin:0 0 12px}
.qr-frame{width:min(100%,200px);margin:0 auto 14px;background:transparent;padding:0;box-shadow:none;position:relative}
.checkin-qr{display:block;width:100%;height:auto;aspect-ratio:1;background:#fff;border-radius:0}
strong{display:block;font-size:clamp(18px,2cqw,26px);font-weight:600;color:var(--text)}
p:not(.checkin-eyebrow){font-size:13px;color:var(--muted);margin-top:6px}small{display:block;font-size:10px;color:var(--subtle);line-height:1.5;margin-top:10px}
.dark-brand .brand-art{mix-blend-mode:screen}.dark-brand .brand-art>img{filter:invert(1) hue-rotate(180deg) saturate(.4)}
/* Let the decoration rise above the content panel without taking space from the QR. */
@media(min-width:701px) and (min-height:701px) and (orientation:landscape){
  .checkin-card{overflow:visible}
  .brand-art{position:absolute;bottom:100%;left:0;z-index:3;pointer-events:none}
}
@media(prefers-reduced-motion:reduce){.brand-art>img{visibility:hidden}.brand-art:after{content:'ThunderSoft';position:absolute;inset:0;display:grid;place-items:center;font-size:22px;font-weight:700;font-style:italic;color:#8f4b52}}
</style>
