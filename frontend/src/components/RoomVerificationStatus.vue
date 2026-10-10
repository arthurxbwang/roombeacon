<script setup lang="ts">
import type { UsageRecord, UsageState } from '@/api/roomUsage'
defineProps<{ usage: UsageState; issues: UsageRecord[] }>()
const reasons: Record<string, [string, string]> = {
  source_unresolved: ['未找到可核验的预约来源', '核对预约组织者和来源日历的接入范围。'],
  source_stale: ['预约来源证据待同步', '等待完整日程同步；持续出现时检查采集状态。'],
  source_changed: ['预约来源已变化', '核对改期或组织者变更，本次预约保持保留。'],
  source_conflict: ['预约来源存在冲突', '核对日程身份及权威来源，处理后再验收新的预约。'],
  event_not_found: ['来源日历中未找到本场预约', '核对实际来源日历及日程是否已取消或改期。'],
  event_changed: ['日程已变更或取消', '等待日程同步并核对最新预约。'],
  access_denied: ['应用没有来源日历的读取权限', '核对该来源日历的应用访问权限。'],
  rate_limited: ['日历查询受到限流', '系统会按退避时间重试，持续出现时检查请求量。'],
  read_timeout: ['日历查询超时', '检查服务器到飞书的连接，系统会有限次重试。'],
  network_error: ['日历连接失败', '检查服务器网络及飞书连接。'],
  upstream_unavailable: ['日历服务暂不可用', '等待上游恢复，核验成功前保留预约。'],
  invalid_response: ['日历核验信息不完整', '检查上游响应结构和服务端核验记录。'],
}
const label = (code?: string | null) => reasons[code || ''] || reasons.invalid_response
const when = (value?: string) => value ? new Date(value).toLocaleString() : '暂无'
const code = (record: UsageRecord) => [record.verification_http_status != null ? `HTTP ${record.verification_http_status}` : '', record.verification_code != null ? `飞书 ${record.verification_code}` : ''].filter(Boolean).join(' · ')
</script>
<template>
  <section class="verification-status" aria-label="预约核验状态">
    <p>房间自动释放：{{ usage.release_enabled ? '已开启' : '未开启' }}</p>
    <template v-if="usage.record">
      <p>本次预约核验：{{ usage.record.verification_error ? '未通过' : usage.record.verified ? '已通过' : '待核验' }}</p>
      <p v-if="usage.record.state === 'confirmed'">本次预约已签到，保持占用</p>
      <p v-else-if="usage.record.state === 'blocked'">本次预约已保留</p>
      <div v-if="usage.record.verification_error" class="verification-warning" role="status">
        <strong>{{ label(usage.record.verification_error)[0] }}</strong>
        <p>{{ label(usage.record.verification_error)[1] }}</p>
        <p v-if="code(usage.record)">{{ code(usage.record) }}</p>
        <p>最近失败：{{ when(usage.record.verification_failed_at) }} · 累计 {{ usage.record.verification_failures || 1 }} 次</p>
      </div>
      <p v-if="usage.record.verification_succeeded_at">最近成功：{{ when(usage.record.verification_succeeded_at) }}</p>
    </template>
    <p v-else>暂无当前预约核验记录</p>
  </section>
  <section v-if="issues.length" class="verification-issues" aria-label="最近核验异常">
    <h3>最近核验异常</h3><p>最近24小时，最多10场；已签到或已恢复的预约不在此列出。</p>
    <ul><li v-for="issue in issues" :key="issue.id">
      <p>{{ when(issue.occurrence.start_time) }} · {{ issue.state === 'blocked' ? '预约已保留' : '等待核验' }}</p>
      <strong>{{ label(issue.verification_error)[0] }}</strong><p v-if="code(issue)">{{ code(issue) }}</p>
    </li></ul>
  </section>
</template>
<style scoped>
.verification-status,.verification-issues{display:grid;gap:8px;padding:16px;border:1px solid #dbe2ea;border-radius:8px}.verification-warning{display:grid;gap:6px;padding:12px;background:#fff7e7;border-left:3px solid #bd751b;overflow-wrap:anywhere}.verification-issues ul{display:grid;gap:12px;font-size:14px}.verification-issues h3{font-weight:600}
</style>
