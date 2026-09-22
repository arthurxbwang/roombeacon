# 新生产服务器部署（2026-09-22）

> 最新只读交付检查：HTTPS、343间真实采集及主控鉴权已通过；备份/告警、入口自恢复、证书续期验证和姓名补全范围仍需收尾。现状以[交付检查](production-handover-audit-2026-09-22.md)为准，以下初次部署结果为历史记录。

## 当前连接信息（用户更新，2026-09-22）

- 用户已确认自行完成服务器部署；以下首次部署时的服务状态、凭证待办和8080网络问题仅为历史记录，不代表当前状态。
- 当前生产域名：`roombeacon.thundersoft.com`；原内网地址记录为`10.0.53.174`，部署目录仍为`/data/roombeacon`。
- SSH入口：`root@roombeacon.thundersoft.com:8081`，使用私有`aw.key`。已真实登录验证，用户名`root`，主机名`tsm-eed-ts-bj`。
- 本次只核对SSH身份，未修改服务器配置，也未重新验证网站协议、端口或业务状态。后续连接使用8081，历史SSH80不再作为当前入口。

```bash
ssh -p 8081 -i /root/.ssh/aw.key root@roombeacon.thundersoft.com
```


## 授权与版本

用户明确授权以 `root@10.0.53.174:80` 部署至 `/data/roombeacon`。这是独立新环境，不自动切换旧 Control、平板绑定、域名、飞书应用或会议室释放规则。

应用源码基线：`3b0bf39cdfdb92e421882444615f8ab7bcb76c8c`，来自 RoomBeacon GitHub 的 `codex/v5-control-release`。服务器直接从 GitHub 拉取；本机未提交工作区不作为发布输入。新服务器的配置模板位于 `scripts/production/`，部署记录与应用 SHA 分开管理。

## 路径与端口

| 项目 | 路径或地址 |
|---|---|
| SSH | `root@10.0.53.174:80`，使用本机私有 `aw.key` |
| 网站 / 主控 | `http://10.0.53.174:8080/`、`/control` |
| GitHub 检出 | `/data/roombeacon/repository` |
| 发布目录 | `/data/roombeacon/releases/<应用SHA>` |
| 当前发布软链接 | `/data/roombeacon/current` |
| Python 环境 | `/data/roombeacon/venvs/<应用SHA>`、`venv-current` |
| Python / Node 工具 | `/data/roombeacon/tools` |
| 私有环境 | `/data/roombeacon/shared/config/{service,feishu,control}.env` |
| 独立 Redis 数据 | `/data/roombeacon/shared/redis` |
| 安装与验证记录 | `/data/roombeacon/backups` |
| 后端 | `roombeacon.service`，`127.0.0.1:8088` |
| Redis | `roombeacon-redis.service`，`127.0.0.1:6380` |

SSH 已占用80端口，Nginx使用8080；保留SSH监听配置。用户已确认先使用8080，并稍后接入域名和HTTPS；尚未进行正式终端切换。

## 配置与启动

- 环境目录权限700，环境文件600，仅root读取；systemd读取后传入非特权 `roombeacon` 进程。凭证不写入Git、部署日志或对话。
- 新环境保留 `ROOM_DISPLAY_*`、`rooms:*`、`argus_room_*` 命名；Redis与旧服务器隔离，不复制旧缓存冒充新采集成功。
- `ROOM_DISPLAY_USAGE_ENABLED=false`、`ROOM_DISPLAY_USAGE_WRITES_ENABLED=false`，释放白名单及自动核验日历映射为空。启用V5或迁移旧释放策略需单独明确范围和核验结果。
- 首次生成独立随机主控凭证，保存在 `control.env`。不会替换旧Control密码或撤销旧设备凭证。
- 飞书凭证为空时，systemd的 `ExecCondition` 跳过后端启动，避免用空凭证调用上游；Nginx静态页仍可服务，API返回503，不提供伪造目录或会议状态。
- Redis仅本机监听，AOF `everysec` 加RDB持久化，最大内存2GB，采用 `noeviction` 以免静默淘汰业务记录。

管理员在服务器填入新应用的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 后执行：

```bash
systemctl start roombeacon
systemctl is-active roombeacon roombeacon-redis nginx
```

用户已明确采用新的灯塔应用，稍后在服务器填写凭证；未从旧服务器读取或迁移私有配置。新应用权限见 [清单](feishu-permissions.md)。首次真实采集后需核对完整周期、目录数量、缓存新鲜度、主控鉴权，以及至少一台实机的设备鉴权和失联状态；未完成这些项目不能声称生产业务验收通过。

## 首次部署回退

此机没有旧RoomBeacon版本。首次回退为：

```bash
systemctl disable --now roombeacon
systemctl disable --now nginx
systemctl disable --now roombeacon-redis
```

保留 `/data/roombeacon`、私有配置、Redis持久化和安装记录，不删数据、不执行 `FLUSHALL`、不触及SSH或旧服务。后续更新前记录 `current`、`venv-current` 的准确目标并备份配置；如已启用写入，先暂停并核对在途请求，再同时恢复应用与虚拟环境软链接，重启应用并验证Nginx。不得把新格式预约记录直接交给不兼容旧版发送。

## 运行环境

服务器Ubuntu 22.04.5，Python 3.13.15、Node.js 20.20.2、Nginx 1.18.0（Ubuntu安全更新包）、Redis 6.0.16。Node下载按官方SHA-256清单校验；Python由uv安装，Python/前端应用依赖按仓库锁定文件安装。系统时间为Asia/Shanghai且NTP同步。

## 本轮结果

- GitHub准确应用SHA已检出，线上源码工作区干净。Python锁定依赖、`npm ci`、生产构建通过。
- Ruff 0.16.7通过；服务器后端250项回归全部通过、无跳过；Playwright Chromium 71项全部通过。
- `systemd-analyze verify`验证本项目单元，`nginx -t`通过。Nginx和独立Redis已启动并设置开机启动；后端已安装并设置开机启动，但因飞书凭证为空被启动条件跳过，未执行真实飞书采集。
- 本机请求根页、`/control`、V1–V5查询入口全部200且HTML禁止缓存；无配置时API503；`.env`、文档与未知路径404。
- 临时进程仅用于实际安装包鉴权验证，显式关闭lifespan采集；无凭证和无效凭证401，正确主控凭证通过认证后因空缓存502。临时进程已退出，没有将模拟数据写入生产缓存。
- 独立Redis开启AOF，部署探针在服务重启后仍可读，随后删除，数据库恢复0键。Redis仅监听127.0.0.1:6380，SSH80保持可用。
- 私有目录700、环境文件600；新主控凭证仅存在服务器`control.env`，未输出到会话或Git。
- 服务器以自身IP访问8080返回200；当前部署客户端直连8080超时。UFW未启用，nftables无规则，iptables及iptables-legacy的INPUT/FORWARD/OUTPUT均ACCEPT；同步短时抓取8080建连SYN未捕获对应请求。因此仍需网络侧核对从使用网段到`10.0.53.174:8080/TCP`的ACL、路由或安全组，不能声称用户侧入口已通过。

## 下一步

1. 按用户选择，在服务器`/data/roombeacon/shared/config/feishu.env`填写新应用凭证，权限保持600，然后`systemctl start roombeacon`。
2. 核对网络侧8080/TCP可达性；本轮没有权限或工具修改外部网络设备。
3. 验证新应用的目录、忙闲、主题、姓名权限及至少一个完整真实采集周期。按需要签发新环境设备凭证，完成样机绑定与离线保护验证；旧终端尚未迁移。
4. 后续接入生产域名和HTTPS；V5观察或写入启用仍需明确范围并独立验收。

本轮完成的是新服务器软件与静态入口部署、隔离运行环境和回退准备。真实飞书采集、用户网段访问及终端迁移尚未验收。
