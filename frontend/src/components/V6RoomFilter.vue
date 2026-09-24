<script setup lang="ts">
import {computed} from 'vue'
import type {Room} from '@/api/management'
import {lowerNodes,regionKey,type RoomScope} from '@/composables/roomScope'
const props=defineProps<{rooms:Room[];modelValue:RoomScope;unassigned?:boolean}>()
const emit=defineEmits<{'update:modelValue':[value:RoomScope]}>()
const unique=(nodes:{id:string;name:string}[])=>[...new Map(nodes.map(n=>[n.id,n])).values()].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'))
const regions=computed(()=>unique(props.rooms.map(r=>({id:regionKey(r),name:r.region}))))
const levels=computed(()=>{
 if(!props.modelValue.region||props.modelValue.region==='@unassigned')return []
 const result:{id:string;name:string}[][]=[]
 let paths=props.rooms.filter(r=>regionKey(r)===props.modelValue.region).map(lowerNodes)
 for(let i=0; ;i++){
  const values=unique(paths.flatMap(p=>p[i]?[p[i]]:[]))
  if(!values.length)break
  result.push(values)
  const selected=props.modelValue.path[i]
  if(!selected)break
  paths=paths.filter(p=>p[i]?.id===selected)
 }
 return result
})
function region(event:Event){emit('update:modelValue',{region:(event.target as HTMLSelectElement).value,path:[]})}
const levelLabel=(i:number,options:{name:string}[])=>options.every(n=>/^(\d+F|B\d+|\d+层|地下.*层)$/i.test(n.name))?'楼层':i===0?'园区 / 楼栋':`下级位置 ${i+1}`
function level(index:number,event:Event){
 const value=(event.target as HTMLSelectElement).value
 emit('update:modelValue',{region:props.modelValue.region,path:[...props.modelValue.path.slice(0,index),...(value?[value]:[])]})
}
</script>
<template>
 <div class="v6-location-filters">
  <label>地区<select aria-label="地区" :value="modelValue.region" @change="region"><option value="">全部地区</option><option v-if="unassigned" value="@unassigned">未分配会议室</option><option v-for="r in regions" :key="r.id" :value="r.id">{{r.name}}</option></select></label>
  <label v-for="(options,i) in levels" :key="i">{{levelLabel(i,options)}}<select :aria-label="levelLabel(i,options)" :value="modelValue.path[i]||''" @change="level(i,$event)"><option value="">全部</option><option v-for="item in options" :key="item.id" :value="item.id">{{item.name}}</option></select></label>
 </div>
</template>
