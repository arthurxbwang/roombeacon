<script setup lang="ts">
import {computed} from 'vue'
import type {Room} from '@/api/management'
import {roomPath, type RoomScope} from '@/composables/roomScope'
const props=defineProps<{rooms:Room[];modelValue:RoomScope;unassigned?:boolean}>()
const emit=defineEmits<{'update:modelValue':[value:RoomScope]}>()
const sorted=(values:string[])=>[...new Set(values)].sort((a,b)=>a.localeCompare(b,'zh-CN'))
const regions=computed(()=>sorted(props.rooms.map(r=>r.region)))
const levels=computed(()=>{
 const result:string[][]=[]
 let paths=props.rooms.filter(r=>!props.modelValue.region||r.region===props.modelValue.region).map(roomPath)
 for(let i=0; ;i++){
  const values=sorted(paths.map(p=>p[i]).filter((v):v is string=>!!v))
  if(!values.length)break
  result.push(values)
  const selected=props.modelValue.path[i]
  if(!selected)break
  paths=paths.filter(p=>p[i]===selected)
 }
 return result
})
function region(event:Event){emit('update:modelValue',{region:(event.target as HTMLSelectElement).value,path:[]})}
function level(index:number,event:Event){
 const value=(event.target as HTMLSelectElement).value
 emit('update:modelValue',{region:props.modelValue.region,path:[...props.modelValue.path.slice(0,index),...(value?[value]:[])]})
}
</script>
<template>
 <div class="v6-location-filters">
  <label>地区 / 园区<select aria-label="地区 / 园区" :value="modelValue.region" @change="region"><option value="">全部地区</option><option v-if="unassigned" value="@unassigned">未分配会议室</option><option v-for="r in regions" :key="r" :value="r">{{r}}</option></select></label>
  <label v-for="(options,i) in levels" :key="i">位置第 {{i+1}} 级<select :aria-label="`位置第 ${i+1} 级`" :value="modelValue.path[i]||''" @change="level(i,$event)"><option value="">全部</option><option v-for="item in options" :key="item" :value="item">{{item}}</option></select></label>
 </div>
</template>
