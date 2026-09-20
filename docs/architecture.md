# RoomBeacon 架构与接口

> 2026-09-20 连续预约修复已上线：前后端均为 `85a3cf2e9afbdc0183e2f9c30ab1156011aa6a09`。前场保留时后场也会在提前窗口独立监控；168项后端及70项浏览器检查通过，BX68真实新协议字段心跳200。仅IT灯塔-Test开放写入，其余342间官方方案；新预约真实释放仍待验证。见 [修复与回退记录](v5-adjacent-monitoring-verification.md)。

> 2026-09-20 23:00 双预约实测：两场均受保护，未发送释放；发现并部署新预约心跳切换修复。当前后端 `781b409841a571fb54ae0c720b234f880537bc32`，静态仍为 `f108b8575e12b54611c1ae84bb4e01713a9c4b1e`。连续预约提前监控仍有缺陷，真实自动释放尚未验收；其他 342 间保持官方方案。见 [双预约实测](v5-two-bookings-verification.md)。

> 版本: 0.1 | 作者: RoomBeacon Team | 更新日期: 2026-09-16

---

## 目录

- [1. 结构](#1-结构)
- [2. 接口](#2-接口)
- [3. 缓存与兼容](#3-缓存与兼容)

## 1. 结构

```text
飞书开放平台 ← FeishuRoomsClient ← 后台 collector → 独立 Redis
                                                     ↓
                    Web V1/V2/V3 ← Nginx ← FastAPI 只读 API
                    Android / ESP：仅规划
```

Python 3.13、FastAPI、Pydantic、httpx、Redis、Astral、qrcode；Vue 3、TypeScript、Vite、Tailwind、Axios。运行不依赖 PostgreSQL、SQLAlchemy、Celery、Argus OAuth 或审批监听。

独立入口 `app.room_display_main:app` 使用 lifespan 启动采集循环；目录每 15 分钟同步，日程默认 300 秒一轮、每批 <=20 间。Redis 租约控制多进程采集，失败保留旧数据和游标。CLI 的目录/签发验证可主动查询上游，但终端与中控读请求不触发飞书。

## 2. 接口

| 方法/路径 | 认证 | 返回 |
|---|---|---|
| GET /api/meeting-rooms/display | 单会议室设备 Bearer 凭证 | 绑定会议室快照 |
| GET /api/room-control/rooms | 主控任一组 Bearer 凭证 | 地区/层级目录 |
| GET /api/room-control/preview?room_id=omm_… | 主控 Bearer 凭证 | 指定会议室快照 |

没有登录/OAuth/签发 HTTP API，没有公共 health 接口。设备凭证不允许调用中控；中控凭证不能替代设备凭证。非法参数 422，认证失败 401，缓存首次同步或上游错误 502；前端展示历史和未知状态。

响应 envelope 为 `{code,message,data}`，RoomSchedule 包含 room、events、synced_at、valid_until、server_time、titles_available、daylight、checkin_qr。事件包含 uid、original_time、start_time、end_time、organizer、summary。checkin_qr 是可选 SVG data URI，ESP 不能假定已提供 PNG。

飞书调用：`/auth/v3/tenant_access_token/internal`、`/vc/v1/rooms`、`/vc/v1/room_levels/mget`、`/meeting_room/freebusy/batch_get`、`/meeting_room/summary/batch_get`。权限沿用既有应用，历史已申请 `vc:room:readonly`、`calendar:room:readonly`、`calendar:room`；不宣称三者均为所有接口的最小必要集，后续变更需按官方权限关联复核。

## 3. 缓存与兼容

保留 rooms:* 键、设备令牌格式 `room:omm_ID:random`、ROOM_DISPLAY_* 配置及 argus_room_display/argus_room_version/argus_room_control 浏览器键。迁移不自动换域名；换 origin 仍需重新绑定。

快照保留 7 天不等于有效 7 天。有效时间约为采集周期+60秒，且不越过上海午夜；前端请求失败也立即转未知。终端每 15 秒读取，时钟每秒更新，使用服务器时间加单调时钟。

生产运行名暂保留历史 app.room_display_main 和 room-display；新安装模板可用 RoomBeacon 路径。配置不再要求 Argus SECRET_KEY/DATABASE_URL，不再引入 Argus 用户 JWT；旧 service.env 多余字段忽略。
