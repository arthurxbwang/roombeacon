# RoomBeacon 运维与仓库切换

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
