# 灯塔独立飞书自建应用：权限与迁移清单

> 2026-09-22最终决定：用户保留“联系人优先 → 可确认的组织者兜底 → 信息不可见”规则，接受当前影响并暂缓实施，Issue #1 按 `not_planned` 关闭。完整接口核查、北京110条预约与4张截图对照、普通预约参与者403/194001及重开条件见[分析归档](archive/issue-1-meeting-contact-2026-09-22.md)。下方权限建议和待办是历史排查记录，不要求新任务继续扩权或重新设计；联系人采集仍未实现。

## 2026-09-22：飞书 UI“预定者”与日程组织者的区别

用户提供同一场面试的飞书截图，UI显示具体人员为“预定者”。这不能证明此前忙闲接口中的异常open_id属于该人员，也不能将多场共享异常ID的日程统一映射到截图中的姓名。

官方存在更直接的字段：日程的会议室参与者 `attendees[].operate_id`。官方[添加日程参与人](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event-attendee/create)说明，应用身份创建日程时，添加会议室需指定会议室联系人，这个联系人会显示在日程的会议室信息中。[获取日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/get)的响应支持返回该字段。它与日程组织者 `event_organizer` / 忙闲接口 `organizer_info` 是不同语义。

建议验证链路：

1. 确认原日程或授权可读副本的 `calendar_id`，由现有忙闲日程的UID及original_time组成 `event_id`。
2. 以 `user_id_type=open_id`、`need_attendee=true` 获取该日程；按会议室 `room_id` 精确选择参与者，读取 `operate_id`。如参与者分页未覆盖目标会议室，需继续有界读取完整参与者列表，不能取任意参与者作为预定者。
3. 用 `operate_id` 查询通讯录姓名，与用户截图的“预定者”核对。不能改用候选人、任意参会人或机器人名称替代。

实测进度：生产应用的日历列表和搜索均HTTP200/code0；列表只返回应用主日历。搜索会议室关键词未找到日历；招聘关键词返回5个共享日历，其中1个为reader，其余仅free_busy_reader。仅在该reader候选日历查询截图指定的日程，返回HTTP404/code193001（没有找到日程）。没有证明这些候选日历就是实际组织日历，也没有取得目标日程的operate_id；字段路径成立，真实返回姓名尚未验证。

下一步需要目标日程分享链接或所属calendar_id。调用日程详情需要 `calendar:calendar.event:read`（或官方替代权限），并且当前身份对日历有reader/writer/owner权限；获取参与者还应满足参与者可见性条件。只增加通讯录权限不能补足日历访问权。优先给予所需日历的只读访问，不为此要求日历写入或招聘资料权限；如必须采用用户身份，应通过正式OAuth授权，而不是复制客户端Cookie。

本轮只读排查，无业务代码、生产配置、飞书授权或日历内容变更。截图姓名、日程标题、真实人员ID不写入仓库。

## 2026-09-22 15:32–15:36 权限调整后复测

用户确认已调整两项“应用身份”权限后，使用生产新应用重新获取令牌并只读复测。配置文件中的应用凭证与运行进程一致；未输出姓名、用户ID或凭证，未重启服务或清空缓存。

| 检查 | 实测结果 |
|---|---|
| 姓名查询正向对照 | 从同一次最新忙闲响应选择两个不同、已有姓名的组织者，分别查询通讯录；均为HTTP200、code0，返回非空name且与忙闲中的姓名一致。证明当前应用已能读取用户姓名；没有管理员会话，不宣称核验了后台全部勾选项或全公司数据范围。 |
| 原失败组织者 | 原来的HTTP400/code41050变为HTTP400/code41012（用户ID无效），仍无姓名。 |
| 最新源数据核对 | 对缺失姓名的一个房间重新查询忙闲，HTTP200/code0；21条预约中13条缺姓名，均携带同一个组织者ID，与原失败对象一致；用最新响应的ID查询仍为41012。不是仅重放旧应用日志或旧缓存中的ID。 |
| 采集与缓存 | 检查时343间快照均新鲜；最近三轮完整采集均为343间、0失败。1028条预约中952条有姓名、76条缺失，不能将全部缺失归因于抽查的一个对象，也不能把跨时刻数量变化当作权限修复效果。 |

**当前姓名读取能力已验证，剩余抽查问题是单个组织者ID无效，无证据需要继续增加权限。** 下一步由飞书管理员核对对应预约组织者的账号状态；若账号正常，需追查忙闲接口为何仍返回通讯录无法识别的ID。注销、外部人员或其他身份关系仅为待核实方向，尚未确认根因。不能将此对象标记为已成功补全，也不猜测其姓名。

错误码依据：[获取单个用户信息](https://open.feishu.cn/document/server-docs/contact-v3/user/get)。本轮只读复测，没有修改飞书授权、生产配置或业务源码。

### 同日后续：41012 身份类型排查

用户要求识别异常ID并分析故障位置。只读复查近期日志中的唯一补全对象，通讯录仍返回HTTP400/code41012；ID仅在用户明确请求的会话中展示，不写入仓库。

- 抽查缺姓名较多的4间会议室，在9月21日至23日的三日窗口中，26条忙闲日程携带同一个异常ID，组织者姓名均为空。不能据此认定这些日程属于同一名员工。
- 同一生产应用查询普通用户成功；忙闲和通讯录使用同一个新应用令牌，排除了本轮探针混用旧应用身份。异常ID直接来自最新忙闲响应。
- 当前灯塔应用机器人信息查询成功，其open_id与异常对象不同；只排除当前应用机器人，不能据此排除其他应用或非员工身份。
- 对4条当天关联日程的主题接口查询成功，返回4项非空主题、0项错误；未展示主题。缓存中此前缺主题不能当作日程必然私密的证据。
- 用户随后明确授权读取这4条日程的标题。均为不同候选人的视频面试，却共享同一异常组织者ID，进一步将排查重点收敛到招聘系统创建日程时使用的应用或服务身份。候选人姓名不能作为组织者姓名；实际标题、候选人姓名不写入仓库。
- 已核对生产源码：仅对忙闲原始响应中已有组织者姓名的日程查询并展示主题，随后才尝试通讯录姓名补全。因此当前对象的姓名缺失会连带隐藏主题，这是现有保守显示策略；不能将其误报为主题接口调用失败。
- 飞书[忙闲接口说明](https://open.feishu.cn/document/server-docs/calendar-v4/meeting-room-event/query-room-availability)明确：应用身份创建的日程不返回组织者姓名，私密日程不返回组织者信息。这是排查应用预约来源的依据，不足以证明当前异常ID一定属于某个应用。

当前故障范围收敛到**日程组织者身份与通讯录用户的对应关系**，优先核对招聘系统的创建应用、组织日历及服务账号；应用身份是有依据的推断，尚未识别具体应用或人员。其次核对实际组织者的账号状态、企业归属及身份映射。没有证据要求继续增加通讯录权限，也没有发现部门树解析、服务器连接或全局凭证故障。姓名补全失败按现有逻辑降级为空并短时负缓存，不改变会议室忙闲判断。

如后续确认属于应用等非人员组织者，应按确认的身份类型处理姓名缺失和重复告警；未确认之前不硬编码人员姓名、不放宽日程主题可见性。本轮没有修改相关逻辑。

## 2026-09-22权限调整前：通讯录数据范围检查（历史）

新生产应用的单用户查询已真实返回HTTP400、`41050`（no user authority）。从最近1小时真实查询记录提取到1个不同的查询对象，复查仍返回41050；没有输出或记录其姓名、用户ID和凭证。此前旧应用的41012记录不覆盖这个新结论。

**当时明确缺口是通讯录数据范围；调整后结果以上方复测为准。** 该结果不是“接口权限未开通”的典型99991672，也不能据此断言所有字段权限已经齐全。服务器只有应用运行凭证，没有飞书开发者后台的管理员会话；该轮未读取完整后台勾选清单，也未修改授权。

补齐步骤：

1. 在新的灯塔应用中核对“应用身份”的两项只读权限：`contact:contact.base:readonly`（获取通讯录基本信息，单用户接口入口）和`contact:user.base:readonly`（获取用户基本信息，包含姓名字段）。已开通则无需重复新增；存在可替代的旧总权限时，也不需要盲目叠加全部权限。
2. 进入[飞书开发者后台](https://open.feishu.cn/app)，选择新灯塔应用 → **开发配置 → 权限管理 → 数据权限 → 通讯录权限范围**，加入需要显示姓名的会议组织者或所属部门。应用可用范围不等于通讯录可读范围。
3. 已发布应用也可由企业管理员在[管理后台](https://feishu.cn/admin) → **工作台 → 应用管理**中调整该应用的通讯录权限范围。依据后台提示完成必要审批/发布，核对范围实际生效。
4. 若要求全公司会议室均显示内部组织者姓名，应让所需员工范围覆盖这些组织者；只试点时可先授权相关部门和人员。不需要通讯录写入、邮箱或手机号权限。
5. 生效后复查原失败用户接口，预期HTTP200、code0且返回非空name，再观察后台下一轮约5分钟采集。姓名负缓存为60秒，不应清空Redis或轮换设备凭证；通常无需重启服务。

如果41050消失但没有name，继续核对`contact:user.base:readonly`是否真正生效及人员类型/字段可见性。不能把所有缺失姓名都归因于同一问题，也不通过扩大日程主题权限来绕过隐私边界。

依据：[获取单个用户信息：41050错误码、接口权限和name字段权限](https://open.feishu.cn/document/server-docs/contact-v3/user/get)。以下2026-09-21清单保留完整功能申请范围；当前姓名问题不要求重新申请全部11项。


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
