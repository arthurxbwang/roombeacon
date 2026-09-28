# V7 发布与 W9TW7S 实施

2026-09-28 用户明确授权“部署上线，给 W9T W7S 部署实施”。关联 [Issue #31](https://github.com/arthurxbwang/roombeacon/issues/31)、[PR #32](https://github.com/arthurxbwang/roombeacon/pull/32)。

## 发布版本与范围

- 目标：`roombeacon.thundersoft.com`，独立服务器 `tsm-eed-ts-bj`，目录 `/data/roombeacon`。
- 前后端准确 SHA：`9f21d96a0698e918b9c61f81a0bb834df20541f4`；功能提交 `52f8ca91cc16aa003730d26a38019c4d1802eb41`。服务器直接从 GitHub fetch，按已审阅 `scripts/production/deploy-v6.sh` 构建、检查、备份、切换和探测。
- 发布前：`3359332b5b84343318693f7266d7966d3a950619`。发布脚本备份：`/data/roombeacon/backups/v6-20260928T060838Z`。
- 配置基线及实施证据：`/data/roombeacon/backups/v7-baseline-20260928T060743Z`，目录 700，JSON 600，留在生产私有目录。
- 当前仅注册一台设备 W9TW7S（BX68 / RK3568），绑定 IT灯塔-Test；只向该设备部署 V7 模板。APK 仍 0.7.0-debug、协议 3，未重新安装 APK。

## 配置与回执

| 项目 | 发布前 | 发布后 |
|---|---|---|
| 硬件模板 | `5052599fb3849c47c63c5570` v2 | 保持 |
| 软件模板 | `f7219baa3da9bd37414faa4d` v1 | `55b58f2c907fe345a12683ec` v1 |
| 软件名称 | 当前软件 · IT灯塔-Test | V7 品牌签到 · IT灯塔-Test · 5+5 分钟 |
| 设备配置／回执 | 7/7 | 8/8 |
| 房间配置 revision | 2 | 3 |
| 会前开放／会后宽限 | 10 / 10 分钟 | 5 / 5 分钟 |
| 释放补确认 | 60 秒 | 60 秒 |

部署记录 `5438ed9ebc4cb4d7fee1d542` 为 applied，设备在线、无错误，房间 policy_state=applied。保留 owner=v5、mode=auto、原业务主控、灯控接线、自动主题、中文及全部房间资格；未扩大单房间写入白名单。顶层 version=v6，presentation.display_version=v7，沿用原 APK 托管协议。

## 验收证据与边界

- 本地 npm ci、构建、Ruff 0.16.7、329 项后端（无跳过）、127 项 Chromium 通过。生产构建、Ruff 和 329 项后端再次通过，Redis 测试使用独立临时实例；两条依赖弃用警告不影响结果。
- 后端、Nginx、独立 Redis 正常；HTTPS 管理入口可用。匿名设备台账、门牌与签到读取均返回 401。
- 14:10:07 北京时间完整采集 343 间、18 批、失败 0；342 间 official/off，仅 IT灯塔-Test 为 v5/auto，写入白名单仍为 1。
- 设备原生回执 8/8，真实网页心跳 ready、策略版本匹配、年龄小于 10 秒。经已连接的 ADB 核对序列号并截图，物理 1920×1080、CSS 1280×720，三栏与时间轴完整，没有纵向截断。公司 GIF 的连续截图帧不同，V7 品牌面板实际显示；本次未开启新的 ADB 服务。
- 切换期间 14:15–14:30 预约已按旧策略生成 blocked/missed_window 记录，截止仍为旧记录 14:25；新策略不会重写旧记录。收敛后 can_confirm=false，实机显示保护提示，不出现签到按钮。后续新记录采用 5+5。此处未清除记录、伪造签到或释放资格，也未点击真实预约签到或删除预约。
- 全局暂停为 false；当前预约上的“自动释放已暂停”是既有 blocked 状态文案，不代表全局开关被关闭。未来预约仍需原有逐实例核验，不能把房间 release_enabled=true 视为全部预约均可释放。
- 本次证明上线、配置收敛和真实显示；未重新验收真实签到提交／飞书释放、16:10 实机或长稳。16:10 与双阶段倒计时边界由隔离浏览器测试覆盖。

## 回退

优先在当前 V7 服务下通过管理界面重新部署原硬件 v2＋原软件 `f7219baa3da9bd37414faa4d` v1，使用操作时最新设备／房间 revision，确认只有 W9TW7S 受影响。原软件同时恢复 10+10 规则；策略切换继续保护已有记录。若只回退外观，先发布规则保持 5+5、display_version=v6 的软件版本再部署。

完整服务回退前必须先部署不含 display_version 的原软件版本并等候真实回执，避免旧后端拒绝 V7 字段。然后依据 `/data/roombeacon/backups/v6-20260928T060838Z/backend.before` 与 `nginx.before` 恢复 current 和 Nginx，恢复备份的 dropin/v6.env（如确有配置差异），执行 nginx -t、systemctl daemon-reload、重启 roombeacon、重载 Nginx并验证 HTTPS、鉴权、采集和设备回执。回退目标为 `3359332b5b84343318693f7266d7966d3a950619`；此次 venv 未变化。

保留新的 SQLite 数据、账号、身份、模板和审计；不整库覆盖旧备份，不清 Redis，不重置预约保护记录。
