# 独立会议室门牌部署手册

> 版本: 2.11 | 作者: Argus Team | 更新日期: 2026-09-16

---

## 目录

- [1. 范围](#1-范围)
- [2. 部署](#2-部署)
- [3. 绑定](#3-绑定)
- [4. 验收与恢复](#4-验收与恢复)

---

## 1. 范围

用户关闭原 PR #165，授权独立测试机 `10.0.24.208` 安装组件、重启及 HTTP 80 部署。保留 GitHub 源码审计；此测试部署不合并 main、不发布生产 Tag，也不操作生产蓝绿节点。

独立 ASGI 入口 `app.room_display_main:app` 只提供设备展示 API，复用飞书连接器、日程服务和 H5。本机 Redis 存储凭证摘要和缓存，不连接生产 Redis/PostgreSQL，不启动 Celery、WS、审批或补偿监听器。按需每 5 分钟刷新，无事件即时刷新。凭证 30 天过期，可 SSH 替换和撤销。

飞书权限：`vc:room:readonly`、`calendar:room:readonly`、`calendar:room`。应用需已发布，接口配额与原应用共享。只查询会议室和预约；主题不可见时降级；预约占用不代表物理有人。

## 2. 部署

代码先提交 GitHub 任务分支，机器通过 Git 拉取并检出已验证完整 SHA。目录 `/opt/argus-room-display`，独立 venv `/opt/argus-room-display-venv`。

依赖：Debian 13、Nginx、Redis、Python 3.13 venv、Node/npm、git。安装 Python 依赖使用 `backend/requirements-room-display.txt`，前端 `npm ci && npm run build`。Redis 仅监听回环，启用 AOF 持久化以保存设备凭证。

`/etc/argus-room-display/feishu.env`（root:root，600）：

```dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

`/etc/argus-room-display/service.env`（root:root，600）：

```dotenv
APP_ENV=production
ROOM_DISPLAY_STANDALONE=true
SECRET_KEY=<独立生成的随机值，至少32字符>
REDIS_URL=redis://127.0.0.1:6379/0
ARGUS_ENV_FILE=/dev/null
READ_ONLY_MODE=true
```

独立模式不要求 DATABASE_URL。`READ_ONLY_MODE=true` 保持外部系统写保护；SSH 管理仅修改本机门牌凭证，不改变飞书预约。

将 `scripts/room-display-admin` 安装到 `/usr/local/bin/room-display-admin`（root:root，700），可直接执行 `room-display-admin list` / `room-display-admin issue omm_ID` / `room-display-admin revoke omm_ID`。

安装 `scripts/room-display.service` 至 systemd，创建无登录的 `room-display` 用户。安装 `scripts/room-display-standalone.nginx.conf` 到 Nginx enabled 配置并撤下默认站点。执行 `nginx -t`、`systemctl daemon-reload`，启用并启动 `redis-server`、`room-display`、`nginx`。应用仅监听 127.0.0.1:8088，Nginx 监听 HTTP 80。环境文件由 systemd root 读取，服务以非 root 运行。

HTTPS 后续由用户通过 ACBridge 配置，当前不占用 443、不配置证书。绑定凭证按站点 origin 保存，切换 HTTPS 或域名后需要在新 origin 再次绑定。

## 3. 绑定

### 测试主控页面

访问 `/control`，首次输入独立测试主控凭证，之后可按地区、会议室名称/位置筛选并预览，支持上一间/下一间。该操作不会签发或替换门牌绑定凭证。凭证保存在当前浏览器标签页的 sessionStorage，退出主控即清除。

`/etc/argus-room-display/control.env`（root:root，600）设置 `ROOM_DISPLAY_CONTROL_TOKEN` 为至少 32 字符的独立随机值。systemd 可选读取此文件；未配置时主控 API 拒绝访问。更新凭证后重启 `room-display`。配置文件由 root 管理，不能把值放在 URL 或 Git。仅开放受此凭证保护的目录/预览 GET 接口；设备凭证不能访问主控接口。临时主控凭证可读取全部会议室，请按测试管理凭证保管。

需要第二组登录凭证时，在同一 `control.env` 中增加 `ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY`（允许短密码，但不能为空或纯空白；区分大小写），保留原 `ROOM_DISPLAY_CONTROL_TOKEN` 不变，重启 `room-display` 后两组均可登录，权限相同。撤销任一组时清空对应配置并重启；该组现有会话在下一次 API 请求时被拒绝。不得将真实凭证放入 Git 或 URL。第二组凭证交付文件可保存在 `/root/room-display-control-token-secondary.txt`，root:root、600。

时间轴显示当前小时之前 6 小时到之后 6 小时，整点向前滚动，跨天刻度标记“昨/明”。查询范围覆盖前后跨天边界，右侧仍只列当日安排。中间会议时间和占用状态字号增大。

### 日出日落与主题预览

独立门牌根据飞书位置层级识别城市，使用 Astral 3.2 按城市中心经纬度和 IANA 时区离线计算日出/日落，日间白底、夜间深色。无需新增天气接口或授权。时钟、日期和今日安排跟随当地时区（含夏令时）；查询扩大到上海日期前一天至后两天，以覆盖海外当地全天和滚动时间轴。

中控“上一间 / 下一间”旁提供“自动 / ☀ 日间 / ☾ 夜间”胶囊切换。手动模式只改变当前测试预览，切换会议室后保留，刷新主控恢复自动；不修改日程时间和设备绑定。正式绑定门牌始终自动切换。

未识别城市（当前为波兰分部、CES2025）显示“城市待配置”并暂用深色；可在中控手动预览两种主题。城市映射位于 `backend/app/services/room_daylight.py`；中控编辑城市配置留待后续迭代。太阳时间基于天文计算，不使用天气、楼宇遮挡或设备定位。位置目录查询失败仅降级主题，不改变日程预约状态。

### 集中采集与缓存

独立服务通过 FastAPI lifespan 启动单独后台采集循环。默认每 300 秒覆盖全部目录，每批最多 20 间；`ROOM_DISPLAY_SYNC_SECONDS` 可在 `service.env` 调整（120–3600 秒），修改后重启生效。目录及层级每 15 分钟刷新，复用同一个飞书客户端和租户 Token。Redis 固定时间窗口锁限制同一时刻的采集者；本轮工作在锁到期前 10 秒取消，超时游标下轮从后续批次继续，避免前部故障导致后部长期无数据。采集进程正常退出时释放自身锁，异常退出最多等待一个采集周期接管。

`/api/meeting-rooms/display`、`/api/room-control/preview` 和目录接口只读本机 Redis，页面切换和终端数量不会增加飞书查询次数。日出/日落信息也仅使用缓存位置离线计算。首次启动且从未同步的房间立即返回首次同步提示，不挂住请求等待飞书；其他房间继续使用已有缓存。主平台可选集成接口保持原逻辑，本节适用于独立门牌服务。

每个房间成功获取后原子替换快照，保留最近一次成功结果 7 天；单房间/单批次失败保留旧值，不用空结果覆盖。前端保留内存中上次成功内容，网络失败或数据过期显示“历史日程 / 最后同步”并继续重试；此时空档不显示可约绿色，不能将历史内容当实时状态。长时间故障超过 7 天或 Redis 历史丢失后，需要重新同步；不是无限期归档。

排查使用 `journalctl -u room-display`，关注 `room_collector_cycle_complete` / `room_collector_batch_failed` / `room_collector_cycle_failed`。本机 Redis 的 `rooms:collector:status` 包含本轮时间、房间数、成功和失败批次、实际更新房间数；`rooms:collector:cursor` 为下轮游标。单次 API 响应成功不代表上游数据新鲜，应同时检查 `synced_at`、`valid_until`。不要手动删除锁或清空设备凭证。

### V1 / V2 与全屏

本次将原有看板定义为 V1，新增 V2（界面版本，独立于 Argus 发布版本号）。中控预览工具栏选择“V1 经典版 / V2 自适应”，选择保存在当前浏览器的 localStorage，切换会议室和刷新后保留。未选择时默认 V2。设备门牌也读取同一浏览器的选择，或者使用 `/?version=v1`、`/?version=v2` 固定该页面版本；不修改设备凭证和其他平板的设置。

V2 根据可用区域比例调整字号和间距，横屏双栏、竖屏上下布局；极小屏幕允许滚动以保证内容可达。右侧仅显示本场与下一场；底部仍保留整个 12 小时窗口内的预约，未结束预约为红色，已结束为灰色，可约空档为绿色。数据失效或会议室停用时，空档恢复中性色，不能以绿色误示可预订。

中控顶部“全屏 / 退出全屏”调用浏览器 Fullscreen API，支持 Esc 或系统操作退出并同步按钮。浏览器不支持或拒绝时显示提示，可使用浏览器菜单或添加到主屏幕；网页不能强制绕过设备限制。

### 看板状态与预约占位

门牌以 6:4 分栏展示，左侧为状态、可用截止时间或倒计时、会议主题和组织者。15 分钟内有下一场时显示“即将开始”，会议期间显示“正在使用”并显示进度条。右侧优先显示当前与后续会议，历史预约保留在“已结束”展开项；没有后续预约时展示空态和实际容量，不推测麦克风、投屏等硬件能力。

“扫码预订 / 预约入口待接入”为经用户确认的视觉占位，不生成二维码、不接受预约，也不会调用飞书写接口。接入真实预约入口前不能作为可用预订功能验收。

### 单设备绑定

以 root SSH 登录，加载环境后运行管理命令。不要把设备凭证写到 URL 或 Git。

```bash
set -a
. /etc/argus-room-display/service.env
. /etc/argus-room-display/feishu.env
set +a
cd /opt/argus-room-display/backend
/opt/argus-room-display-venv/bin/python -m app.services.room_display_admin list
/opt/argus-room-display-venv/bin/python -m app.services.room_display_admin issue omm_目标会议室ID
# 撤销：
/opt/argus-room-display-venv/bin/python -m app.services.room_display_admin revoke omm_目标会议室ID
```

`list` 默认使用中文对齐表格，每页 20 间，列出地区/园区、楼层、名称、容量、状态及完整会议室 ID。地区来自飞书层级（当前租户：企业 / 国家 / 地区园区 / 楼栋 / 楼层），按完整位置路径匹配，不根据会议室名称猜测。目录缓存 5 分钟，位置无法解析时标注未知。需要现有应用具备层级批量查询权限；已在独立机验证同一应用可调用。

```bash
room-display-admin regions                         # 地区/园区及数量
room-display-admin list --region 北京              # 北京地区
room-display-admin list --region 北京 --name 创新  # 同时筛选名称
room-display-admin list --region 北京 --page 2     # 下一页
room-display-admin list --region 北京 --all        # 显示全部北京会议室
room-display-admin list --region 北京 --all --json # 完整位置/名称，便于导出
```

`--region` 也支持园区/楼栋关键词；长名称仅在表格内省略，`--json` 保留全文。可用/停用是会议室配置状态，不代表此刻的预约闲忙。

在 iPad 打开 `http://10.0.24.208/`，粘贴生成的凭证。每个会议室仅一份有效凭证，重新签发使旧凭证失效；Redis 丢失或凭证到期后重新签发。凭证只允许读绑定会议室，不能管理平台。

修改飞书配置后执行 `systemctl restart room-display`。实际 iPad 需设置常亮或引导式访问，网页不控制系统锁屏。

## 4. 验收与恢复

检查 `systemctl is-active room-display nginx redis-server`、`nginx -t`、端口以及 Git HEAD。根页面返回 200，未认证 `/api/meeting-rooms/display` 返回 401，`/api/admin/users` 和 `/login` 返回 404。列表和凭证验证必须以真实租户接口为准，禁止把 mock 当作真实验收。

绑定后核对日期、会议室、日程、组织者和主题；数据过期或连接失败应显示未知。至少观察一次完整刷新周期。物理 iPad 和后续 HTTPS 单独验收。

升级前记录当前 SHA 和配置备份；从 GitHub 拉取指定提交，构建通过后重启。失败回退已记录且兼容的 SHA、重建并重启。不要清空 Redis，也不要恢复指向生产的配置。首次部署无先前版本时停用门牌服务并保留故障证据，不能宣称已回退到可用版本。

## V3 官方扫码签到

V3 在中控版本选择器切换，设备固定入口为 `/?version=v3`。V1/V2 保持原有行为，默认版本仍为 V2，选择会保存在当前浏览器。

V3 去除预约占位，左侧主信息旁显示已配置会议室的飞书官方签到二维码，配公司品牌插画；窄屏纵向排列。使用服务器环境变量 `ROOM_DISPLAY_CHECKIN_URLS` 配置 JSON 对象，键为会议室唯一 ID，值为官方完整签到链接；不按名称匹配。配置保存在独立机 `/etc/argus-room-display/service.env`（600），修改后重启 `room-display`。不要把真实链接的 resource_token 写入仓库。

示例格式：`ROOM_DISPLAY_CHECKIN_URLS={"omm_example":"https://www.feishu.cn/calendar/pages/resource_qrcode?code=0&resource_token=REPLACE_ME"}`。

二维码在本机离线生成，不使用第三方二维码服务；未配置或停用的会议室不展示。扫码由员工飞书完成官方签到，本系统不提交签到、不推断或显示“已签到”。品牌插画使用公司提供 GIF 的顶部区域，降低饱和度；下方保留真实签到二维码，不能用品牌宣传二维码替换。装饰色跟随预约状态，不代表签到状态。二维码固定显示，不由历史日程控制签到资格。回退选 V2 即可隐藏签到区域。

V3 签到区无独立外框，二维码保留白色静区以便扫描；高纠错艺术码使用确定性的汽车/无人机中心图标。全屏状态外框：空闲绿色、使用中红色、即将开始橙色、未知灰色。右侧“后续会议”从已缓存日程中按开始时间排序，仅显示未来两场并标注日期，不包含本场。
