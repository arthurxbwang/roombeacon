# 生产入口异常恢复修复（2026-09-22）

用户明确授权修复异常自动恢复。目标为 `root@roombeacon.thundersoft.com:8081`，应用目录 `/data/roombeacon`，应用源码保持 `3b0bf39cdfdb92e421882444615f8ab7bcb76c8c`。本次仅修改系统服务覆盖配置，不重新部署业务代码。

## 最终配置

| 单元 | 覆盖文件 | 生效配置 |
|---|---|---|
| Caddy | `/etc/systemd/system/caddy.service.d/50-roombeacon-recovery.conf` | `Restart=on-failure`、`RestartSec=5s`，60秒内最多启动5次；`ExecStart`增加`--resume`。 |
| Nginx | `/etc/systemd/system/nginx.service.d/50-roombeacon-recovery.conf` | `Restart=on-failure`、`RestartSec=5s`，60秒内最多启动5次。 |

配置模板保存在 `scripts/production/caddy-recovery.conf` 和 `scripts/production/nginx-recovery.conf`。主动`systemctl stop`不自动拉起；连续失败触发启动限额后应排查原因，再执行`systemctl reset-failed <服务>`并启动。

Caddy的证书由ACBridge通过管理API动态加载。增加`--resume`后，下一次启动优先读取已持久化的配置，保留加载的证书和路由；没有autosave文件时仍回退到`/etc/caddy/Caddyfile`。当前autosave文件可由caddy用户读取，实际持久化配置已通过`caddy validate`。规则依据[Caddy命令行说明](https://caddyserver.com/docs/command-line#caddy-run)。

## 回归与线上验证

修复前先编写 `scripts/production/test_entry_recovery.py`：读取真实生产单元的重启策略，在独立回环端口启动临时Caddy/Nginx，随后仅终止临时主进程。Caddy用管理API写入独立配置，验证重启后能否保留。

- 修改前：Caddy、Nginx均未自动恢复，`NRestarts=0`，两项回归按预期失败。
- 修改后：两个临时实例均自动恢复，`NRestarts=1`，Caddy动态配置恢复通过。
- 临时单元、监听端口和测试目录均已清理；测试没有使用生产证书、凭证或业务数据。
- `systemd-analyze verify`和`nginx -t`通过；对实际Caddy持久化配置的验证通过。
- 只执行`systemctl daemon-reload`使策略生效，未重启正在运行的生产服务。Caddy主进程147733、Nginx主进程69002保持，生产`NRestarts=0`。
- HTTPS首页与Control返回200，无凭证主控请求401，正确主控请求200并返回343间目录。应用采集继续运行。
- 回归脚本Ruff通过。本次没有业务源码变更，不重复运行整套前后端回归。

本轮证明策略在隔离实例中能从真实进程崩溃恢复，并确认生产已加载同一策略；未强制中断生产服务或执行整机重启演练。

## 回退

备份目录：`/data/roombeacon/backups/20260922-151717-entry-recovery/`，权限700，保存原单元、原属性、校验日志、变更说明及验证结果。两个覆盖文件新增前均不存在。

回退只删除本轮两个`50-roombeacon-recovery.conf`并执行`systemctl daemon-reload`。不要删除其他覆盖文件，不修改Caddy证书、Nginx路由或应用环境；回退重启策略无需主动重启服务。

## 用户确认的交付安排

- **备份**：采用VM层备份，已按用户要求记录并接受；不追加应用层备份要求，也不宣称本轮执行了恢复演练。
- **指标采集**：用户后续单独配置，本轮不实施、不作为本轮阻塞项。
- **证书续期**：由既定自动化负责，已记录；保留ACBridge，不新增另一套续期机制。
- **姓名补全**：用户调整权限后，两位对照用户已成功取得姓名；原失败对象改为41012（用户ID无效），待核对账号与上游身份数据。见[权限复测](feishu-permissions.md)。服务器侧未修改飞书后台授权。
