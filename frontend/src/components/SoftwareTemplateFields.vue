<script setup lang="ts">
import type {ManagedDevice} from '@/api/management'
import type {SoftwareSpec} from '@/api/configuration'
import BackgroundFields from './BackgroundFields.vue'
defineProps<{modelValue:SoftwareSpec;devices?:ManagedDevice[]}>()
const emit=defineEmits<{uploading:[value:boolean]}>()
</script>
<template>
 <h3>页面展示</h3>
 <label class="v6-check"><input type="checkbox" :checked="modelValue.show_meeting_titles!==false" @change="modelValue.show_meeting_titles=($event.target as HTMLInputElement).checked" />显示会议名称</label>
 <p class="v6-muted">关闭后隐藏当前、后续及历史会议名称；保留时间、组织者和签到。已部署设备的日程响应不携带会议名称。</p>
 <label>软件类型<select aria-label="软件类型" :value="modelValue.roombeacon_checkin!==false ? 'checkin' : 'display'" @change="modelValue.roombeacon_checkin=($event.target as HTMLSelectElement).value==='checkin';if(!modelValue.roombeacon_checkin){modelValue.rules.owner='official';modelValue.rules.mode='off'}"><option value="checkin">签到版</option><option value="display">未签到版 · 飞书官方签到</option></select></label>
 <label>门牌界面<select aria-label="门牌界面" :value="modelValue.display_version || 'v6'" @change="modelValue.display_version=($event.target as HTMLSelectElement).value as 'v6'|'v7'"><option value="v6">V6 现有门牌</option><option value="v7">V7 品牌签到门牌</option></select></label>
 <div class="v6-form-row"><label>页面布局<select aria-label="页面布局" v-model="modelValue.layout"><option value="standard">标准布局</option><option value="compact">紧凑布局</option></select></label><label>支持方向<select aria-label="支持方向" v-model="modelValue.orientation"><option value="any">横竖自适应</option><option value="landscape">仅横屏</option><option value="portrait">仅竖屏</option></select></label></div>
 <div class="v6-form-row"><label>最小网页宽度<input v-model.number="modelValue.min_width" type="number" min="0" max="8192" /></label><label>最小网页高度<input v-model.number="modelValue.min_height" type="number" min="0" max="8192" /></label></div>
 <p class="v6-muted">单位为网页像素；0 表示不限定。设备未上报尺寸时不会猜测兼容性。</p>
 <div class="v6-form-row"><label>日夜模式<select aria-label="日夜模式" v-model="modelValue.theme_mode"><option value="auto">跟随会议室所在地日出日落</option><option value="light">固定白天</option><option value="dark">固定夜间</option></select></label><label>页面语言<select aria-label="页面语言" v-model="modelValue.language"><option value="zh-CN">中文</option><option value="en">English</option></select></label></div>
 <BackgroundFields :model-value="modelValue" :devices="devices" @uploading="emit('uploading',$event)" />
 <p v-if="modelValue.roombeacon_checkin===false" class="v6-muted">保留飞书官方签到二维码；不启用 RoomBeacon 按钮签到与自动释放。</p>
 <template v-else><h3>会议室业务规则</h3>
 <div class="v6-form-row"><label>签到方案<select aria-label="签到方案" v-model="modelValue.rules.owner" @change="modelValue.rules.mode='off'"><option value="official">飞书官方签到</option><option value="v5">RoomBeacon 签到（V5）</option></select></label><label>运行模式<select aria-label="运行模式" v-model="modelValue.rules.mode" :disabled="modelValue.rules.owner==='official'"><option value="off">关闭</option><option value="observe">观察</option><option value="auto">自动释放 · 需房间核验</option></select></label></div>
 <template v-if="modelValue.rules.owner==='v5'"><button v-if="modelValue.display_version==='v7'" type="button" class="secondary" @click="modelValue.rules.early_minutes=5;modelValue.rules.grace_minutes=5;modelValue.rules.release_delay_seconds=0">使用会前 5 分钟／会后 5 分钟预设</button><div class="v6-form-row"><label>提前开放确认（分钟）<input v-model.number="modelValue.rules.early_minutes" type="number" min="1" max="30" /></label><label>开始后宽限（分钟）<input v-model.number="modelValue.rules.grace_minutes" type="number" min="1" max="30" /></label></div><label>待释放补确认（秒）<input v-model.number="modelValue.rules.release_delay_seconds" type="number" min="0" max="300" /></label><p class="v6-muted">补确认为 0 秒时，签到截止后立即进入核验，不再接受补签到。这里只保存规则参数。官方规则核对、释放验证和预约授权分别属于具体会议室与预约，不能随模板复制。</p></template></template>
</template>
