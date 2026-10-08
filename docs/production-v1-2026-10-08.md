# RoomBeacon 1.0.0 正式版上线记录

2026-10-08 用户明确要求删除保护说明行，将全部修改一并推送 PR，发布正式版本上线。

## 准确版本与范围

- 需求 [#34](https://github.com/arthurxbwang/roombeacon/issues/34)，[PR #35](https://github.com/arthurxbwang/roombeacon/pull/35) 已合入 main。
- 正式应用 SHA：`6ac52034fb3473ecbcd67ed20c99c619a3fdf423`，与已验证功能分支树一致。[Release v1.0.0](https://github.com/arthurxbwang/roombeacon/releases/tag/v1.0.0) 指向该 SHA，非预发布。
- 当前生产：`roombeacon.thundersoft.com`、主机 `tsm-eed-ts-bj`、`/data/roombeacon/current` 指向该 SHA。从 GitHub 拉取，按仓库已校验部署脚本构建、测试、备份、切换及探测；未复制开发机应用源码。
- 发布前应用：`9f21d96a0698e918b9c61f81a0bb834df20541f4`。应用版本 1.0.0，门牌界面 V7；APK 0.7.0-debug 和原硬件保持。本次正式发布为前后端，不发布新的 Android APK。

## 配置与真实回执

| 项目 | 发布前 | 发布后 |
|---|---|---|
| 软件模板 | `55b58f2c907fe345a12683ec` v1 | 同模板 v2，正式签到 |
| 硬件安装 | `5052599fb3849c47c63c5570` v2 | 保持 |
| 设备配置/回执 | 8/8 | **9/9**，无错误 |
| 房间 revision | 3 | 4 |
| 提前/宽限 | 5/5 分钟 | 保持 |
| 补签到 | 60 秒 | **0 秒** |
| 全局暂停 | true | **false** |

- 仅为 W9TW7S/IT灯塔-Test 显式部署；软件 v1 不可覆盖，新增 v2「V7 正式签到 · IT灯塔-Test · 5+5 分钟」。部署记录 `621fd9cc2d2c24c149469c5d` 为 applied；房间 policy_state=applied、策略 revision=`a659662b0c837bdd6abd0d2e`。
- 原房间官方规则核对及释放资格保持；在真实托管 ready 心跳和策略一致、后台 terminal_healthy=true 后解除全局暂停，release_enabled=true。policy 与 paused 的 TTL 均为 -1。
- 逐房间只读核对：343 间中 342 间 official/off、1 间 v5/auto；服务器写入白名单仍仅该房间。日历映射未扩大，未来预约仍逐实例核验，不自动授予整系列资格。
- 17 条既有 blocked 记录状态全部保持，不重置保护或授予资格、不代用户签到。9:45 当次此前未签到，继续保留；签到恢复过程见 [恢复与最终规则](v7-final-checkin-2026-10-08.md)。

## 验证与边界

- 本地 345 项后端、129 项 Chromium，生产再次 345 项后端全部通过，无跳过；Ruff 0.16.7、npm ci、TypeScript/Vite 构建、`git diff --check` 通过。生产两条依赖弃用警告不影响结果。Redis 测试为独立临时 Unix socket，SQLite 临时，飞书 mock。
- 10:21:32 北京时间完成完整采集：343 间、18 批、失败 0，新鲜缓存有效。后端、Nginx、Redis 正常。
- 正式 HTTPS 页面 release meta 为准确部署 SHA；当前 JS 资源返回 200 且不含删除的保护说明。匿名设备台账、日程和签到读取均为 401。
- 真实设备配置回执 9/9、在线、无错误；真实 H5 心跳年龄约 4 秒、operation_state=ready、后台托管身份核验通过，网页视口元数据仍为 1280×720。
- 删除的是「本次预约受保护，不会自动释放」说明行；内部保护、签到权限、截止判断和未知状态保持。零补签到到点关闭操作，后台继续真实在线回执与预约核验，核验耗时不算补签到窗口。
- 本次未使用 ADB、新装 APK、点击真实签到或调用飞书释放；真实配置/心跳与公开资源核对不等于逐场签到/释放、物理屏幕截图或长稳验收。剩余真实业务验收沿 Issue #2/#3/#10 继续。

## 私有备份与回退

- 应用脚本完整备份：生产 `/data/roombeacon/backups/v6-20261008T022000Z`。
- 单房间发布前及发布/应用后证据：生产 `/data/roombeacon/backups/v1-baseline-20261008T021302Z`，目录 700、JSON 600。凭证、真实 session_id 及私有原件不进入 Git。
- 回退应用目标：`9f21d96a0698e918b9c61f81a0bb834df20541f4`。先暂停并核对在途释放，在当前后端部署原软件 v1（补签到 60 秒），等待设备真实回执；旧后端不能读取补确认 0 的策略。
- 然后按完整备份恢复 current 和 Nginx，执行配置检查、服务重启与 HTTPS/鉴权/采集探测。保留 SQLite/AOF、账号、审计、模板版本和预约保护，不整库覆盖、不清 Redis；持久策略继续保留。
