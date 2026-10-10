# RoomBeacon 当前状态

## 首装取消网段白名单（2026-10-10，PR #71已上线）

用户授权后，需求[#70](https://github.com/arthurxbwang/roombeacon/issues/70)经[PR #71](https://github.com/arthurxbwang/roombeacon/pull/71)合入并从GitHub上线准确应用 **`35ca0d9fb5954308f008932fb94cd02bd3776882`**。后台与新版现场助手取消固定IP／CIDR名单，旧值／参数兼容但不再拦截，任意站点RFC1918内网IPv4可检测；后台无法直达时使用当地现场助手。原管理员、ADB端口、正式APK和设备身份核验保持。

实际生产检测 `10.0.51.170` 返回200：`rk3568_r`／Android11，已有门牌应用，应到设备台账核对短码配置；未安装、启动或配置该设备。本地／生产590项后端、181项Chromium、构建／Ruff及准确页面资源检查通过。343间完整采集失败0，15条原预约、模板／设备／策略／来源及私有配置保持；BDC5ZS自动加载新H5、页面／灯控健康、2/2。15:45:57复核自动核验／释放true、暂停false。准确备份、回退至 `27b4b30` 和跨站点边界见[本次回执](production-install-no-allowlist-2026-10-10.md)及[操作说明](installation-delivery.md#跨网段与跨站点安装)。下方保留历史发布记录。

## 签到保密模板（2026-10-10，PR #68已上线）

用户授权后，需求#67经[PR #68](https://github.com/arthurxbwang/roombeacon/pull/68)合入并上线准确应用 **`27b4b3009b7001238636de50d1dafad75107e11f`**。仅新增“签到保密版”v1；原模板、草稿、已发布版本、设备和会议室配置逐条保持，未下发新模板。后台三款软件目录已验证，由用户自行推送测试设备。生产560项后端／181项Chromium、构建及Ruff通过；343间完整采集失败0、15条原预约及策略保持。BDC5ZS自动更新H5、页面／灯控健康、2/2保持，15:15实际复核自动核验／释放true、暂停false。选择方式、准确备份和回退见[上线回执](production-private-template-2026-10-10.md)及[模板说明](private-software-template.md)。下方按日期保留历史生产记录。

## 静态发布检查（2026-10-10，PR #65已上线）

当前准确应用为 **`e0e5926484489298f74635190e2eb530390b309b`**。发布过程在私有umask下验证公开dist权限自动处理，并通过本机Nginx和外网检查准确页面版本及JS／CSS资源；生产556项后端、162项Chromium通过。真实设备、开关恢复与准确回退见[本次回执](production-static-gate-2026-10-10.md)。本轮业务／前端／Android源码及配置与上一应用相同，日历解析仍只为IT灯塔-Test启用，真实业务矩阵和72小时观察继续#2／#3。

13:45实际复核：BDC5ZS已自动加载新H5、页面／灯控健康、配置2/2，原18条预约与稳定配置保持；343份新鲜快照及来源配对，自动核验／释放均true、暂停false。无需ADB操作或APK更新。

## 跨组织者日历修复（2026-10-10，已上线）

用户确认[PR #64](https://github.com/arthurxbwang/roombeacon/pull/64)合并并授权部署，准确应用 **`3a527efecd8d0fb86f2e4e269a266087489ba7ff`** 已从GitHub上线。只对IT灯塔-Test启用 `ROOM_DISPLAY_USAGE_ORGANIZER_SOURCE_ROOM_IDS`，按每场组织者解析日历并在发送前固定来源重查；原白名单及固定映射保持。生产543项后端及3项定向Chromium回归通过；343间完整采集失败0，18条原记录、身份、策略和配置保持。此前两场404／193001预约已由新代码通过真实只读核验，原blocked未改写。准确回执、开关恢复与回退见[发布记录](production-calendar-source-2026-10-10.md)。

Ruff 0.16.7、后端543项、`npm ci`／隔离构建、Chromium162项通过，均无跳过；新增67项后端和3项浏览器回归，完整HTTP链路9项可由脚本单独复验。生产另有2条上游弃用提示，npm依赖审计原有17项（2中危、15高危）仍待发布依赖审查。本轮修复公开静态产物权限后，BDC5ZS实际H5为 `3a527ef`、页面／灯控健康、配置2/2，13:14恢复释放；APK保持0.7.1。发布脚本权限及页面探针改进、13项新增回归随回执提交，尚不在该应用SHA中。

真实3人至少6场预约、正式来源类型矩阵及72小时观察仍待#2／#3；本轮只读核验不代替真实自动释放闭环。详见[实现／回退](calendar-source-qualification.md)及[原计划](../plan/calendar-source-release-readiness.md)。下方09:12生产核查是当时快照，以最新发布记录为准。

## 开始后新增预约窗口修复（2026-10-10，已上线）

#61／[PR #62](https://github.com/arthurxbwang/roombeacon/pull/62) 已上线应用 `ed90c9fea8c573414e1745ccb8689316af4517ea`。连续完整采集及健康监控中出现的已开始新预约，获得一次固定签到窗口（当前 5 分钟，不超过结束）；刷新不延期，故障恢复和旧保护记录不重新授权。V7 对不可签到的保护状态提示联系管理员。476 项后端／159 项 Chromium、生产两项定向浏览器回归通过；343 间新鲜完整采集失败 0，原 17 条记录、策略及设备配置保持。当前来源为 primary/free_busy_reader，真实新增预约签到／释放闭环及来源覆盖继续 #2／#3。准确验证和回退见[发布回执](late-booking-checkin.md#生产发布回执2026-10-10)。

09:25 BDC5ZS 自动加载新 H5 `ed90c9f`，页面 ready／灯控 ok、正式 APK 0.7.1、身份和 2/2 回执保持；无需安装 APK 或下发新配置。

## 签到版未释放核查（2026-10-10，只读）

09:12核查时生产为`9314125`。IT灯塔-Test今天09:00场已在08:56:42正常进入监控，但固定来源日历查询返回404／193001，实例未核验，09:05保护保留。09:17已确认根因：昨天13:00及今天09:00两场属于另一位组织者的主日历B，后台却固定查询历史来源A；相同日程ID在B读取200、时间完全匹配，现有核验函数也通过。全局释放／自动核验已开、未暂停，心跳及缓存正常；本问题需按预约来源覆盖，不能由#61开始后新增窗口修复代替。生产准确源码相关154项隔离回归通过、无跳过；未部署、改配置或操作预约。见[核查与测试记录](checkin-release-diagnosis-2026-10-10.md)。

## PR #55 与正式 APK 覆盖升级（2026-10-09，已上线）

#52／[PR #55](https://github.com/arthurxbwang/roombeacon/pull/55) 已处理最新 main 的 6 处冲突，合入并上线准确应用 `9314125493b71278de87ff3635aafdbae1df253a`。BDC5ZS 已通过同签名 ADB 覆盖由 0.7.0 升至正式 0.7.1（11），应用 UID／首次安装时间、原设备身份、2/2 配置和主控保持；新回执页面 ready、灯控 ok，真实 H5 版本为该 SHA，WebView 106.0.5249.79。原策略和 17 条记录保持，343 间完整采集失败 0；后端 446、Chromium 158、Android31项及构建／签名检查通过。后台自动升级通道未实现，默认首装包仍0.7.0。#41／PR #42 仍未合并，其他分支和历史记录不改。见[冲突评估、真实升级与回退](production-native-health-upgrade-2026-10-09.md)。

## 模板收敛与设备删除（2026-10-09，已上线）

[#56](https://github.com/arthurxbwang/roombeacon/issues/56) 经 PR #57／#58 合入并发布，最终生产应用 `3d0b1e1958c4961b55ecc3ed8910f901f073cfe3`。硬件仅 BX68 13.3 寸 1080P／旧款 10.1 寸，软件仅签到／未签到；未签到版保留飞书官方二维码逻辑，当前生产尚无对应链接配置。管理员删除需二次确认，只读拒绝；真实打开并取消、代理与鉴权检查通过，未删除真实设备。BDC5ZS 正式 APK 0.7.0、在线 2/2、主控心跳健康，W9TW7S 仍离线 11/10；原配置、规则及 17 条记录保持，343 间完整采集失败 0。另有 #52／PR #55 与 #41／PR #42 两个本地分支未合并，均有冲突。准确验证、分支盘点及回退见[上线回执](production-catalog-cleanup-2026-10-09.md)，操作见[说明](catalog-device-cleanup.md)。

## 正式样机绑定与原生回执修复（2026-10-08）

用户要求后，BDC5ZS 已绑定 IT灯塔-Test 并接替业务主控，硬件 v2／软件 v2／V7，配置回执 2/2、无错误、真实网页业务心跳正常；旧 W9TW7S 离线且不再主控。仅本样机的厂商启动项已由旧 debug 包改为正式包并读回。生产仍是 `5b9fe3c`／正式 APK 0.7.0，343 份缓存有效、预约记录和策略保持。

#52 的灯控错误恢复与独立页面健康回执已形成修复，配套 APK 0.7.1 尚未发布或安装；验证、生产操作及回退见[本轮记录](android-runtime-health.md)。剩余事项已归入 GitHub #10／#16／#29／#2／#3／#4／#5／#54，由用户按后续节奏处理。下方待配置与旧主控回执为此前阶段记录。

## 首装与交付后台（2026-10-08，已真实装机）

当前生产应用为 PR #50 的 `5b9fe3c702f4e7a36d3ea535ceaa3c7d3602ba24`。默认入口是“输入 IP → 检测 → 确认初始化”；现场助手仅作为服务器无法连接设备时的备用方式。用户批准建立项目专用签名，正式 APK 0.7.0（10）已准备并私密备份签名；后台默认包缺失和误导指引已解决。此前首装实现、IP 流程和排版分别见 PR #44／#46／#47／#49。

用户卸载旧 APK 后，样机 `10.0.51.221` 已经真实后台完成正式安装、启动和注册，原生屏幕短码核对后关联为 **BDC5ZS**。新设备在线待配置，下一步选择会议室；原 W9TW7S 因卸载离线，原台账和配置保留，不能沿用历史“旧设备心跳健康”的结论。343 间采集正常，原 16 条记录与策略保持。后端 403 项、Chromium 146 项、Android 单测／lint／构建及真实签名校验通过。

准确 SHA、签名保管、现场证据与回退见[操作说明和首装回执](installation-delivery.md#正式包首装生产回执2026-10-08)。当前仅放行样机 `/32`；批量网段、新批次授权、关闭 ADB／PoE 冷启动、2GB 长稳和无 ADB 更新继续 #16／#29／#10。真实首装通过不等于完整交付验收通过。

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
| 日历自动核验与改期 | IT灯塔-Test 已启用按组织者解析来源，两场历史失败只读核验通过；真实多组织者释放／改期及其他来源覆盖待完成 | [2: 专用日历映射、自动核验启用与改期真实联调](https://github.com/arthurxbwang/roombeacon/issues/2) |
| V5 剩余验收及长稳 | 每日重复有历史通过记录；周／月重复、故障及跨日场景仍有缺口 | [3: V5 剩余场景验收、周月重复与长稳](https://github.com/arthurxbwang/roombeacon/issues/3) |
| 飞书忙闲 504 诊断 | 已有限次只读重试；失败追踪与根因尚未闭环 | [4: 飞书忙闲 504 脱敏诊断与故障链路闭环](https://github.com/arthurxbwang/roombeacon/issues/4) |
| V6 实机验收 | 旧北京201接入、PoE/有线切换、72小时/7天及跨昼夜长稳待完成；当前台账只有1台设备 | [10: V6 设备接入、PoE/有线切换与长稳验收](https://github.com/arthurxbwang/roombeacon/issues/10) |
| 无 ADB 更新与恢复 | 已有配置回执；H5 更新回退、独立 APK 升级通道及现场恢复仍待完成 | [16: 无 ADB 运维](https://github.com/arthurxbwang/roombeacon/issues/16) |
| 认证后关闭网络 ADB | 已有厂家接口分析，仅规划；普通应用权限、维护规则及开关实测待完成 | [29: 自动关闭网络 ADB](https://github.com/arthurxbwang/roombeacon/issues/29) |
| DP72 人体存在传感器 | 协议评估已移交；Android 串口驱动和真实传感器集成尚未实现 | [5: DP72_DRT RS485 人体存在传感器只读接入](https://github.com/arthurxbwang/roombeacon/issues/5) |

总规划见[下一阶段计划](../plan/next-phase.md)。上述事项不能因为旧任务归档而标记完成；ESP32 仍仅规划。
