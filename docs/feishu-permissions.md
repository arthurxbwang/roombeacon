# 灯塔独立飞书自建应用：权限与迁移清单

更新：2026-09-21。适用当前 RoomBeacon 代码，以及已提交、尚未启用的日历自动核验和预约测试工具。推荐在现有企业内创建“灯塔 RoomBeacon”企业自建应用，使用应用身份 `tenant_access_token`。本次只整理配置与迁移清单，没有创建应用、换密钥或改线上房间规则。

## 一、完整申请清单

覆盖当前门牌展示、V5释放、改期自动核验、自动预约测试及姓名补全，共11项。下表采用细分日历权限，不要求再叠加 `calendar:calendar` 总权限。

| 编号 | 开放平台权限标识 | 权限名称 | 当前用途与是否需要 |
|---|---|---|---|
| 1 | `vc:room:readonly` | 获取视频会议室信息 | 基础必需：读取会议室目录、容量、启停状态和楼宇/楼层层级。 |
| 2 | `calendar:room:readonly` | 获取会议室信息 | 基础必需：读取会议室忙闲；V5未签到释放接口也使用此权限。 |
| 3 | `calendar:room` | 管理会议室信息 | 保持会议主题展示需要：现有主题/详情查询接口明确要求此权限。不是为了让灯塔创建或删除会议室资源。 |
| 4 | `calendar:calendar:read` | 读取日历信息 | 自动核验及测试工具需要：查询指定日历、角色和日历列表。 |
| 5 | `calendar:calendar.event:read` | 读取日程信息 | 自动核验需要：读取预约详情、重复实例、改期实例；测试工具检查参与者接受状态。 |
| 6 | `calendar:calendar.event:create` | 创建日程 | 自动预约测试需要：创建不重复及每日/每周/每月测试系列。 |
| 7 | `calendar:calendar.event:update` | 更新日程 | 自动预约测试需要：改期及添加会议室资源参与者。创建日程本身不等于订到会议室。 |
| 8 | `calendar:calendar.event:delete` | 删除日程 | 自动预约测试需要：取消工具创建的日程或指定重复实例；V5正常未签到释放不依赖此接口。 |
| 9 | `calendar:calendar:create` | 创建日历 | 自动准备测试日历时需要；若已提供符合条件的可写共享日历，可不申请。 |
| 10 | `contact:contact.base:readonly` | 获取通讯录基本信息 | 姓名补全需要：调用获取单个用户信息接口的入口权限。 |
| 11 | `contact:user.base:readonly` | 获取用户基本信息 | 姓名补全需要：让单用户接口返回name等基本字段；与第10项用途不同。 |

仅展示忙闲和按既有试点规则运行，可按1–3配置；增加自动核验需4–5；完整自动化测试增加6–9；姓名补全增加10–11。姓名补全缺少授权时不猜测姓名，不阻止忙闲显示。

两处容易误配：

- `calendar:room:readonly` 虽然名称带readonly，官方“回复会议室日程实例”接口仍使用它执行未签到释放；不要把名称当成严格只读保证。
- `calendar:room` 是当前“查询会议室日程主题和会议详情”的明确要求，不能因灯塔不创建会议室就直接去掉。

## 二、接口逐项对应与官方依据

路径均以 `/open-apis` 开头。已按2026-09-21可取得的官方文档正文核对；释放接口同时参考本会话已保存的官方文档正文。新应用尚未创建，以下不是新应用已授权或已经实测的证明。

| 代码实际调用 | 对应权限 | 官方文档 |
|---|---|---|
| GET `/vc/v1/rooms` | `vc:room:readonly` | [查询会议室列表](https://open.feishu.cn/document/server-docs/vc-v1/room/list) |
| POST `/vc/v1/room_levels/mget` | `vc:room:readonly` | [批量查询层级](https://open.feishu.cn/document/server-docs/vc-v1/room_level/mget) |
| GET `/meeting_room/freebusy/batch_get` | `calendar:room:readonly` | [查询会议室忙闲](https://open.feishu.cn/document/ukTMukTMukTM/uIDOyUjLygjM14iM4ITN) |
| POST `/meeting_room/summary/batch_get` | `calendar:room` | [查询主题和详情](https://open.feishu.cn/document/ukTMukTMukTM/uIjM5UjLyITO14iMykTN/) |
| POST `/meeting_room/instance/reply` | `calendar:room:readonly` | [回复会议室日程实例](https://open.feishu.cn/document/ukTMukTMukTM/uYzN4UjL2cDO14iN3gTN) |
| GET `/calendar/v4/calendars`、`/calendars/:calendar_id` | `calendar:calendar:read` | [日历列表](https://open.feishu.cn/document/server-docs/calendar-v4/calendar/list)、[日历详情](https://open.feishu.cn/document/server-docs/calendar-v4/calendar/get) |
| GET `/calendar/v4/calendars/:calendar_id/events/:event_id`及`/instances`、`/attendees` | `calendar:calendar.event:read` | [日程详情](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/get)、[重复实例](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/instances)、[参与者](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event-attendee/list) |
| POST `/calendar/v4/calendars` | `calendar:calendar:create` | [创建日历](https://open.feishu.cn/document/server-docs/calendar-v4/calendar/create) |
| POST `/calendar/v4/calendars/:calendar_id/events` | `calendar:calendar.event:create` | [创建日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/create) |
| PATCH `/calendar/v4/calendars/:calendar_id/events/:event_id` | `calendar:calendar.event:update` | [更新日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/patch) |
| POST `/calendar/v4/calendars/:calendar_id/events/:event_id/attendees` | `calendar:calendar.event:update` | [添加会议室参与者](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event-attendee/create) |
| DELETE `/calendar/v4/calendars/:calendar_id/events/:event_id` | `calendar:calendar.event:delete` | [删除日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/delete) |
| GET `/contact/v3/users/:open_id?user_id_type=open_id` | `contact:contact.base:readonly` + `contact:user.base:readonly` | [单用户信息：接口及字段权限](https://open.feishu.cn/document/server-docs/contact-v3/user/get) |

日历接口文档列出的 `calendar:calendar` 或 `calendar:calendar:readonly` 多为细分权限的替代项，不是全部都要叠加。通讯录旧权限 `contact:contact:readonly_as_app` 是历史替代方案；新应用优先使用上述接口权限+字段权限，不复制Argus历史整包权限。

## 三、权限之外还要配置的资源

- [ ] 在同一企业创建企业自建应用，开通上述“应用身份”权限；完成管理员审批及版本发布，核对实际生效状态。
- [ ] 启用应用机器人能力。应用身份创建、修改、删除日程和添加参与者均要求机器人能力；无需因此申请聊天消息读写权限。
- [ ] 配置应用可用范围、通讯录数据权限范围，覆盖实际需要显示姓名的预约组织者；这不等于获得其个人日历的读取权。
- [ ] 为新应用准备独立共享日历 `RoomBeacon-Automation-IT灯塔-Test`，应用具有owner/writer；可由工具使用第9项创建。旧Argus应用的日历和权限不会因换App ID自动转移。
- [ ] 自动核验目标日历须允许应用读取日程详情，只有忙闲权限不足。现版本按房间映射一个显式可读日历，测试从该日历发起；覆盖全体员工从个人日历创建的预约，还需解决这些日历的授权及映射/发现，当前未完成全员场景验证。
- [ ] 自动预约时确认测试房间允许该应用预约，且参与者状态返回accept。工具不使用管理员绕过预约范围。
- [ ] V4房间继续官方签到、官方规则；只有IT灯塔-Test关闭飞书原生未签到释放，采用V5服务器规则。API权限本身不会设置这些业务规则。
- [ ] 服务器保持只给IT灯塔-Test授予V5释放白名单；新应用可读取其他房间不等于灯塔程序可以释放它们。

日历资源权限与组织者身份仍有限制：修改会议时间需要符合组织者编辑权，删除日程要求当前身份是组织者。测试工具只操作自身账本创建的预约；不能把event:update/delete解释成可以随意改删全公司会议。

## 四、当前不用额外申请的权限

当前没有调用消息、审批、云文档、考勤、录制、视频会议管理或通讯录写入接口；也不读取邮箱、手机号和用户user_id，不为这些字段申请权限。目录层级读取选择 `vc:room:readonly`，不需再叠加 `vc:room`。

V4二维码来自管理员配置的官方签到链接，没有额外调用Open API生成签到码或替用户完成官方签到。V5平板/Control签到和心跳写入RoomBeacon自身服务与Redis，不是飞书考勤，也不需要attendance权限。

现代码使用服务器轮询，无用户OAuth登录流程、无飞书事件订阅处理器，因此本轮不要求OAuth回调、事件订阅地址、Encrypt Key或Verification Token。后续若采用事件推送降低同步延迟，再单独增加相应能力。

## 五、从Argus切到新应用

1. 创建并发布新应用，完成权限和专用日历配置。先用新应用做无写入预检：目录/层级、忙闲、主题、姓名、日历及重复实例；检查读取范围，不以旧缓存页面正常作为通过。
2. 在服务器私有环境中保存新App ID、App Secret和日历ID，权限600。App Secret不进入Git、截图或对话；不修改Argus自身服务配置。
3. 新应用建立独立测试日历，验证创建、添加会议室接受、单次改期、指定实例取消，再测试签到保留/缺席释放。旧应用的测试账本不直接作为新应用可修改资源清单。
4. 选定准确代码SHA、现有Control目标服务和回退配置；切换前暂停V5写入、核对在途请求，保留Redis和房间策略。更换 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS` 并重启单个采集/服务实例。
5. 用户open_id按应用隔离。用新应用重新采集组织者ID；姓名缓存已按App ID分区。核对会议室ID仍匹配既有绑定，完整刷新缓存，不将旧App ID获取的人员ID直接用于新应用。
6. 保留现有API路径、Control密码、设备凭证、浏览器存储和Redis业务键；同域名/路径下单纯换飞书应用一般无需重新绑定平板。核对343间目录/显示及其他342间官方规则，再恢复测试房下一场完整监控窗口。已保护实例不强行重置。
7. 回退：先暂停V5写入并核对在途状态，恢复原应用私有配置和旧版本。旧Argus应用仍可能服务其他系统，不因灯塔迁移而删除应用或撤销它仍使用的权限。

## 六、可复制的完整权限标识

```text
vc:room:readonly
calendar:room:readonly
calendar:room
calendar:calendar:read
calendar:calendar.event:read
calendar:calendar.event:create
calendar:calendar.event:update
calendar:calendar.event:delete
calendar:calendar:create
contact:contact.base:readonly
contact:user.base:readonly
```

## 七、原姓名补全实现与历史核查

以下保留2026-09-17记录；权限申请以本文上方新清单为准。

### 实现与失败边界

- 仅在忙闲数据没有姓名、但有格式有效的 `open_id` 时补全；已有姓名优先，无 ID 不猜测。
- 每批最多查询 20 个不同 ID，并发请求各限时 3 秒；超出本批额度的人员在后续采集中重试。重复 ID 合并查询。
- `rooms:organizer:v1:{App ID 的 SHA-256 前 24 位}:{open_id}` 缓存成功姓名 300 秒、失败/空姓名 60 秒。成功缓存意味着权限撤销或改名最长可能延迟约 5 分钟再检查；已经生成的日程快照仍遵循原有有效期和离线展示规则。
- 权限拒绝、无效 ID、网络失败、超时或畸形数据均不伪造姓名，不改变忙闲时间，不使用过期姓名缓存兜底。失败日志只含错误类型；传输层只记录错误码，不记录响应体、姓名或凭证。
- 姓名补全不会扩大日程主题查询范围；忙闲接口原来未提供姓名的会议仍不因通讯录补全而额外获取主题。
- 不向终端新增 open_id 字段；终端仍只读缓存。

### 2026-09-17线上只读核查

2026-09-17，用门牌服务器现有应用查询北京 201 当日 09:30–10:15 的组织者：忙闲接口有 open_id、无姓名，通讯录接口返回 `41012`，无姓名结果。本次未保存或输出真实 ID、姓名、凭证或上游响应体。

这证明该场会议尚不能通过此接口补全；不能据此断言只缺权限。后续需核对 ID 对当前应用是否有效、人员类型与所属租户，以及通讯录范围；必要时由飞书支持协查。本地 mock 测试通过不等于该场线上修复成功。本次未部署代码、重启服务或调整飞书权限。
