import {test,expect,type Locator,type Page} from '@playwright/test'
import {Buffer} from 'node:buffer'
import {createHash} from 'node:crypto'
import {fixture} from './configuration.fixture'

type ImageFile={name:string;mimeType:string;buffer:Buffer;width:number;height:number}
type Asset={id:string;mime:string;size:number;width:number;height:number}

async function imageFile(page:Page,mime='image/jpeg',width=160,height=90):Promise<ImageFile>{
 const data=await page.evaluate(async({mime,width,height})=>{
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height
  const context=canvas.getContext('2d')!,pixels=context.createImageData(width,height)
  for(let i=0;i<pixels.data.length;i+=4){pixels.data[i]=(i*13)%256;pixels.data[i+1]=(i*29)%256;pixels.data[i+2]=(i*47)%256;pixels.data[i+3]=255}
  context.putImageData(pixels,0,0)
  const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('图片生成失败')),mime,.9))
  return await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob)})
 },{mime,width,height})
 return {name:'background.'+({'image/png':'png','image/jpeg':'jpeg','image/webp':'webp'}[mime]||'bin'),mimeType:mime,buffer:Buffer.from(data,'base64'),width,height}
}

async function openEditor(page:Page){
 await page.goto('/control');await page.getByRole('button',{name:'软件模板',exact:true}).click()
 await page.getByRole('button',{name:'新建软件模板',exact:true}).click()
 const editor=page.locator('.v6-template-editor:visible');await editor.getByLabel('模板名称').fill('背景回归模板')
 return editor
}

async function assetMock(page:Page){
 const files=new Map<string,ImageFile>(),uploads:{body:{name:string;data:string};bytes:Buffer;asset:Asset}[]=[]
 const state={files,uploads,fail:false}
 await page.route(/\/api\/v6\/admin\/assets(?:\/[^/?]+)?(?:\?.*)?$/,async route=>{
  const path=new URL(route.request().url()).pathname
  if(route.request().method()==='GET'){
   const id=path.split('/').at(-1)!,file=files.get(id)
   return file?route.fulfill({json:{code:0,data:{id,mime:file.mimeType,size:file.buffer.length,width:file.width,height:file.height}}}):route.fulfill({status:404,json:{code:404}})
  }
  expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
  const body=route.request().postDataJSON(),bytes=Buffer.from(body.data,'base64'),id=createHash('sha256').update(bytes).digest('hex')
  const file=[...files.values()].find(file=>file.name===body.name)!
  const asset={id,mime:file?.mimeType||'image/png',size:bytes.length,width:file?.width||160,height:file?.height||90}
  uploads.push({body,bytes,asset})
  if(state.fail)return route.fulfill({status:503,json:{code:503}})
  if(file)files.set(id,file)
  return route.fulfill({json:{code:0,data:asset}})
 })
 await page.route('**/api/v6/assets/*',route=>{
  const file=files.get(new URL(route.request().url()).pathname.split('/').at(-1)!)
  return file?route.fulfill({contentType:file.mimeType,body:file.buffer}):route.fulfill({status:404})
 })
 return state
}

function register(state:Awaited<ReturnType<typeof assetMock>>,file:ImageFile){state.files.set(file.name,file)}
async function upload(editor:Locator,file:ImageFile,index=0){await editor.locator('input[type=file]').nth(index).setInputFiles({name:file.name,mimeType:file.mimeType,buffer:file.buffer})}
function jpegWithSize(source:Buffer,size:number){
 const segments:Buffer[]=[];let remaining=size-source.length
 while(remaining){
  let length=Math.min(65_537,remaining);if(remaining-length>0&&remaining-length<4)length-=4
  const segment=Buffer.alloc(length);segment[0]=0xff;segment[1]=0xfe;segment.writeUInt16BE(length-2,2);segments.push(segment);remaining-=length
 }
 return Buffer.concat([source.subarray(0,2),...segments,source.subarray(2)])
}

for(const [mime,label] of [['image/png','PNG'],['image/jpeg','JPEG'],['image/webp','WebP']]){
 test(`${label} 背景上传保持原始字节并显示格式、实际大小与像素`,async({page})=>{
  await fixture(page);const state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page,mime);register(state,file)
  await upload(editor,file);await expect.poll(()=>state.uploads.length).toBe(1)
  expect(state.uploads[0].body.name).toBe(file.name);expect(Buffer.compare(state.uploads[0].bytes,file.buffer)).toBe(0)
  const metadata=editor.locator('.v6-asset-info');await expect(metadata).toContainText(label);await expect(metadata).toContainText((file.buffer.length/1_000_000).toFixed(2)+' MB');await expect(metadata).toContainText(file.buffer.length+' 字节');await expect(metadata).toContainText('160 × 90 像素')
  await expect(editor.locator('.v6-asset-thumbnail')).toHaveAttribute('src','/api/v6/assets/'+state.uploads[0].asset.id)
  expect((await editor.locator('input[type=file]').nth(1).boundingBox())!.height).toBeLessThan(60)
 })
}

test('原图恰好 3 MB 可上传，大小按原始字节校验',async({page})=>{
 await fixture(page);const state=await assetMock(page),editor=await openEditor(page),source=await imageFile(page)
 const file={...source,buffer:jpegWithSize(source.buffer,3_000_000)};register(state,file)
 await upload(editor,file);await expect.poll(()=>state.uploads.length).toBe(1);expect(Buffer.compare(state.uploads[0].bytes,file.buffer)).toBe(0)
 await expect(editor.locator('.v6-asset-info')).toContainText('3.00 MB');await expect(editor.getByRole('alert')).toHaveCount(0)
})

test('超过 3 MB 时展示实际大小且不发送上传请求',async({page})=>{
 await fixture(page);const state=await assetMock(page),editor=await openEditor(page),file={name:'oversized.jpeg',mimeType:'image/jpeg',buffer:Buffer.alloc(3_100_000),width:160,height:90}
 await upload(editor,file);await expect(editor.getByRole('alert')).toContainText('3.10 MB');await expect(editor.getByRole('alert')).toContainText('3 MB');expect(state.uploads).toHaveLength(0)
})

test('损坏图片或超过 4096 像素时拒绝上传并保留已有背景',async({page})=>{
 const configuration=await fixture(page),state=await assetMock(page),editor=await openEditor(page),original=await imageFile(page);register(state,original)
 await upload(editor,original);await expect(editor.locator('.v6-asset-thumbnail')).toBeVisible();const oldId=state.uploads[0].asset.id
 await upload(editor,{...original,name:'broken.jpeg',buffer:Buffer.from('invalid JPEG')});await expect(editor.getByRole('alert')).toBeVisible();expect(state.uploads).toHaveLength(1)
 const wide=await imageFile(page,'image/png',4097,1);await upload(editor,wide);await expect(editor.getByRole('alert')).toContainText('4096');expect(state.uploads).toHaveLength(1)
 await expect(editor.locator('.v6-asset-thumbnail')).toHaveAttribute('src','/api/v6/assets/'+oldId)
 await editor.getByRole('button',{name:'保存草稿',exact:true}).click();expect(configuration.writes.at(-1)?.body.spec.background_day).toBe(oldId)
})

test('后台上传失败保留原背景及原图信息，草稿仍可保存',async({page})=>{
 const configuration=await fixture(page),state=await assetMock(page),editor=await openEditor(page),original=await imageFile(page,'image/jpeg');register(state,original)
 await upload(editor,original);await expect(editor.locator('.v6-asset-info')).toContainText('JPEG');const oldId=state.uploads[0].asset.id
 const replacement=await imageFile(page,'image/webp');register(state,replacement);state.fail=true;await upload(editor,replacement)
 await expect(editor.getByRole('alert')).toContainText('服务暂不可用');await expect(editor.locator('.v6-asset-thumbnail')).toHaveAttribute('src','/api/v6/assets/'+oldId);await expect(editor.locator('.v6-asset-info')).toContainText('JPEG')
 await editor.getByRole('button',{name:'保存草稿',exact:true}).click();expect(configuration.writes.at(-1)?.body.spec.background_day).toBe(oldId)
})

test('重新编辑已保存的背景可读取原图格式、大小和像素',async({page})=>{
 const configuration=await fixture(page),state=await assetMock(page),file=await imageFile(page,'image/webp'),id=createHash('sha256').update(file.buffer).digest('hex')
 state.files.set(id,file);Object.assign(configuration.catalog.find(template=>template.id==='sw')!.spec,{background_day:id})
 await page.goto('/control');await page.getByRole('button',{name:'软件模板',exact:true}).click();await page.locator('.v6-template-item:visible').getByRole('button',{name:'编辑',exact:true}).click()
 const metadata=page.locator('.v6-template-editor:visible .v6-asset-info');await expect(metadata).toContainText('WebP');await expect(metadata).toContainText(file.buffer.length+' 字节');await expect(metadata).toContainText('160 × 90 像素');expect(state.uploads).toHaveLength(0)
})

test('取消编辑中止未完成的文件读取，后续编辑可重新上传',async({page})=>{
 await fixture(page);const state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page)
 await page.evaluate(()=>{
  const read=FileReader.prototype.readAsDataURL,abort=FileReader.prototype.abort
  ;(window as any).backgroundReaders={started:0,aborted:0}
  FileReader.prototype.readAsDataURL=function(blob){if((blob as File).name!=='delayed.jpeg')return read.call(this,blob);(window as any).backgroundReaders.started++;Object.defineProperty(this,'readyState',{configurable:true,value:1})}
  FileReader.prototype.abort=function(){(window as any).backgroundReaders.aborted++;abort.call(this);this.dispatchEvent(new Event('abort'))}
 })
 await upload(editor,{...file,name:'delayed.jpeg'});await expect.poll(()=>page.evaluate(()=>(window as any).backgroundReaders.started)).toBe(1)
 await editor.getByRole('button',{name:'取消编辑',exact:true}).click();await expect.poll(()=>page.evaluate(()=>(window as any).backgroundReaders.aborted)).toBe(1);expect(state.uploads).toHaveLength(0)
 await page.getByRole('button',{name:'新建软件模板',exact:true}).click();register(state,file);await upload(page.locator('.v6-template-editor:visible'),file);await expect.poll(()=>state.uploads.length).toBe(1)
})

test('取消编辑中止进行中的上传，不让旧请求覆盖后续编辑',async({page})=>{
 await fixture(page);const state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page);register(state,file)
 let release!:()=>void,started=false,failed=false;const pending=new Promise<void>(resolve=>{release=resolve})
 page.on('requestfailed',request=>{if(new URL(request.url()).pathname==='/api/v6/admin/assets')failed=true})
 await page.route('**/api/v6/admin/assets',async route=>{started=true;await pending;await route.fulfill({json:{code:0,data:{id:'e'.repeat(64),mime:file.mimeType,size:file.buffer.length,width:160,height:90}}})})
 await upload(editor,file);await expect.poll(()=>started).toBe(true);await editor.getByRole('button',{name:'取消编辑',exact:true}).click();await expect.poll(()=>failed).toBe(true)
 release();await page.unroute('**/api/v6/admin/assets');await page.getByRole('button',{name:'新建软件模板',exact:true}).click()
 await upload(page.locator('.v6-template-editor:visible'),file);await expect.poll(()=>state.uploads.length).toBe(1);await expect(page.locator('.v6-asset-thumbnail')).toHaveAttribute('src','/api/v6/assets/'+state.uploads[0].asset.id)
})

test('背景上传完成前禁止保存草稿，完成后保存新背景 ID',async({page})=>{
 const configuration=await fixture(page),state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page);register(state,file)
 let release!:()=>void,started=false;const pending=new Promise<void>(resolve=>{release=resolve})
 await page.route('**/api/v6/admin/assets',async route=>{started=true;await pending;await route.fallback()})
 await upload(editor,file);await expect.poll(()=>started).toBe(true)
 try{await expect(editor.getByRole('button',{name:'保存草稿',exact:true})).toBeDisabled();await expect(editor.getByRole('button',{name:'取消编辑',exact:true})).toBeEnabled();expect(configuration.writes).toHaveLength(0)}finally{release()}
 await expect.poll(()=>state.uploads.length).toBe(1);await expect(editor.getByRole('button',{name:'保存草稿',exact:true})).toBeEnabled()
 await editor.getByRole('button',{name:'保存草稿',exact:true}).click();expect(configuration.writes.at(-1)?.body.spec.background_day).toBe(state.uploads[0].asset.id)
})

test('切换编辑其他软件模板时取消旧上传，旧背景不会写入新草稿',async({page})=>{
 const configuration=await fixture(page),other=structuredClone(configuration.catalog.find(template=>template.id==='sw')!);Object.assign(other,{id:'sw2',name:'第二软件'});configuration.catalog.push(other)
 const state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page);register(state,file)
 let release!:()=>void,started=false,failed=false;const pending=new Promise<void>(resolve=>{release=resolve})
 page.on('requestfailed',request=>{if(new URL(request.url()).pathname==='/api/v6/admin/assets')failed=true})
 await page.route('**/api/v6/admin/assets',async route=>{started=true;await pending;await route.fulfill({json:{code:0,data:{id:'e'.repeat(64),mime:file.mimeType,size:file.buffer.length,width:160,height:90}}})})
 await upload(editor,file);await expect.poll(()=>started).toBe(true)
 try{
  await page.locator('.v6-template-item:visible').filter({has:page.getByRole('heading',{name:'第二软件',exact:true})}).getByRole('button',{name:'编辑',exact:true}).click()
  await expect.poll(()=>failed).toBe(true);await expect(editor.getByLabel('模板名称')).toHaveValue('第二软件');await expect(editor.locator('.v6-asset-thumbnail')).toHaveCount(0)
 }finally{release()}
 await expect(editor.getByRole('button',{name:'保存草稿',exact:true})).toBeEnabled();await editor.getByRole('button',{name:'保存草稿',exact:true}).click()
 expect(configuration.writes.at(-1)?.path).toBe('/api/v6/admin/catalog/sw2');expect(configuration.writes.at(-1)?.body.spec.background_day).toBe('')
})

test('缩略图按目标屏幕比例居中裁切，完整显示可切换并保留原图',async({page})=>{
 const configuration=await fixture(page);Object.assign(configuration.devices[1].metadata,{screen:{viewport_width:1000,viewport_height:600}})
 const state=await assetMock(page),editor=await openEditor(page),file=await imageFile(page);register(state,file);await upload(editor,file)
 const thumbnail=editor.locator('.v6-asset-thumbnail');await expect(thumbnail).toBeVisible();await expect(thumbnail).toHaveCSS('object-fit','cover');await expect(thumbnail).toHaveCSS('object-position','50% 50%')
 await editor.getByLabel('背景预览比例').selectOption('9/16');const box=await thumbnail.boundingBox();expect(box!.width/box!.height).toBeCloseTo(9/16,1)
 const deviceOption=editor.getByLabel('背景预览比例').locator('option').filter({hasText:/DEF567.*1000.*600/});await expect(deviceOption).toHaveCount(1)
 await editor.getByLabel('背景预览比例').selectOption((await deviceOption.getAttribute('value'))!);const deviceBox=await thumbnail.boundingBox();expect(deviceBox!.width/deviceBox!.height).toBeCloseTo(1000/600,1)
 await editor.getByLabel('背景适配',{exact:true}).selectOption('contain');await expect(thumbnail).toHaveCSS('object-fit','contain');await expect(thumbnail).toHaveAttribute('src','/api/v6/assets/'+state.uploads[0].asset.id)
 expect(state.uploads).toHaveLength(1);expect(Buffer.compare(state.uploads[0].bytes,file.buffer)).toBe(0)
})

for(const version of ['v6','v7'])for(const fit of ['cover','contain']){
 test(`${version} ${fit} 背景随横竖屏保持比例且在内容下方`,async({page})=>{
  await page.setViewportSize({width:1280,height:720});const file=await imageFile(page),id='a'.repeat(64)
  await page.route('**/api/v6/assets/*',route=>route.fulfill({contentType:file.mimeType,body:file.buffer}))
  await page.route('**/api/meeting-rooms/display',route=>{const now=Date.now();return route.fulfill({json:{data:{room:{room_id:'omm_fixture',name:'模拟背景会议室',capacity:8,enabled:true},events:[],synced_at:new Date(now).toISOString(),server_time:new Date(now).toISOString(),valid_until:new Date(now+60000).toISOString(),usage_owner:'official',titles_available:true,display_preferences:{display_version:version,theme_mode:'light',language:'zh-CN',background_day:id,background_fit:fit}}}})})
  await page.goto('/?version='+version+'&managed=1');const background=page.locator('.template-background'),door=page.locator('main.door')
  await expect(background).toHaveCSS('object-fit',fit);await expect(background).toHaveCSS('object-position','50% 50%');await expect.poll(()=>background.evaluate((node:HTMLImageElement)=>node.naturalWidth)).toBe(160)
  for(const viewport of [{width:1280,height:720},{width:720,height:1280}]){
   await page.setViewportSize(viewport);const bounds=await background.boundingBox(),main=await door.boundingBox();expect(bounds!.width).toBeCloseTo(main!.width,0);expect(bounds!.height).toBeCloseTo(main!.height,0)
   const layers=await door.evaluate(node=>({background:getComputedStyle(node.querySelector('.template-background')!).zIndex,header:getComputedStyle(node.querySelector('.door-header')!).zIndex,content:getComputedStyle(node.querySelector('.content')!).zIndex}))
   expect(Number(layers.background)).toBeLessThan(layers.header==='auto'?0:Number(layers.header));expect(Number(layers.background)).toBeLessThan(layers.content==='auto'?0:Number(layers.content))
   await expect(page.getByText('模拟背景会议室',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
 })
}
