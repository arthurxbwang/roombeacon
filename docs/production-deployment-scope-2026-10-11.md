# 单会议室部署范围提示发布回执

2026-10-11（北京时间）；需求 [#85](https://github.com/arthurxbwang/roombeacon/issues/85)，修复 [PR #86](https://github.com/arthurxbwang/roombeacon/pull/86)。沿用用户本轮修改与上线授权，仅发布后台网页提示。

## 修改与实际范围

单设备部署复选框改为“仅更换所选会议室的软件模板，并同步本设备及该会议室其他已激活门牌”，下方写明“其他会议室的软件模板和版本不随本次部署更新”。会议室筛选数量说明为可选范围，预览显示所选房间名称和受影响门牌数量。

原有接口和部署逻辑保持：仅发送一个所选 `room_id`；更换该房间软件时，同步当前设备及同房间其他已激活门牌，包括离线设备。勾选和范围检查不提交配置，只有“确认部署”才提交；离线设备联网并回执后才确认生效。设备迁移仍可能清理原房间主控关联，因此文案仅承诺其他会议室的软件模板和版本不随之更新。

## 准确版本与发布过程

| 项目 | 发布后 |
| --- | --- |
| 环境 | `roombeacon.thundersoft.com`，`tsm-eed-ts-bj`，`/data/roombeacon` |
| 网页准确 SHA | `921536a90274fc24f5687f747f9a7e063ac20fa9` |
| Nginx 静态 root | `/data/roombeacon/releases/921536a90274fc24f5687f747f9a7e063ac20fa9/frontend/dist` |
| 后端准确 SHA | `3aaf5ee7dd91f0239d75675ee6dad8985f22687d` |
| Python 环境 | `/data/roombeacon/venvs/background-3aaf5ee7dd91f0239d75675ee6dad8985f22687d` |
| 后端进程 | PID `2829848`；启动时间 `2026-10-10 20:04:27 CST`，发布前后相同、active |
| 私有发布备份 | `/data/roombeacon/backups/deployment-scope-85-20261011` |

从 RoomBeacon GitHub 获取已合并准确 SHA，核对后端、Android 和生产脚本与原应用无差异，使用 `git archive` 建立隔离目录并构建。保存原 Nginx、版本及进程基线，保留旧哈希静态资源；公开 dist 使用 0755／0644，并以 Nginx 用户验证文件可读。

仅替换现有 Nginx 的唯一静态 `root`，`nginx -t` 后 reload，没有切换 `current`／`venv-current` 或重启后端，没有提交会议室、模板或设备部署。APK 继续使用原正式包。准备和发布脚本未读取业务数据库、私有环境或 Redis；验收使用公开静态资源和服务进程信息。

## 验证证据

- 先在旧网页构建复现新的范围提示缺失；`npm ci`、类型检查、隔离构建、10 项相关 Chromium、199 项前端全量、最终单项部署回归及 `git diff --check` 通过。
- 1440×1000、390×844 本地隔离模拟复核，新复选框和解释完整可见，没有页面或面板横向溢出；模拟不代表真实设备验收。
- 生产隔离构建与 10 项部署相关浏览器回归通过。所有业务 API 使用测试夹具，未向生产接口提交部署。
- 发布前后后端 PID／启动时间／状态、应用及 Python 环境链接保持；只修改 Nginx 静态 root。
- 本机 `http://127.0.0.1:8080` 和正式 HTTPS 的首页、托管入口、`/control`、`/control/legacy` 均返回准确新 SHA，入口 JS／CSS 状态与类型通过。
- 09:40:26 正式 HTTPS `/control` 返回 200；入口 `/assets/main-room-display-CFl6Kggm.js` 含全部新范围提示，并与本地已验证 JS 逐字节一致，SHA-256 为 `2d15e6fb714f0e5318db9b08c56e685fd9f3c32859e4fcd7672e3aedb419a600`。

本次没有执行真实会议室部署或新增 APK 实机测试，也未将业务数据快照导出到本地。用户刷新后台即可看到新提示。

## 仅网页回退

旧网页 SHA 为 `3aaf5ee7dd91f0239d75675ee6dad8985f22687d`，原 root 为 `/data/roombeacon/current/frontend/dist`。在上述生产服务器执行：

```bash
cp /data/roombeacon/backups/deployment-scope-85-20261011/nginx.before /etc/nginx/sites-available/roombeacon
nginx -t && systemctl reload nginx
/data/roombeacon/venv-current/bin/python /data/roombeacon/current/scripts/production/static_release.py verify http://127.0.0.1:8080 3aaf5ee7dd91f0239d75675ee6dad8985f22687d
/data/roombeacon/venv-current/bin/python /data/roombeacon/current/scripts/production/static_release.py verify https://roombeacon.thundersoft.com 3aaf5ee7dd91f0239d75675ee6dad8985f22687d
```

本次回退只恢复静态 Nginx 配置，不恢复数据库、不重启后端或切换 Python 环境。旧资源和旧目录保留。
