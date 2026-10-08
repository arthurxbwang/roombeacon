# RoomBeacon 当前状态

## 批量交付与维护计划（2026-10-08，未实施）

用户确认设备均支持 PoE；新建本地分支 `codex/16-delivery-maintenance-plan`，整理[首装、前后台任务、低频 APK 更新与 PoE 恢复计划](../plan/device-delivery-maintenance.md)。现有自动纳管、模板与回执继续复用；按 IP 安装、安装助手、无 ADB APK 更新、自动关闭 ADB 和交换机控制为待建设／待验收。PoE 单端口实际断电及无 ADB 自动恢复仍待核验；分别接续 #16／#29／#10。此次仅修改计划与文档，生产版本不变。

## 1.0.1 正式门牌补丁与就绪核查（2026-10-08）

PR #38 / Release v1.0.1 / 生产应用 `b574638beed5be65596e5ca647c98236da56cd17` 已上线，门牌运维提示已清理，重启显式签到恢复修复；W9TW7S刷新回执10/10、无错误、真实心跳健康，18条既有记录保持。本地/生产后端各358项、浏览器136项通过。展示/签到可日常使用。

用户分享日程已定位正确来源日历；现有自动核验函数对真实非重复和4个每日重复实例只读验证成功。用户随后明确授权生产写入，12:31 仅为 IT灯塔-Test 启用该来源映射；12:32 实际API auto_verify_enabled=true、release_enabled=true、paused=false。平板10/10、真实心跳健康，18条旧记录和策略保持，343间/18批采集无失败。真实释放/改期联调和其他来源覆盖仍待完成。详见 [整体核查与上线回执](production-readiness-2026-10-08.md)，接续 #2。

## RoomBeacon 1.0.0 正式版已上线（2026-10-08）

[#34](https://github.com/arthurxbwang/roombeacon/issues/34) 经 [PR #35](https://github.com/arthurxbwang/roombeacon/pull/35) 合入，正式 [v1.0.0](https://github.com/arthurxbwang/roombeacon/releases/tag/v1.0.0) / 生产应用为 `6ac52034fb3473ecbcd67ed20c99c619a3fdf423`。W9TW7S 已应用 V7 软件 v2：提前/宽限各 5 分钟、补确认 0 秒；移除保护说明、保留保护判断。长期策略/暂停持久化及托管身份核验上线，自动释放恢复。设备回执 9/9、无错误、真实心跳健康，硬件 v2、APK 0.7.0-debug 不变；343 间采集正常，17 条旧保护记录保持，其他 342 间未扩大写入权限。本地/生产后端各 345 项、浏览器 129 项通过。准确版本、验收边界和回退见 [正式上线记录](production-v1-2026-10-08.md)。

## V7 已部署（2026-09-28）

[#31](https://github.com/arthurxbwang/roombeacon/issues/31) 经 PR #32 合入，生产前后端为 `9f21d96a0698e918b9c61f81a0bb834df20541f4`。W9TW7S（IT灯塔-Test）已应用 V7 专用软件 v1，硬件 v2、APK 0.7.0 不变，设备回执 8/8、无错误；会前／会后各 5 分钟，保留 60 秒释放缓冲。实机 1280×720 显示及 343 间缓存采集正常，其他 342 间仍 official/off。14:15 旧预约保留保护、不重新授予签到或释放资格。准确配置与回退见[上线记录](production-v7-2026-09-28.md)，界面说明见 [V7 文档](v7-brand-checkin.md)。

更新：2026-10-08。本页是新任务的状态入口；下方按日期保留历史发布记录。

## GitHub 收尾与待办校准（2026-09-24）

PR #24 → #26 → #28 已依次合入 `main`，最终应用合并提交 `a9143250e0ae9d156d362696d9612fe15ccd7033`；Issue #23、#25、#27 按已完成关闭。合并树与重构分支 `4c9025c` 完全一致，后者相对生产 `3359332` 仅有文档差异。本轮未重新部署；只读核对生产 102 个源文件一致，BX68 APK 0.7.0、协议 3、回执 7/7、无错误。详情见[事项校准与合并回执](issue-reconciliation-2026-09-24.md)。

旧配置模型由 [ADR 0005](adr/0005-versioned-configuration.md) 接续：业务参数随软件版本显式部署，房间资格和预约逐实例核验独立保留。已转换设备拒绝旧配置及旧回退接口。#10 只跟踪设备接入、网络切换和长稳；#16 跟踪无 ADB 更新与恢复，自动关闭网络 ADB 另见 #29。2026-09-22 的 ADB 关闭是历史实测，#29 的 2026-09-24 检查记录其已重新可连接。

## 配置模型重构已部署（2026-09-24）

[#27](https://github.com/arthurxbwang/roombeacon/issues/27)：硬件安装和软件模板独立编辑、不可覆盖的发布版本、设备显式部署、会议室与模板三处反查、可读审计已实现。生产应用 `3359332b5b84343318693f7266d7966d3a950619`；BX68 APK 0.7.0，硬件 v2＋软件 v1 回执 7/7，原参数与 V5 策略不变。324 项后端、108 项浏览器覆盖和 19 项 Android 测试通过；真实验收及回退见[本次发布](production-configuration-2026-09-24.md)，关系定义见 [ADR 0005](adr/0005-versioned-configuration.md)。以下旧版本记录按日期保留。

## 台账与模板编辑已部署（2026-09-23）

设备台账多级筛选、安装模板编辑与会议室业务方案分离见 [Issue #25](https://github.com/arthurxbwang/roombeacon/issues/25) 和[设计记录](device-inventory-templates.md)。前后端 `4b65ecc` 已部署，343 间真实采集、后台模板新建／编辑和五级位置筛选通过；BX68 回执仍为 5/5，未更新 APK 或业务规则，见[发布与回退记录](production-inventory-templates-2026-09-23.md)。分支 `codex/device-inventory-templates` 接续型号模板基线 `3cb966e`，验收后推送 GitHub。

## 版本与维护入口

| 用途 | 标签 | 提交 |
|---|---|---|
| 完整源码整合基线 | `baseline-2026-09-22` | `15c1652dc8adf43adf1e7231689189c9d6349db1` |
| V6之前的生产后端 | `production-backend-2026-09-22` | `3b0bf39cdfdb92e421882444615f8ab7bcb76c8c` |
| V6之前的生产前端 | `production-frontend-2026-09-22` | `43d8b8f18d5569940cecce53217e7822459191e1` |

唯一维护仓库为 [arthurxbwang/roombeacon](https://github.com/arthurxbwang/roombeacon)，后续开发从最新 `main` 创建短期 `codex/` 分支。上述基线标签固定旧提交，后续文档或代码合并不移动标签。源码基线与生产前后端版本分别管理。

生产域名 `roombeacon.thundersoft.com`，SSH 8081，目录 `/data/roombeacon`；私钥和凭证仅保存在私有环境。此前 2026-09-23 前后端 SHA 为 `4b65ecceb53e82333df54038d1290bf4da42dc57`，台账及模板编辑的最新验收见[发布记录](production-inventory-templates-2026-09-23.md)；APK 0.6.2 的实机证据见[此前型号模板发布](production-model-templates-2026-09-23.md)；飞书登录基线见[发布记录](production-feishu-login-2026-09-22.md)，退出按钮修复的最新静态SHA与回退回执见[#20](https://github.com/arthurxbwang/roombeacon/issues/20)，此前设备交付见[V6发布记录](production-v6-2026-09-22.md)。

## 已完成

- Android WebView 外壳、型号灯控与恢复能力；BX68 样机当前 APK 0.7.0-debug，模板配置回执 9/9。
- V1—V5 页面及主控；提前结束已关闭，兼容接口认证后固定拒绝。
- 当前生产仅 IT灯塔-Test 开启 V5 签到与受控释放，其余 342 间不扩大写入权限。未来预约不因房间开关而自动获得释放资格。
- Caddy／Nginx 异常恢复已修复；接受 VM 层备份，指标由用户后续配置，证书续期由既定自动化负责。
- 全部历史分支源码已经整合，基线后端 250 项、前端 84 项、Android 11 项测试及对应构建检查通过。详见[整合报告](source-consolidation-2026-09-22.md)。

硬件开发资料已整理为[按需阅读索引](reference/README.md)：RK3568 使用精简 SDK 摘要，DP72 先读交接与勘误。SDK 资料整理不代表增加了 APK 能力。

## V6 新增交付

用户已批准一次性开发与上线 V6（[#10](https://github.com/arthurxbwang/roombeacon/issues/10)）：设备免配置纳管、Wi-Fi/有线身份连续、六位唯一码、管理员/只读与飞书登录、集中配置和回执。实施与运行边界见 [V6 文档](v6-device-management.md)。BX68自动纳管与开机恢复通过，用户关闭网络ADB后远程刷新回执4/4，后续无ADB更新验收见[#16](https://github.com/arthurxbwang/roombeacon/issues/16)；旧样机仍因DNS/网络不可达待接入。飞书回调用户已配置，首页飞书登录及一次性首位员工管理员初始化已发布8915b38，用户已真实扫码确认本人，核验唯一员工管理员及消费记录通过；见[登录发布记录](production-feishu-login-2026-09-22.md)及[#17](https://github.com/arthurxbwang/roombeacon/issues/17)。

## 已接受的联系人限制

用户确认“联系人优先 → 可确认的组织者兜底 → 信息不可见”，认为当前影响有限、非核心卡点。[Issue #1](https://github.com/arthurxbwang/roombeacon/issues/1) 按暂不实施关闭；现有业务仍展示组织者，联系人采集未实现。本项不再作为优先待办。接口结论、普通会议与北京110条预约实测及重开条件见[分析归档](archive/issue-1-meeting-contact-2026-09-22.md)，后续复用此记录，不重复分析。

## 型号模板已发布

- 按型号配置模板已上线：昼夜开关、语言、型号固定接线、后台匹配提示与异型号确认强制下发。BX68 已升级 APK 0.6.2 并应用 `bx68` 配置，在线、回执 5/5、无错误；343 间缓存及既有账号／模板／绑定／规则核对一致。本次经用户明确批准，先 Git bundle 部署验收，再推 GitHub。见[功能说明](device-model-templates.md)及需求 [#23](https://github.com/arthurxbwang/roombeacon/issues/23)。

## 下一阶段仍需完成

| 工作 | 当前边界 | 入口 |
|---|---|---|
| 日历自动核验与改期 | IT灯塔-Test 已接入一个来源日历，真实释放/改期联调及其他来源覆盖待完成 | [2: 专用日历映射、自动核验启用与改期真实联调](https://github.com/arthurxbwang/roombeacon/issues/2) |
| V5 剩余验收及长稳 | 每日重复有历史通过记录；周／月重复、故障及跨日场景仍有缺口 | [3: V5 剩余场景验收、周月重复与长稳](https://github.com/arthurxbwang/roombeacon/issues/3) |
| 飞书忙闲 504 诊断 | 已有限次只读重试；失败追踪与根因尚未闭环 | [4: 飞书忙闲 504 脱敏诊断与故障链路闭环](https://github.com/arthurxbwang/roombeacon/issues/4) |
| V6 实机验收 | 旧北京201接入、PoE/有线切换、72小时/7天及跨昼夜长稳待完成；当前台账只有1台设备 | [10: V6 设备接入、PoE/有线切换与长稳验收](https://github.com/arthurxbwang/roombeacon/issues/10) |
| 无 ADB 更新与恢复 | 已有配置回执；H5 更新回退、独立 APK 升级通道及现场恢复仍待完成 | [16: 无 ADB 运维](https://github.com/arthurxbwang/roombeacon/issues/16) |
| 认证后关闭网络 ADB | 已有厂家接口分析，仅规划；普通应用权限、维护规则及开关实测待完成 | [29: 自动关闭网络 ADB](https://github.com/arthurxbwang/roombeacon/issues/29) |
| DP72 人体存在传感器 | 协议评估已移交；Android 串口驱动和真实传感器集成尚未实现 | [5: DP72_DRT RS485 人体存在传感器只读接入](https://github.com/arthurxbwang/roombeacon/issues/5) |

总规划见[下一阶段计划](../plan/next-phase.md)。上述事项不能因为旧任务归档而标记完成；ESP32 仍仅规划。
