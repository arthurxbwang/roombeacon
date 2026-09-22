# RoomBeacon 当前状态

更新：2026-09-22。本页是新任务的状态入口；详细历史保留在各次验证记录中。生产信息依据已保存的发布回执，本次整理没有重新部署或改变运行配置。

## 版本与维护入口

| 用途 | 标签 | 提交 |
|---|---|---|
| 完整源码整合基线 | `baseline-2026-09-22` | `15c1652dc8adf43adf1e7231689189c9d6349db1` |
| 已记录的生产后端 | `production-backend-2026-09-22` | `3b0bf39cdfdb92e421882444615f8ab7bcb76c8c` |
| 已记录的生产前端 | `production-frontend-2026-09-22` | `43d8b8f18d5569940cecce53217e7822459191e1` |

唯一维护仓库为 [arthurxbwang/roombeacon](https://github.com/arthurxbwang/roombeacon)，后续开发从最新 `main` 创建短期 `codex/` 分支。上述基线标签固定旧提交，后续文档或代码合并不移动标签。源码基线与生产前后端版本分别管理。

生产域名 `roombeacon.thundersoft.com`，SSH 8081，目录 `/data/roombeacon`；私钥和凭证仅保存在私有环境。运行和回退依据[生产签到记录](production-v5-checkin-2026-09-22.md)。

## 已完成

- Android WebView 外壳、型号灯控与恢复能力；当前已记录的 BX68 样机使用 APK 0.2.4-debug。
- V1—V5 页面及主控；提前结束已关闭，兼容接口认证后固定拒绝。
- 当前生产仅 IT灯塔-Test 开启 V5 签到与受控释放，其余 342 间不扩大写入权限。未来预约不因房间开关而自动获得释放资格。
- Caddy／Nginx 异常恢复已修复；接受 VM 层备份，指标由用户后续配置，证书续期由既定自动化负责。
- 全部历史分支源码已经整合，基线后端 250 项、前端 84 项、Android 11 项测试及对应构建检查通过。详见[整合报告](source-consolidation-2026-09-22.md)。

## 下一阶段仍需完成

| 工作 | 当前边界 | 入口 |
|---|---|---|
| 会议联系人统一显示 | 方案已确认，尚未编码；目标日历定位与读取权待补齐 | [1: 会议联系人统一显示与身份来源核验](https://github.com/arthurxbwang/roombeacon/issues/1) |
| 日历自动核验与改期 | 代码及隔离回归已存在，生产日历映射为空，真实联调待完成 | [2: 专用日历授权、自动核验与改期联调](https://github.com/arthurxbwang/roombeacon/issues/2) |
| V5 剩余验收及长稳 | 每日重复有历史通过记录；周／月重复、故障及跨日场景仍有缺口 | [3: V5 剩余场景验收、周月重复与长稳](https://github.com/arthurxbwang/roombeacon/issues/3) |
| 飞书忙闲 504 诊断 | 已有限次只读重试；失败追踪与根因尚未闭环 | [4: 飞书忙闲 504 脱敏诊断与故障链路闭环](https://github.com/arthurxbwang/roombeacon/issues/4) |
| DP72 人体存在传感器 | 协议评估已移交；Android 串口驱动和真实传感器集成尚未实现 | [5: DP72_DRT RS485 人体存在传感器只读接入](https://github.com/arthurxbwang/roombeacon/issues/5) |

总规划见[下一阶段计划](../plan/next-phase.md)。上述事项不能因为旧任务归档而标记完成；ESP32 仍仅规划。
