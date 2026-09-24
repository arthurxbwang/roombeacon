# RoomBeacon 架构与接口

> 2026-09-24 配置模型改为设备关联硬件安装版本、会议室关联软件版本、明确部署与回执；当前定义见 [ADR 0005](adr/0005-versioned-configuration.md)。下面旧配置分层叙述保留为历史。

> 开发增补（未部署）：后台支持显式房间→日历映射，对新时间身份自动核验重复范围，释放前二次读取并重查心跳/租约；终端仍只请求缓存。默认空映射保留原流程，详见[设计与边界](v5-reschedule-autoverify.md)。

> 当前后端7deb6ba（前端da63152）每日重复单实例释放已实测、后续日期保留。重复实例增补：管理员verify接口支持互斥的recurring_verified登记，发送前将普通实例0转换为已核对开始时刻Unix秒，例外保留原始时间；后续实例读回核验。未登记未来实例不自动获释放资格，见[重复测试](v5-recurring-release-verification.md)。

> 2026-09-21 当前后端374db89、静态da63152。门牌提前结束已关闭，忙闲GET有限重试，非重复连续签到与两次自动释放已实测通过；其他342间官方方案。准确版本与范围见[连续三场验收](v5-retest-acceptance.md)，下方旧版本说明为历史记录。

> 2026-09-21 当前Control后端c665859、静态85a3cf2。完整忙闲读回更新释放后缓存，原子发布防止旧采集覆盖；非重复自动释放与提前结束均已实测，其他342间官方方案。182项后端检查通过，范围与回退见[四场记录](v5-four-bookings-verification.md)。

> 2026-09-20 连续预约修复已上线：前后端均为 `85a3cf2e9afbdc0183e2f9c30ab1156011aa6a09`。前场保留时后场也会在提前窗口独立监控；168项后端及70项浏览器检查通过，BX68真实新协议字段心跳200。仅IT灯塔-Test开放写入，其余342间官方方案；新预约真实释放仍待验证。见 [修复与回退记录](v5-adjacent-monitoring-verification.md)。

> 2026-09-20 23:00 双预约实测：两场均受保护，未发送释放；发现并部署新预约心跳切换修复。当前后端 `781b409841a571fb54ae0c720b234f880537bc32`，静态仍为 `f108b8575e12b54611c1ae84bb4e01713a9c4b1e`。连续预约提前监控仍有缺陷，真实自动释放尚未验收；其他 342 间保持官方方案。见 [双预约实测](v5-two-bookings-verification.md)。

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

快照保留 7 天不等于有效 7 天。有效时间约为采集周期+60秒，且不越过实际查询终点（上海后天零点）；已覆盖下一天的数据不在中间零点提前失效；前端请求失败也立即转未知。终端每 15 秒读取，时钟每秒更新，使用服务器时间加单调时钟。

生产运行名暂保留历史 app.room_display_main 和 room-display；新安装模板可用 RoomBeacon 路径。配置不再要求 Argus SECRET_KEY/DATABASE_URL，不再引入 Argus 用户 JWT；旧 service.env 多余字段忽略。

## 组织者姓名补全（2026-09-17）

后台采集在组织者姓名缺失时，以现有飞书应用查询通讯录补全，成功缓存 5 分钟、失败缓存 1 分钟；按 App ID 隔离，不改变终端 API 或主题可见性。2026-09-22 生产已使用独立应用，最新权限核对及实测限制见 [飞书应用权限清单](feishu-permissions.md)。姓名补全已在生产复测；会议联系人统一显示仍待实现。

## 台账与模板分层（2026-09-23 已部署）

硬件方案描述型号与接线，安装模板引用硬件方案并保存方向和显示设置，设备绑定会议室并接收模板配置快照，会议室独立管理签到业务规则。模板原位编辑新增版本检查及独立版本表，保留原有设备与模板字段；详见[关系分析与接口兼容](device-inventory-templates.md)。
