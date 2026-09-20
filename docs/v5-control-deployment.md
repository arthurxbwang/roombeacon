# Control V4/V5 更新与回退

> 2026-09-20 18:54 最新生效状态：现有服务器运行 `fa09d72453da71d4186fd0f6737f1b4ed5364a4f`，仅「IT灯塔-Test」开启 V5 自动释放写入，服务器白名单仅含该房间 ID，全局暂停已解除。已逐一核对其他 342 间为官方方案且无 V5 写入资格；下方写入关闭／观察模式为前次部署记录。真实释放尚未验收。

日期：2026-09-20。用户明确要求更新现有 Control 服务，以便自行预约和测试；本次目标为 `http://10.0.24.208/control`，不涉及其他服务器或 APK 升级。

## 发布内容

- Control 门牌版本菜单增加 V4、V5，默认 V4；V1/V2/V3 继续可选。
- 同步部署 V5 API 和保护协议 2。Nginx 增加准确的 V5 查询、确认、心跳及主控规则路由；所有接口仍由 FastAPI 验证凭证。
- 功能开关开启，飞书写入保持关闭；专用「IT灯塔-Test」配置为 V5 观察模式。其他房间保留官方方案、原绑定及二维码配置。
- Control 的门牌预览仍只读，V5 规则入口可管理观察配置。预览不等于平板已绑定操作凭证，也不等于真实释放验收。

## 来源与部署方式

使用独立发布工作区和 `codex/v5-control-release` 分支，从 GitHub 获取准确提交，在服务器新目录 `/opt/roombeacon-releases/<SHA>` 构建。未直接覆盖或回写 `/opt/argus-room-display` 源码；原目录保留回退。共用现有 Python 虚拟环境前先核对全部固定依赖版本。

服务继续名为 `room-display`、端口 8088，沿用现有私有配置、Redis 和凭证。通过独立 systemd drop-in 切换 WorkingDirectory，并使用最后加载的配置文件设定 V5 开关，避免修改已有密钥配置。保持一个采集服务，不启动第二个采集器。Nginx 原地址不变，减少重新登录和设备重新绑定。

## 检查与回退

部署前保存当前 Nginx 配置、服务参数与 V5 目标策略快照，目录权限仅管理员可读。旧源码 SHA 为 `c34a5614bdb5e86305e40deb0d5c36807ccd0b03`，配置根为 `/etc/argus-room-display`。

切换前运行依赖检查、前端构建及 `nginx -t`；切换后核对 HTML 发布标识、静态资源、未授权请求拒绝、主控目录和预览、V5 规则读写开关，以及至少一个正常采集周期。页面版本选项另用浏览器测试验证，不把 200 状态码单独作为功能成功。

失败时恢复备份的 Nginx 配置、删除本次创建的服务 drop-in 并 reload/restart，恢复原目录；不清空 Redis、不轮换凭证。仅恢复本次专用房间策略变更，不改动其他房间。自动释放保持关闭，已发出的请求仍不能通过代码回滚撤回。

真实日程创建及释放由用户后续测试，本次不宣称通过。

## 已部署结果

- 运行代码 SHA：`4ba9d3836ba3de86db608b800661989037775cf4`；来自 GitHub `codex/v5-control-release`，未推送 main。
- 服务工作目录：`/opt/roombeacon-releases/4ba9d3836ba3de86db608b800661989037775cf4/backend`；Nginx 静态根指向同一发布目录的 `frontend/dist`。
- 服务覆盖配置：`/etc/systemd/system/room-display.service.d/50-roombeacon-v5.conf`；V5 标志文件：`/etc/argus-room-display/v5-preview.env`。原有密钥配置内容未修改。
- 回退备份：`/var/backups/roombeacon-control/20260920-4ba9d38/`，含原 Nginx 配置和仅管理员可读的目标策略基线。
- 发布前：冻结发布工作区 Ruff 0.16.7、后端 129 项、前端构建及 Chromium 63 项通过；服务器固定依赖版本核对、ASGI 导入、npm ci/build 通过。
- 发布后：实际 `/control` 返回 HTTP 200 和对应 SHA；脚本与服务器构建文件哈希一致，包含 V1–V5 全部菜单项。带认证的主控目录返回 343 间房，V5 规则及预览返回成功，未授权 V5 读写请求均为 401。
- 设备凭证摘要集合与部署前一致；原飞书应用、主控凭证、Redis 配置和二维码私有配置一致。北京 201、205 仍为官方方案，二维码状态与原配置一致。
- 新服务首轮采集于北京时间 18:37:49 开始、18:38:48 完成：343 间房全部刷新，18 个批次完成，失败批次为 0。
- `IT灯塔-Test` 当前 owner=v5、mode=observe；`ROOM_DISPLAY_USAGE_ENABLED=true`、`ROOM_DISPLAY_USAGE_WRITES_ENABLED=false`，全局暂停有效。未签发或轮换操作凭证，没有真实飞书释放写入。

用户访问原 Control 地址，搜索测试房间，点击「预览门牌」，在「门牌版本」选择 V4 或 V5；若仍看到旧菜单，强制刷新页面。V5 规则可查看／调整观察设置；Control 预览始终只读，实际平板确认还需独立操作凭证绑定，观察模式不自动释放。

## 单房间释放追加部署

用户随后明确授权仅为 IT灯塔-Test 开放释放。追加服务器端 `ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS` 白名单，内容仅为 `omm_d42ad8a9e50c5ddf9d60fe3d3bc6473b`，再开启写入并解除全局暂停。其余房间即使误改自动规则也不能获得写入资格；实际启用结果在生效核验后记录。保留用户已保存的测试房间规则，不重置或代替每场实例登记。


### 2026-09-20 18:54 启用核验

- 生效代码 SHA：`fa09d72453da71d4186fd0f6737f1b4ed5364a4f`；服务工作目录与 Nginx 静态根均切换到该 SHA 的发布目录，Control 地址不变。
- `ROOM_DISPLAY_USAGE_ENABLED=true`、`ROOM_DISPLAY_USAGE_WRITES_ENABLED=true`、`ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS=["omm_d42ad8a9e50c5ddf9d60fe3d3bc6473b"]`，全局暂停为 false。白名单不能通过 Control 扩大。
- 343 间真实规则接口全部成功；仅 IT灯塔-Test 的 `writes_enabled=true`，其他 342 间均为 official/off 且写入关闭，无异常项。北京 201、203、205 官方二维码与原配置匹配。
- 保留用户原规则：提前 10 分钟、宽限 10 分钟、待释放 60 秒、auto/v5；规则 revision 未改变。原设备凭证摘要、飞书应用、主控及二维码私有配置一致。
- 本次后端 Ruff 0.16.7 及 136 项测试通过，覆盖名单为空、其他 ID、相近 ID、通配符、提前结束、发送前撤销白名单和逐房间开关返回。服务器依赖核对、前端构建与 Nginx 检查通过；前端业务未变，沿用此前 63 项浏览器结果。
- 18:54:51 核验无真实释放审计；当前测试实例为 `blocked/missed_window`，未登记允许释放，不会补执行。新测试预约须覆盖完整签到窗口、平板操作凭证与主动保活正常、在 Control 登记当前单次实例；开启服务器开关不绕过这些保护。
- 本轮回退目录：`/var/backups/roombeacon-control/20260920-fa09d72-single-room/`。回退先暂停全局释放，再恢复其中 Nginx、systemd drop-in、开关文件，daemon-reload、重启服务、检查并重载 Nginx，回到写入关闭的 4ba9d38；不清 Redis、不撤销既有预约或轮换凭证。

- 服务重启后首轮采集于北京时间 18:55:32 完成：343 间刷新、18 批完成、0 失败；18:56:02 再次核对所有房间隔离状态无异常，释放审计仍为空。
