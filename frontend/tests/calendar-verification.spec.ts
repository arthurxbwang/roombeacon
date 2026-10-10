import { expect, test } from '@playwright/test'
import { fixture } from './configuration.fixture'
import type { UsageState } from '../src/api/roomUsage'

function state(): UsageState {
  return { room_id:'omm_beijing',enabled:true,paused:false,release_enabled:true,auto_verify_enabled:true,
    server_time:new Date().toISOString(),valid_until:new Date(Date.now()+30000).toISOString(),
    policy:{owner:'v5',mode:'auto',early_minutes:5,grace_minutes:5,release_delay_seconds:0,native_policy_cleared:true,release_verified:true,revision:'r'},
    record:{id:'a'.repeat(64),state:'pending',reason:'monitoring',verified:false,deadline:new Date(Date.now()+300000).toISOString(),
      occurrence:{uid:'fixture',original_time:0,start_time:new Date().toISOString(),end_time:new Date(Date.now()+3600000).toISOString()},
      verification_error:'event_not_found',verification_http_status:404,verification_code:193001,
      verification_failures:2,verification_failed_at:new Date().toISOString()},
    can_confirm:true,can_end:false,target_id:'a'.repeat(64) }
}

for (const role of ['admin','viewer']) test(`后台${role}能区分开关与本场核验并看到恢复`, async ({page})=>{
  await fixture(page,role)
  await page.clock.install()
  const usage=state();let reads=0
  await page.route('**/api/room-control/usage/omm_beijing',route=>{
    reads++
    return route.fulfill({json:{data:{usage,audit:[],global_audit:[],writes_enabled:true,verification_issues:usage.record?.verification_error?[usage.record]:[]}}})
  })
  await page.goto('/control')
  await page.getByRole('button',{name:'会议室',exact:true}).click()
  await page.getByRole('button',{name:'规则与房间核验'}).first().click()
  const panel=page.getByRole('dialog',{name:'会议室规则'})
  await expect(panel.getByText('房间自动释放：已开启',{exact:true})).toBeVisible()
  await expect(panel.getByText('本次预约核验：未通过',{exact:true})).toBeVisible()
  await expect(panel.getByText('来源日历中未找到本场预约',{exact:true}).first()).toBeVisible()
  await expect(panel.getByText('HTTP 404 · 飞书 193001',{exact:true}).first()).toBeVisible()
  if(role==='viewer') await expect(panel.getByRole('button',{name:'仅登记当前实例'})).toHaveCount(0)
  else await panel.getByLabel('开始后宽限（分钟）').fill('8')
  usage.record!.verified=true;usage.record!.verification_error=null;usage.record!.verification_succeeded_at=new Date().toISOString()
  await page.clock.fastForward(11000)
  await expect(panel.getByText('本次预约核验：已通过',{exact:true})).toBeVisible()
  await expect(panel.getByRole('region',{name:'最近核验异常'})).toHaveCount(0)
  if(role==='admin')await expect(panel.getByLabel('开始后宽限（分钟）')).toHaveValue('8')
  await panel.getByRole('button',{name:'关闭',exact:true}).click()
  const finished=reads
  await page.clock.fastForward(31000)
  expect(reads).toBe(finished)
})

test('到期核验失败显示预约保留并保留诊断原因',async({page})=>{
  await fixture(page)
  const usage=state();usage.record!.state='blocked';usage.record!.reason='calendar_verification_failed'
  usage.record!.verified=true // A preflight failure invalidates an earlier successful qualification.
  usage.record!.verification_error='access_denied';usage.record!.verification_http_status=403;usage.record!.verification_code=191002
  await page.route('**/api/room-control/usage/omm_beijing',route=>route.fulfill({json:{data:{usage,audit:[],global_audit:[],writes_enabled:true}}}))
  await page.goto('/control');await page.getByRole('button',{name:'会议室',exact:true}).click()
  await page.getByRole('button',{name:'规则与房间核验'}).first().click()
  const panel=page.getByRole('dialog',{name:'会议室规则'})
  await expect(panel.getByText('本次预约已保留',{exact:true})).toBeVisible()
  await expect(panel.getByText('本次预约核验：未通过',{exact:true})).toBeVisible()
  await expect(panel.getByText('应用没有来源日历的读取权限',{exact:true})).toBeVisible()
  await expect(panel.getByText('核对该来源日历的应用访问权限。',{exact:true})).toBeVisible()
})
