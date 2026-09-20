# Control V4/V5 更新与回退

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
