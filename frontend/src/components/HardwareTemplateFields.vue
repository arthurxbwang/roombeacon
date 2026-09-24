<script setup lang="ts">
import type {HardwareSpec} from '@/api/configuration'
defineProps<{modelValue:HardwareSpec}>()
</script>
<template>
 <div class="v6-form-row"><label>厂家<input v-model="modelValue.manufacturer" maxlength="80" /></label><label>设备型号<input v-model="modelValue.model" maxlength="100" placeholder="通用屏幕可留空" /></label></div>
 <label>参考固件<input v-model="modelValue.firmware" maxlength="160" /></label>
 <div class="v6-form-row"><label>安装方向<select aria-label="安装方向" v-model="modelValue.portrait"><option :value="false">横屏安装</option><option :value="true">竖屏安装</option></select></label><label>灯控<select aria-label="灯控" v-model="modelValue.room_light"><option :value="false">无灯控</option><option :value="true">同步会议状态侧灯</option></select></label></div>
 <div class="v6-form-row"><label>面板物理宽度（像素）<input v-model.number="modelValue.width" type="number" min="0" max="8192" /></label><label>面板物理高度（像素）<input v-model.number="modelValue.height" type="number" min="0" max="8192" /></label></div>
 <p class="v6-muted">未知尺寸填写 0。软件布局会按设备实际网页视口校验，不改变屏幕分辨率。</p>
 <div v-if="modelValue.room_light" class="v6-wiring"><div class="v6-form-row"><label v-for="(name,key) in {red:'红灯',green:'绿灯',blue:'蓝灯'}" :key="key">{{name}} GPIO<select v-model.number="modelValue.pins[key]"><option v-for="pin in [147,148,154]" :key="pin" :value="pin">{{pin}}</option></select></label><label>点亮电平<select aria-label="点亮电平" v-model.number="modelValue.active_level"><option :value="0">低电平点亮 · 高电平熄灭</option><option :value="1">高电平点亮 · 低电平熄灭</option></select></label></div><p>三路通道必须不同。自定义接线组合需要支持该能力的 APK。</p></div>
 <label>安装说明<textarea v-model="modelValue.notes" rows="3" maxlength="2000" /></label>
</template>
