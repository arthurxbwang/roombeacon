<script setup lang="ts">
import {computed} from 'vue'
import {type DeviceConfig, type DeviceProfile} from '@/api/management'
const props=defineProps<{modelValue:DeviceConfig;profiles:DeviceProfile[]}>()
const emit=defineEmits<{'update:modelValue':[value:DeviceConfig]}>()
const profile=computed(()=>props.profiles.find(p=>p.id===props.modelValue.device_profile))
function set<K extends keyof DeviceConfig>(key:K,value:DeviceConfig[K]) {
  const config={...props.modelValue,[key]:value}
  if(key==='device_profile'&&value==='generic')config.room_light=false
  emit('update:modelValue',config)
}
</script>
<template>
  <label>设备型号<select :value="modelValue.device_profile" @change="set('device_profile',($event.target as HTMLSelectElement).value)">
    <option v-if="modelValue.device_profile==='auto'" value="auto">旧配置 · 本机自动识别（请选择具体型号）</option>
    <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
  </select></label>
  <div v-if="profile?.pins" class="v6-wiring">
    <strong>{{ profile.active_level===0?'低电平点亮 · 高电平熄灭':'高电平点亮 · 低电平熄灭' }}</strong>
    <dl><div><dt>红灯 GPIO</dt><dd>{{ profile.pins.red }}</dd></div><div><dt>绿灯 GPIO</dt><dd>{{ profile.pins.green }}</dd></div><div><dt>蓝灯 GPIO</dt><dd>{{ profile.pins.blue }}</dd></div></dl>
    <p>系统型号：{{ profile.model }}<br />参考固件：{{ profile.firmware }}</p>
    <small>接线按已验证型号固定。空闲绿、使用中红、即将开始黄；未知或失联熄灯。</small>
  </div>
  <p v-else class="v6-muted">{{ modelValue.device_profile==='auto'?'旧配置沿用本机接线识别；新模板需选择具体型号。':'通用屏幕仅应用显示设置，不控制 GPIO。' }}</p>
  <div class="v6-form-row">
    <label>显示方案<select :value="modelValue.version" @change="set('version',($event.target as HTMLSelectElement).value as DeviceConfig['version'])"><option value="v6">V6 自动适配房间方案</option><option value="v4">V4 官方签到</option><option value="v5">V5 确认使用</option></select></label>
    <label>屏幕方向<select :value="String(modelValue.portrait)" @change="set('portrait',($event.target as HTMLSelectElement).value==='true')"><option value="false">横屏</option><option value="true">竖屏</option></select></label>
  </div>
  <label class="v6-check"><input type="checkbox" :checked="modelValue.theme_mode==='auto'" @change="set('theme_mode',($event.target as HTMLInputElement).checked?'auto':'light')" />自动切换白天／黑夜</label>
  <p class="v6-muted">{{ modelValue.theme_mode==='auto'?'跟随会议室所在城市的日出日落；城市时间不可用时保持白天。':'已关闭自动切换，始终使用白天模式。' }}</p>
  <label>门牌语言<select :value="modelValue.language" @change="set('language',($event.target as HTMLSelectElement).value as DeviceConfig['language'])"><option value="zh-CN">简体中文</option><option value="en">English</option></select></label>
  <label class="v6-check"><input type="checkbox" :checked="modelValue.room_light" :disabled="modelValue.device_profile==='generic'" @change="set('room_light',($event.target as HTMLInputElement).checked)" />同步侧边灯</label>
</template>
