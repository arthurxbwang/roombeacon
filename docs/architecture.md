# RoomBeacon 架构与接口

> 2026-09-20 发布：现有 Control 已切换至 RoomBeacon `4ba9d38`，V4/V5 前端与保护协议 2 API 同步部署，Nginx 仅追加对应的认证路由。测试房间观察模式，飞书写入关闭；详见 [部署记录](v5-control-deployment.md)。下方“尚未部署”说明为发布前记录。

> V5 保护协议 2 已本地实现：逐房间 owner 决定官方／V5 责任，GET 查询不保活；平板主动上报健康和操作状态，服务器在待释放后要求短期核验，再查询飞书并发送一次释放。方案、会话、实例或健康状态不一致则跳过当前预约；V5 房间不返回官方签到码。当前尚未部署，真实写入验证受测试预约准备权限限制。

> V5 增加默认关闭的确认 API 与独立后台释放任务；下文只读架构描述的是原有展示链路，保持兼容。V5 的鉴权、实例识别、失败策略见 [ADR 0003](adr/0003-v5-room-usage.md)，新增接口见 [V5 说明](v5-usage-verification.md)。

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
                    Android WebView 外壳 → 同源 H5（样机开发）
                    ESP：仅规划
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

## 组织者姓名补全（2026-09-17）

后台采集在组织者姓名缺失时，以现有飞书应用查询通讯录补全，成功缓存 5 分钟、失败缓存 1 分钟；按 App ID 隔离，不改变终端 API 或主题可见性。当前暂借 Argus 自建应用，权限核对、实测限制及独立迁移见 [飞书应用权限清单](feishu-permissions.md)。本次功能仅在 RoomBeacon 本地实现，未部署线上。
