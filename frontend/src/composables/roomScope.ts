import type {Room} from '@/api/management'
export interface RoomScope {region:string;path:string[]}
export const emptyScope=():RoomScope=>({region:'',path:[]})
export const locationNodes=(room:Room)=>room.location_nodes?.length ? room.location_nodes : room.location.split(' / ').map(v=>v.trim()).filter(Boolean).map((name,i)=>({id:`legacy:${i}:${name}`,name}))
export const regionKey=(room:Room)=>room.region_id || room.region
export const lowerNodes=(room:Room)=>{const nodes=locationNodes(room);const anchor=nodes.findIndex(n=>room.region_id ? n.id===room.region_id : n.name===room.region);return anchor>=0 ? nodes.slice(anchor+1) : nodes}
export const roomPath=(room:Room)=>lowerNodes(room).map(n=>n.id)
export const matchesScope=(room:Room|undefined,scope:RoomScope)=>{
 if(scope.region==='@unassigned')return !room
 if(!room)return !scope.region&&!scope.path.length
 return (!scope.region||regionKey(room)===scope.region)&&scope.path.every((v,i)=>roomPath(room)[i]===v)
}
export const normalized=(value:string)=>value.replace(/\s/g,'').toLocaleLowerCase()
export const roomMatches=(room:Room,query:string)=>normalized(`${room.region} ${room.location} ${room.name}`).includes(normalized(query))
