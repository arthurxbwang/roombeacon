<script setup lang="ts">
import {onUnmounted,ref} from 'vue'
import V6ConfigFields from './V6ConfigFields.vue'
import {defaultConfig,management,managementError,type ConfigTemplate,type DeviceConfig,type DeviceProfile} from '@/api/management'
const props=defineProps<{templates:ConfigTemplate[];profiles:DeviceProfile[];editable:boolean}>()
const emit=defineEmits<{changed:[]}>()
const abort=new AbortController()
const editing=ref(false), identity=ref(''), revision=ref(0), name=ref(''), config=ref<DeviceConfig>({...defaultConfig})
const busy=ref(false),error=ref(''),notice=ref('')
const profile=(c:DeviceConfig)=>props.profiles.find(p=>p.id===c.device_profile)
const polarity=(c:DeviceConfig)=>profile(c)?.active_level===0?'低电平点亮':profile(c)?.active_level===1?'高电平点亮':'自动识别 / 无灯控'
function edit(template?:ConfigTemplate,copy=false){
 identity.value=copy?'':template?.id||'';revision.value=template?.revision||0
 name.value=template?template.name+(copy?'（副本）':''):''
 config.value={...defaultConfig,device_profile:'bx68',...template?.config,reload:0}
 if(copy&&config.value.device_profile==='auto'){config.value.device_profile='generic';config.value.room_light=false}
 editing.value=true;error.value='';notice.value=''
}
async function save(){
 if(busy.value)return
 busy.value=true;error.value='';notice.value=''
 try{
  const body={name:name.value.trim(),config:config.value,...(identity.value?{expected_revision:revision.value}:{})}
  await management(identity.value?'PUT':'POST','/api/v6/admin/templates'+(identity.value?'/'+identity.value:''),abort.signal,body)
  editing.value=false;notice.value='模板已保存；选择设备下发后生效。';emit('changed')
 }catch(e){if(!abort.signal.aborted)error.value=managementError(e)}finally{busy.value=false}
}
onUnmounted(()=>abort.abort())
</script>
<template>
 <section class="v6-card v6-presets">
  <div class="v6-template-heading"><div><h2>硬件安装模板</h2><p class="v6-muted">同型号可分别创建横版、竖版模板。保存模板后，由设备选择并下发。</p></div><button v-if="editable" @click="edit()" :disabled="busy">新建模板</button></div>
  <p v-if="notice" class="v6-info" role="status">{{notice}}</p><p v-if="error" class="v6-error" role="alert">{{error}}</p>
  <div class="v6-template-grid"><article v-for="t in templates" :key="t.id" class="v6-template-item">
   <h3>{{t.name}}</h3><p class="v6-muted">{{profile(t.config)?.name||'旧模板 · 自动识别'}} · {{t.config.portrait?'竖屏':'横屏'}} · 第 {{t.revision}} 版</p>
   <p>{{t.config.theme_mode==='light'?'始终白天':'自动昼夜'}} · {{t.config.language==='en'?'English':'简体中文'}}</p><p>{{t.config.room_light?polarity(t.config):'灯控关闭'}} · {{t.config.version.toUpperCase()}} 页面</p>
   <div v-if="editable" class="v6-actions"><button class="secondary" @click="edit(t)" :disabled="busy">编辑</button><button class="secondary" @click="edit(t,true)" :disabled="busy">复制调整</button></div>
  </article></div>
  <p v-if="!templates.length&&!editing" class="v6-empty">暂无模板{{editable?'，点击新建模板开始配置。':'。'}}</p>
  <form v-if="editable&&editing" @submit.prevent="save"><fieldset :disabled="busy">
   <h3>{{identity?'编辑模板':'新建模板'}}</h3>
   <label>模板名称<input aria-label="模板名称" v-model="name" required maxlength="80" /></label>
   <V6ConfigFields v-model="config" :profiles="profiles" />
   <p class="v6-muted">页面版本只决定展示；官方签到、确认使用与释放规则在「会议室 → 业务方案」管理。</p>
   <div class="v6-actions"><button :disabled="busy||!name.trim()||!profiles.length">保存模板</button><button type="button" class="secondary" @click="editing=false">取消编辑</button></div>
  </fieldset></form>
 </section>
</template>
