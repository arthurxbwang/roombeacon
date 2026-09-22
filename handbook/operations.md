# RoomBeacon 运维与仓库切换

> 2026-09-22源码已统一整合；本次仅合并与上传 GitHub，不执行部署。生产单房间签到配置及最新界面记录见[生产签到](../docs/production-v5-checkin-2026-09-22.md)，其余版本叙述为按日期保留的历史记录。门牌提前结束已关闭，旧接口认证后返回403。

> 2026-09-22生产Caddy/Nginx已启用异常重启，Caddy优先恢复持久化配置；实际覆盖文件、验证及回退见[修复记录](../docs/production-entry-recovery-2026-09-22.md)。备份接受VM方案；指标由用户后续配置；证书由自动化负责。

> 当前生产服务器为`roombeacon.thundersoft.com`，SSH使用`root`、私有`aw.key`和端口`8081`；部署目录`/data/roombeacon`。已验证登录主机`tsm-eed-ts-bj`。用户已完成部署；历史SSH80及首次部署待办不能覆盖当前状态，见[连接与历史部署记录](../docs/production-10.0.53.174.md)。

> 改期自动核验尚未部署。先完成日历权限与专用日历配置，再从准确GitHub SHA发布；启用和回退不能重置已保护记录。见[操作与权限清单](../docs/v5-reschedule-autoverify.md)。

> 2026-09-21 当前后端374db89、静态da63152，提前结束已关闭。连续三场非重复验收通过，只有IT灯塔-Test获V5写入资格；新预约仍需逐实例登记。见[验收记录](../docs/v5-retest-acceptance.md)，回退沿用[504修复记录](../docs/v5-three-bookings-verification.md)所列备份。下方旧版本为历史记录。

> 现有 Control 已按用户授权部署 V4/V5；实际目录、准确 SHA、配置覆盖及回退备份以 [2026-09-20 部署记录](../docs/v5-control-deployment.md)为准。以下未切换说明为此前基线，不覆盖该记录。

V5 默认关闭；独立环境启用、专用操作凭证、逐实例登记及暂停回退见 [V5 运维](../docs/v5-usage-verification.md)。历史 Control 曾在 IT灯塔-Test 实测非重复自动释放及当时的提前结束（此功能现已关闭），见[四场记录](../docs/v5-four-bookings-verification.md)。新增预约仍需在V5规则逐实例登记非重复；房间开关不会自动批准未知未来预约。

V5 保护协议 2 要求前后端同步升级：在中控明确选 V5 方案，旧无 owner 的策略按官方关闭处理，旧页面不能靠 GET 为释放保活。回退须先暂停写入、核对在途请求，再切服务器方案及页面；飞书后台的官方规则需单独恢复。当前虚拟房间写入验收状态见 [测试记录](../docs/v5-test-room-verification.md)。

> 版本: 0.1 | 作者: RoomBeacon Team | 更新日期: 2026-09-16

---

## 目录

- [1. 当前环境](#1-当前环境)
- [2. 本机配置与管理](#2-本机配置与管理)
- [3. 后续部署](#3-后续部署)

## 1. 当前环境

本次只迁移代码，不操作服务器，不保证历史服务器状态仍与会话记录完全一致。已知环境见 docs/handoff.md。旧操作手册完整保存在 docs/archive/argus-operations.md，仅作历史参考；其中蓝绿、按需查询、平台路由等早期说法不能覆盖当前独立架构。

## 2. 本机配置与管理

环境变量见 .env.example。环境文件权限 600；FEISHU_APP_ID/FEISHU_APP_SECRET 与 ROOM_DISPLAY_CONTROL_TOKEN/SECONDARY 由管理员在机器上填写。ROOM_DISPLAY_CHECKIN_URLS 是 JSON 字符串，键为唯一 room_id；真实链接不能入库。

主控主密码仍要求 >=32 字符，第二组按用户要求允许非空短密码，两者权限相同。修改后重启应用生效。设备凭证保存的是 SHA-256 摘要，不用主控密码替代。

```bash
# 已加载私有环境变量或设置 ROOMBEACON_ENV_FILE 后，在 backend/ 执行
../.venv/bin/python -m app.services.room_display_admin regions
../.venv/bin/python -m app.services.room_display_admin list --region 北京
../.venv/bin/python -m app.services.room_display_admin issue omm_目标ID
../.venv/bin/python -m app.services.room_display_admin revoke omm_目标ID
```

issue 会在终端显示一次设备凭证，属于管理员有意操作；不要把输出粘贴进 Git、截图或共享日志。

## 3. 后续部署

- scripts/room-display* 为兼容旧路径模板；scripts/roombeacon* 为新安装路径模板。都不是自动执行脚本，不同时启用两组采集服务。
- 新安装模板假定 `/opt/roombeacon`、`/opt/roombeacon-venv`、`/etc/roombeacon`、`roombeacon` 服务用户；需提前创建用户、虚拟环境和环境文件。
- 应用只监听 127.0.0.1:8088，Nginx 提供 HTTP 80；HTTPS 另行对接用户 ACBridge。
- Redis 只允许本机访问并启用 AOF。保留历史 rooms:* 凭证、快照和目录，迁移不能 flushall。

真正切换时先核对线上 SHA/服务/配置，准备准确 RoomBeacon GitHub 提交和旧版本回退，评审后执行：

1. 从 RoomBeacon GitHub 拉取已批准提交到新目录，独立构建并运行测试。
2. 停止旧采集应用，保留 Redis；复用配置或经审核迁到新配置路径。
3. 更新 systemd 与 Nginx 路径，nginx -t 后启动一套新服务。
4. 验证根页面、中控认证、设备认证、数据新鲜度、至少一个完整采集周期，以及 V1/V2/V3。
5. 失败时停止新应用，恢复旧目录/服务配置和基线 SHA；不清空 Redis。

保持浏览器 origin 和 API 路径可减少重新绑定；若更换域名/协议，设备需重新输入凭证。迁移到新仓库不表示此切换已获批准或执行。

## 组织者姓名补全（2026-09-17）

后台采集在组织者姓名缺失时，以现有飞书应用查询通讯录补全，成功缓存 5 分钟、失败缓存 1 分钟；按 App ID 隔离，不改变终端 API 或主题可见性。此节为 2026-09-17 历史实现记录；2026-09-22 生产已使用独立应用，最新权限核对及姓名异常边界见 [飞书应用权限清单](../docs/feishu-permissions.md)。生产姓名补全已复测，不能据此认定会议联系人回查方案也已实现。


## 重复实例试点登记（2026-09-21）

仅对白名单V5房间，通过既有管理员认证POST `/api/room-control/usage/{room_id}/verify`，请求包含当前`occurrence_id`、`policy_revision`及`recurring_verified: true`。与`non_recurring_verified`不能同时提交；旧非重复登记仍兼容。登记只对当前实例有效，不授权整个系列。未知单条0实例不能凭开始时间直接认定重复，必须有快照重复依据；发送前重复核对。Control现有非重复勾选不能用于重复预约，本轮由有截止时间的测试脚本调用新登记类型。

重复记录可能包含`release_scope=recurring_instance`和`release_original_time`。回退到不识别这些字段的旧版时，保持全局暂停，核对在途请求和记录后再决定恢复；不能把新版已登记记录交给旧版直接发送。部署、真实结果和回退目录见[重复实例验证](../docs/v5-recurring-release-verification.md)。
