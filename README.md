# RoomBeacon · 会议灯塔

**V6 集中管理已进入发布：飞书登录、管理员/只读权限、设备自动纳管、短码核对与远程配置。使用及真实验收边界见 [V6 文档](docs/v6-device-management.md)。**

维护入口：[当前状态](docs/current-state.md) · [下一阶段计划](plan/next-phase.md) · [GitHub 总规划](https://github.com/arthurxbwang/roombeacon/issues/6)。新任务从这些入口和最新 `main` 接续，历史会话用于追溯。

**当前源码包含 Android 外壳、V1—V5 页面、改期后重新签到及日历自动核验。生产是否启用以运行配置为准；目标日历授权与映射仍待完成。会议联系人规则已确认，用户接受现有限制并暂缓实施，Issue #1 已归档关闭；见[分析与接续条件](docs/archive/issue-1-meeting-contact-2026-09-22.md)。**

当前生产入口为 `roombeacon.thundersoft.com`，部署目录 `/data/roombeacon`。源码合并与服务器部署分别管理；本轮汇总源码不会自动部署或启用 V5 写入。运行版本与边界见[生产记录](docs/production-10.0.53.174.md)，日历核验准备见[修复说明](docs/v5-reschedule-autoverify.md)。

面向飞书会议室的独立门牌系统。服务器集中采集并缓存日程，终端显示会议状态、时间、组织者、后续会议与官方签到二维码。

**当前：Web V4 汇总现有门牌功能，V1/V2/V3 保留兼容；Android 0.2.4 按型号匹配两套样机的侧灯接线，BX68已切V5专用房间测试，ESP32-P4 仍仅规划。** 软件仓库版本暂为 0.1.0，界面版本与 APK 版本分别管理。

V5 签到和受控释放已实现，通过 `/?version=v5` 显式选择；配置默认关闭。最新生产记录仅对 IT灯塔-Test 开启，仍按具体实例核验，日历自动核验映射未配置；见[生产单房间记录](docs/production-v5-checkin-2026-09-22.md)。非重复和每日重复单实例的历史验收见[重复实例验收](docs/v5-recurring-release-verification.md)。门牌提前结束已关闭，周/月重复及长稳仍待验收；默认 V4 保持兼容。

V5 已增加平板主动保活、操作异常保护、待释放补确认和发送前核验；服务器逐房间选择官方／V5 方案，切页面不切换后台规则。专用虚拟房间已完成真实读取检查，本轮非重复预约实测见 [四场记录](docs/v5-four-bookings-verification.md)，历史预检见 [测试记录](docs/v5-test-room-verification.md)。

## 快速开始

需 Python 3.13、Node.js 20、独立 Redis。不要连接 Argus 生产 Redis。

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-test.txt
cp .env.example .env
chmod 600 .env
# 手动填写飞书应用及中控凭证，不要提交 .env
export ROOMBEACON_ENV_FILE="$PWD/.env"
cd backend
../.venv/bin/uvicorn app.room_display_main:app --host 127.0.0.1 --port 8088
```

另开终端：

```bash
cd frontend
npm ci
npm run dev
```

打开 Vite 给出的本地地址 `/control`，输入已配置主控凭证。设备端 `/?version=v4`；未指定时采用已保存的版本选择，没有保存选择则默认 V4。首次采集完成前会提示等待。

## 文档

- [独立飞书应用：11项权限与迁移清单](docs/feishu-permissions.md)

- [2026-09-22 全部分支整合与代码分析](docs/source-consolidation-2026-09-22.md)
- [项目交接：先读](docs/handoff.md)
- [系统架构与 API](docs/architecture.md)
- [界面与历史设计决策](docs/design.md)
- [开发与检查](handbook/development.md)
- [运行环境与部署迁移边界](handbook/operations.md)
- [Android / ESP 对照规划](plan/meeting-room-terminal-comparison.md)
- [开发资料索引：RK3568 SDK 摘要与 DP72 协议](docs/reference/README.md)
- [Android 外壳构建与样机测试](android/README.md)
- [Android 样机验证记录](docs/android-sample-verification.md)
- [Android 型号与灯控接线](docs/android-device-profiles.md)
- [北京-203 / 1080P 样机记录](docs/android-203-1080p-verification.md)
- [BX68 / IT灯塔-Test / V5 样机记录](docs/android-v5-test-room-verification.md)
- [2026-09-20 源码备份说明](docs/source-backup-2026-09-20.md)
- [源代码出处清单](docs/migration-manifest.json)
- [迁移验证](docs/migration-verification.md)

## 来源和维护边界

从 Argus `codex/meeting-room-standalone` 的 `c34a5614bdb5e86305e40deb0d5c36807ccd0b03` 抽取；没有导入整个 Argus Git 历史及无关平台功能。后续门牌修改只在 RoomBeacon 维护。

已有服务没有随仓库迁移而切换。历史目录、服务名和浏览器存储键保留兼容；详见交接文档。
公司提供的 ThunderSoft 品牌素材仅用于本项目，未新增开源许可证或第三方再授权承诺。
