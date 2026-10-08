export interface ApkManifest {
 package:string;version_code:number;version_name:string;sha256:string;certificate_sha256:string;size:number;models:string[]
}
export interface InstallExecutor {id:string;name:string;revoked:number;expires:number;last_seen:number}
export interface InstallRelease {id:string;manifest:ApkManifest;created_at:number}
export interface InstallJob {
 id:string;batch_id:string;executor_id:string;release_id:string;ip:string;port:number;serial:string;state:string;revision:number
 lease_until:number;result:string;error:string;device_id:string;device_code:string;device_ready:boolean;acceptance_current:boolean
 acceptance:Record<string,unknown>;created_at:number
}
export interface InstallOverview {executors:InstallExecutor[];releases:InstallRelease[];jobs:InstallJob[]}
export const installationBase='/api/v6/admin/installation'
export function installationError(error:unknown){
 if(axios.isAxiosError(error)&&[409,422].includes(error.response?.status||0)&&typeof error.response?.data?.message==='string')return error.response.data.message
 return managementError(error)
}
export const installState=(state:string)=>({queued:'等待助手领取',running:'安装执行中',uncertain:'结果待核实',failed:'安装失败',installed:'安装完成，等待关联',associated:'已关联，等待配置与验收',accepted:'已记录现场验收',cancelled:'任务已结束'}[state]||state)
export const installError=(code:string)=>({apk_invalid:'APK 校验未通过',connection_failed:'ADB 连接失败或未授权',identity_mismatch:'序列号不一致',model_mismatch:'型号不适用',existing_apk:'已有其他 APK，请单独处理迁移',install_failed:'安装失败',launch_failed:'启动未成功',verification_failed:'安装后核验未通过',local_failure:'助手工具执行失败'}[code]||code)
import axios from 'axios'
import {managementError} from './management'
