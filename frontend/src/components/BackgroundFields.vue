<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {management,managementError,type ManagedDevice} from '@/api/management'
import type {SoftwareSpec} from '@/api/configuration'
import {imageFormat,imageSize,readBackground,type BackgroundAsset} from '@/utils/backgroundImage'
const props=defineProps<{modelValue:SoftwareSpec;devices?:ManagedDevice[]}>()
const emit=defineEmits<{uploading:[value:boolean]}>()
const titles={background_day:'白天背景',background_night:'夜间背景'} as const
const abort=new AbortController(),error=ref(''),uploading=ref(false),ratio=ref('16/9')
const assets=ref<Record<string,BackgroundAsset>>({}),loading=new Set<string>()
const deviceRatios=computed(()=>props.devices?.flatMap(device=>{
 const screen=device.metadata.screen,w=screen?.viewport_width,h=screen?.viewport_height
 return w&&h?[{code:device.code,value:`${w}/${h}`,label:`设备 ${device.code} · ${w} × ${h}`}]:[]
})||[])
watch(()=>[props.modelValue.background_day,props.modelValue.background_night],ids=>{
 for(const id of new Set(ids))if(id&&!assets.value[id]&&!loading.has(id)){
  loading.add(id)
  management<BackgroundAsset>('GET','/api/v6/admin/assets/'+id,abort.signal)
   .then(asset=>{if(!abort.signal.aborted)assets.value[id]=asset})
   .catch(e=>{if(!abort.signal.aborted)error.value='背景信息读取失败：'+managementError(e)})
   .finally(()=>loading.delete(id))
 }
},{immediate:true})
async function upload(event:Event,key:keyof typeof titles){
 const input=event.target as HTMLInputElement,file=input.files?.[0];if(!file||uploading.value)return
 error.value='';uploading.value=true;emit('uploading',true)
 try{
  const data=await readBackground(file,abort.signal)
  const asset=await management<BackgroundAsset>('POST','/api/v6/admin/assets',abort.signal,{name:file.name,data})
  if(!abort.signal.aborted){assets.value[asset.id]={...asset,name:file.name};props.modelValue[key]=asset.id}
 }catch(e){if(!abort.signal.aborted)error.value=e instanceof Error&&!('isAxiosError' in e)?e.message:managementError(e)}
 finally{uploading.value=false;input.value='';if(!abort.signal.aborted)emit('uploading',false)}
}
onUnmounted(()=>{abort.abort();emit('uploading',false)})
</script>
<template>
 <p class="v6-muted">支持 PNG、JPEG、WebP，单张不超过 3 MB，宽高均不超过 4096 像素；保留原图格式与画质。</p>
 <label>背景预览比例<select aria-label="背景预览比例" v-model="ratio"><option value="16/9">横屏 16:9 · 1280 × 720</option><option value="16/10">横屏 16:10 · 1280 × 800</option><option value="9/16">竖屏 9:16</option><option value="10/16">竖屏 10:16</option><option v-for="device in deviceRatios" :key="device.code" :value="device.value">{{device.label}}</option></select></label>
 <div class="v6-form-row"><label v-for="(title,key) in titles" :key="key">{{title}}
  <input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploading" @change="upload($event,key)" />
  <template v-if="modelValue[key]">
   <img :src="'/api/v6/assets/'+modelValue[key]" class="v6-asset-thumbnail" :style="{aspectRatio:ratio,objectFit:modelValue.background_fit}" :alt="title+'裁切预览'" />
   <span v-if="assets[modelValue[key]]?.name" class="v6-asset-name">{{assets[modelValue[key]].name}}</span>
   <span v-if="assets[modelValue[key]]" class="v6-asset-info">{{imageFormat(assets[modelValue[key]].mime)}} · {{imageSize(assets[modelValue[key]].size)}} · {{assets[modelValue[key]].width}} × {{assets[modelValue[key]].height}} 像素</span>
   <button type="button" class="secondary" @click="modelValue[key]=''">恢复默认背景</button>
  </template>
 </label></div>
 <label>背景适配<select aria-label="背景适配" v-model="modelValue.background_fit"><option value="cover">等比铺满 · 居中裁切</option><option value="contain">完整显示 · 等比留白</option></select></label>
 <p class="v6-muted">门牌按实际屏幕比例等比显示，不拉伸变形。铺满时居中裁掉超出部分；完整显示时保留整张图。预览比例仅用于检查背景，不改变原图或设备配置。</p>
 <p v-if="uploading" role="status">正在保存图片…</p><p v-if="error" class="v6-error" role="alert">{{error}}</p>
</template>
<style scoped>
.v6-form-row{align-items:start}
.v6-asset-thumbnail{display:block;width:240px;max-width:100%;height:auto;max-height:none;object-position:center;background:#e9edf4;box-sizing:border-box}
.v6-asset-info,.v6-asset-name{font-size:12px;line-height:1.6;overflow-wrap:anywhere;color:#52627a}
</style>
