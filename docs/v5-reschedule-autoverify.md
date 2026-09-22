# V5 改期重新签到与自动化预约测试（2026-09-21）

## 结论与当前状态

用户确认规则：已签到会议改期后，按新时间重新签到；未签到只释放改期后的当次预约，重复系列后续日期保留。

本轮完成代码与隔离回归，尚未部署或启用。Control 现有后端仍为 `7deb6ba97818d30e11677c1cb7f5ae8e06c3f5c0`，静态仍为 `da6315263fde70f4351a26f64d40a9edb17823a6`。没有修改任何房间策略、历史签到、设备凭证或线上预约。现有 IT灯塔-Test 白名单不变，其他342间保持官方方案。

真实缺陷见[已签到改期观察](v5-signed-reschedule-observation.md)：17:30场签到后移到18:00，新身份未取得释放资格，18:10进入保护，预约保留。本轮不把保护记录重置为可释放。

## 实现

- 房间、会议UID、原始实例时间、开始和结束共同构成签到身份；改期产生新记录，原签到仅保留在旧记录。
- 新配置 `ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS` 为精确的房间→可读取日历映射，默认空。只有同时在释放白名单、V5自动模式、允许写入且未暂停的房间才自动核验。
- 新预约先经历既有提前监控、平板心跳和缓存新鲜度校验，再由后台读取该日历的会议详情。普通预约必须明确非重复且时间一致；重复预约查询实际实例ID；改期例外保留原始实例时间。
- 日历读取总时限8秒；失败保留未核验状态，后续最多每30秒重新读取。截止前仍无法确认则保护，不继承旧签到，也不根据忙闲猜测重复规则。
- 日历核验结束重新检查时间窗口、规则、心跳和缓存；原子更新避免覆盖同时到达的签到。发送释放前再次读取日历，核对作用范围，并重新检查平板挑战时效、租约、规则及预约。
- 日历称非重复但忙闲显示同UID后续实例时拒绝释放。只有单次明确写入，发送结果不明仍保留不确定状态，不重试释放。
- 已配置自动核验的页面显示“正在核验预约，暂不自动释放”，仍可正常签到；未配置日历保留原逐实例登记流程。

这是显式日历范围内的自动核验，不代表可以读取全公司每个人的日历。从其他不可读取日历创建的预约仍会受保护。自动测试应统一从专用测试日历发起；要覆盖某个员工现有预约，需要另外给应用该预约所在日历的读取权限，并配置相应日历。API权限本身不等于日历数据访问权。

## 当前权限阻塞

2026-09-21只读请求现有应用 `/calendar/v4/calendars?page_size=50`，飞书返回 HTTP400 / `99991672`，要求日历读取相关权限。此前创建测试日历也因权限不足被拒绝。因此尚不能用真实日历证据启用这项修复，更不能把模拟通过当作线上改期释放验收。

在现有自建应用中申请权限并发布生效；租户如有审批要求，由管理员完成。无需提供个人密码、主控密码或在对话中粘贴 App Secret。

| 用途 | 权限 |
|---|---|
| 读取指定日历和权限信息 | `calendar:calendar:read` |
| 读取会议、重复实例和参与者状态 | `calendar:calendar.event:read` |
| 自动创建测试预约 | `calendar:calendar.event:create` |
| 改期、添加专用会议室 | `calendar:calendar.event:update` |
| 取消工具创建的测试预约或指定实例 | `calendar:calendar.event:delete` |
| 让工具创建应用自有测试日历（可选但建议） | `calendar:calendar:create` |

仅修复自动核验需要前两项，以及目标日历可读；完整自动预约测试需要后续写权限。保留现有会议室忙闲与释放权限。启用应用机器人能力；专用日历名固定 `RoomBeacon-Automation-IT灯塔-Test`，类型为共享日历，应用对它拥有 owner/writer。可以授权工具创建该日历，或准备同名共享日历并提供其 calendar_id 和应用访问权限。

官方依据：[获取日历](https://open.feishu.cn/document/server-docs/calendar-v4/calendar/get)、[创建日历](https://open.feishu.cn/document/server-docs/calendar-v4/calendar/create)、[创建日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/create)、[读取日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/get)、[修改日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/patch)、[删除日程](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/delete)、[添加会议室参与者](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event-attendee/create)。

## 测试资源与工具

沿用 IT灯塔-Test、BX68 平板和现有 Control，不需要再创建会议室。平板持续在线；长期测试最好建立平板到 Control 的稳定内网连通，避免依赖临时 ADB 反向转发。服务器故障注入宜使用独立测试实例，不能停掉服务其他房间的共享采集。

`backend/app/services/room_usage_test_driver.py` 提供 init/preflight/create/inspect/instances/move/cancel。凭证从既有服务器私有环境读取，状态写入源码仓库之外的600权限JSON账本；只修改账本中自己创建的日程，只邀请固定测试房间。支持不重复、每天、每周、每月，重复系列限定3次；预约提前至少20分钟，时长15–60分钟。写入超时不自动重发；需独立读回核实。

下例在 backend 目录、已加载私有环境的会话执行；开始时间替换为实际未来带时区时间。不会直接创建或运行这些示例。

```bash
python -m app.services.room_usage_test_driver --ledger /var/lib/roombeacon-tests/ledger.json init
python -m app.services.room_usage_test_driver --ledger /var/lib/roombeacon-tests/ledger.json preflight
python -m app.services.room_usage_test_driver --ledger /var/lib/roombeacon-tests/ledger.json create --case b04 --start '2026-09-22T14:00:00+08:00' --minutes 30
python -m app.services.room_usage_test_driver --ledger /var/lib/roombeacon-tests/ledger.json inspect --case b04
```

inspect 只有会议室参与者返回 accept 才表示预约已接受；添加参与者接口返回成功不等于订房成功。重复日程先通过 instances 取得真实正数 original，再对 move/cancel 指定 `--original`，工具拒绝0代表整个系列。工具当前按原实例时间前后2天核对重复实例；改期超过该范围的再次操作会拒绝，需要扩展查询与实测后再使用，不猜测实例。

这是预约准备与核对工具，尚未完成真实权限联调；不是已跑通全部验收场景的无人值守测试平台。签到通过既有 Control/平板接口和真实心跳验证；故障与竞争条件在隔离环境模拟，不向生产伪造在线信号。

## 启用与回退

1. 权限生效后先创建/读取专用测试日历，验证应用角色与真实非重复/重复数据格式，以及会议室资源已接受预约。
2. 将日历ID以私有环境 JSON 映射到 IT灯塔-Test；不能映射其他在用房间。保留既有单房间释放白名单。
3. 从 GitHub 已提交的准确SHA发布前后端；部署前核对当前版本、备份 systemd/环境/静态路径和 Redis 记录，避开在途释放。重启后的已监控记录保留保护，不强行恢复资格。
4. 按[验收清单](v5-acceptance-checklist.md)优先重测B04（签到后改期，分别再次签到/不签到）、B01（明天实例移到今天），核对后续日期保留；之后周/月重复和故障边界。
5. 回退前暂停V5写入，核对在途请求；恢复上述后端和静态SHA、原环境，移除新映射。旧版本不完整理解日历核验来源，不能直接让它处理新版已核验记录；复核记录并使用下一场完整监控窗口后恢复。

## 验证

- Ruff通过；250项后端隔离测试通过，含改期两条完整生命周期、周/月实例解析、重复例外、元数据矛盾、权限拒绝、读超时、映射撤销、并发签到、断线、暂停、改期竞态、平板确认过期和只操作自建日历等。
- 前端依赖安装与构建通过；Chromium单进程完整回归71项通过。首轮6进程运行60通过、11失败，出现页面关闭及等待超时；相同构建和断言单进程复跑全部通过，未将首轮失败隐藏或归因为已查明的产品缺陷。
- 真实改期自动核验、自动预约创建和最终释放尚待上述权限与专用日历；本轮未部署，未新增真实预约。
