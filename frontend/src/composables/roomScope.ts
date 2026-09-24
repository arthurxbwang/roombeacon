import type {Room} from '@/api/management'
export interface RoomScope {region:string;path:string[]}
export const emptyScope=():RoomScope=>({region:'',path:[]})
export const roomPath=(room:Room)=>room.location.split(' / ').map(v=>v.trim()).filter(Boolean)
export const matchesScope=(room:Room|undefined,scope:RoomScope)=>{
 if(scope.region==='@unassigned')return !room
 if(!room)return !scope.region&&!scope.path.length
 return (!scope.region||room.region===scope.region)&&scope.path.every((v,i)=>roomPath(room)[i]===v)
}
export const normalized=(value:string)=>value.replace(/\s/g,'').toLocaleLowerCase()
export const roomMatches=(room:Room,query:string)=>normalized(`${room.region} ${room.location} ${room.name}`).includes(normalized(query))
