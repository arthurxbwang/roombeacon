<script setup lang="ts">
import {computed} from 'vue'
import type {ManagedDevice} from '@/api/management'
import {deviceHealth} from '@/utils/deviceHealth'
const props=defineProps<{device?:ManagedDevice;compact?:boolean}>()
const health=computed(()=>deviceHealth(props.device))
</script>
<template>
 <div class="v6-device-health" :class="{compact}" data-testid="device-health">
  <template v-if="compact"><span :class="{'v6-error':health.pageProblem}">{{health.page}}</span><small :class="{'v6-error':health.lightProblem}">{{health.light}}</small></template>
  <dl v-else class="v6-facts">
   <div><dt>页面运行</dt><dd :class="{'v6-error':health.pageProblem}">{{health.page}}<small v-if="health.error">{{health.error}}</small></dd></div>
   <div><dt>灯控健康</dt><dd :class="{'v6-error':health.lightProblem}">{{health.light}}</dd></div>
   <div><dt>实际 H5 版本</dt><dd>{{health.release}}</dd></div><div><dt>WebView 版本</dt><dd>{{health.webview}}</dd></div>
   <div><dt>最近页面回执</dt><dd>{{health.age}}</dd></div>
  </dl>
 </div>
</template>
<style scoped>
.v6-device-health{margin:18px 0}.v6-device-health.compact{margin:0;font-size:12px;min-width:130px}.v6-device-health .v6-error{margin:0}.v6-device-health small{display:block;font-size:11px;line-height:1.6;margin-top:5px;color:#718096}.v6-device-health small.v6-error{color:#c34747}.v6-device-health dl{margin:0}
</style>
