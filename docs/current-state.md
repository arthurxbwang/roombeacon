# RoomBeacon 当前状态

更新：2026-09-24。本页是新任务的状态入口；详细历史保留在各次验证记录中。当前生产已按用户授权发布V6，准确版本与实机证据见下方发布记录。

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

- Android WebView 外壳、型号灯控与恢复能力；BX68 样机当前 APK 0.7.0-debug，模板配置回执 7/7。
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
| 日历自动核验与改期 | 代码及隔离回归已存在，生产日历映射为空，真实联调待完成 | [2: 专用日历授权、自动核验与改期联调](https://github.com/arthurxbwang/roombeacon/issues/2) |
| V5 剩余验收及长稳 | 每日重复有历史通过记录；周／月重复、故障及跨日场景仍有缺口 | [3: V5 剩余场景验收、周月重复与长稳](https://github.com/arthurxbwang/roombeacon/issues/3) |
| 飞书忙闲 504 诊断 | 已有限次只读重试；失败追踪与根因尚未闭环 | [4: 飞书忙闲 504 脱敏诊断与故障链路闭环](https://github.com/arthurxbwang/roombeacon/issues/4) |
| DP72 人体存在传感器 | 协议评估已移交；Android 串口驱动和真实传感器集成尚未实现 | [5: DP72_DRT RS485 人体存在传感器只读接入](https://github.com/arthurxbwang/roombeacon/issues/5) |

总规划见[下一阶段计划](../plan/next-phase.md)。上述事项不能因为旧任务归档而标记完成；ESP32 仍仅规划。
