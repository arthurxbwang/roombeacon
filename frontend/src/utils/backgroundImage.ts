export interface BackgroundAsset {id:string;name?:string;mime:string;size:number;width:number;height:number}
export const backgroundLimit=3_000_000
export const imageSize=(size:number)=>`${(size/1_000_000).toFixed(2)} MB（${size} 字节）`
export const imageFormat=(mime:string)=>({'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WebP'}[mime]||'图片')

export async function readBackground(file:File,signal:AbortSignal){
 if(file.size>backgroundLimit)throw new Error(`图片为 ${imageSize(file.size)}，超过 3 MB 上限，请缩小尺寸后重试`)
 if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('仅支持 PNG、JPEG 或 WebP 图片')
 let bitmap:ImageBitmap
 try{bitmap=await createImageBitmap(file)}catch{throw new Error('图片损坏或无法读取，请重新选择完整图片')}
 try{if(bitmap.width>4096||bitmap.height>4096)throw new Error('图片宽高不能超过 4096 像素')}
 finally{bitmap.close()}
 return new Promise<string>((resolve,reject)=>{
  const reader=new FileReader()
  const cleanup=()=>{signal.removeEventListener('abort',cancel);reader.onload=reader.onerror=reader.onabort=null}
  const cancel=()=>{reader.abort();cleanup();reject(new DOMException('已取消图片读取','AbortError'))}
  reader.onload=()=>{const data=String(reader.result).split(',')[1];cleanup();resolve(data)}
  reader.onerror=()=>{cleanup();reject(new Error('图片读取失败，请重新选择'))}
  reader.onabort=()=>{cleanup();reject(new DOMException('已取消图片读取','AbortError'))}
  if(signal.aborted){cancel();return}
  signal.addEventListener('abort',cancel,{once:true})
  reader.readAsDataURL(file)
 })
}
