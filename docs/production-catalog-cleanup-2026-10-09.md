# 模板收敛、设备删除上线与本地分支盘点

2026-10-09；用户明确授权 `codex/56-catalog-device-cleanup` 推送、上线并检查其他本地分支。需求 [#56](https://github.com/arthurxbwang/roombeacon/issues/56)，功能 [PR #57](https://github.com/arthurxbwang/roombeacon/pull/57)，代理修复 [PR #58](https://github.com/arthurxbwang/roombeacon/pull/58)。其他需求分支仅盘点，没有合并或发布。

## 准确版本与发布过程

- 独立生产：`roombeacon.thundersoft.com`，主机 `tsm-eed-ts-bj`，SSH 8081，目录 `/data/roombeacon`。
- 发布前应用：`5b9fe3c702f4e7a36d3ea535ceaa3c7d3602ba24`。
- 功能初次合并：`45bc7bc95d2e44801e71ef5703f14042cdac23e5`；实际 HTTPS 检查发现旧 Nginx 方法白名单拦截 DELETE，随后补齐受限路径。
- **最终应用与静态资源：`3d0b1e1958c4961b55ecc3ed8910f901f073cfe3`**，`current` 指向 `/data/roombeacon/releases/3d0b1e1958c4961b55ecc3ed8910f901f073cfe3`。源码均由服务器直接从 RoomBeacon GitHub 获取，以准确 SHA 归档发布。
- Python 环境仍为 `/data/roombeacon/venvs/3b0bf39cdfdb92e421882444615f8ab7bcb76c8c`；无需依赖升级。正式样机 APK 保持 0.7.0，没有 Android 源码发布或安装。

两次重启前均确认没有 waiting／checking／releasing／end_requested 在途记录。没有修改日历来源、官方配置、写入白名单或签到规则，没有提交签到、预约释放或设备删除。

## 真实上线核对

默认硬件选择仅两项：BX68 13.3 寸 1920×1080 横屏（沿用 v2）与 RK3568_R 10.1 寸 1280×800 横屏（v1）。软件仅“签到版”（沿用 v2）和“未签到版”（v1）。原发布版本、设备配置、凭证摘要、会议室关联、主控、安装关联、策略及暂停选择均与备份基线一致。

真实 HTTPS `/control`、静态资源及 API 通过。真实管理员浏览器打开 W9TW7S 删除确认，核对短码和会议室后点击“保留设备”，设备数仍为 2；无业务写请求、无页面脚本错误。匿名 DELETE 对确定不存在的全零设备 ID 返回 401，管理员返回 404，浏览器缺少 CSRF 返回 403，证明受限代理路径可到达后端。管理员／只读及有效删除的完整行为由隔离回归覆盖；没有为测试而创建生产账号或删除真实设备。

自动审批拒绝向在线 BDC5ZS 发送错误短码 DELETE 的诊断请求，理由为未授权删除该设备且存在不必要的生产变更风险。此类请求已停止；后续只用确定不存在的 ID 验证代理与鉴权，以及独立 Nginx／假上游验证方法边界。

BDC5ZS 真实在线、修订／回执 **2/2**、无应用错误，正式 APK 0.7.0，当前主控业务心跳健康。W9TW7S 仍离线，修订／回执 **11/10**，旧 0.7.0-debug 台账及历史保留；上线不会自动删除它，管理员可在新确认框操作。不能将同房间主控的业务心跳认作旧设备在线。

17 条发布前记录的 state／verified 保持，343 间会议室目录有效。最终重启后的完整采集于 **2026-10-09 10:46:03（北京时间）**完成：343 间、18 批、失败 0；10:46:28 的最终核对通过。

门牌静态产物包含“无后续预约”，旧长文案已移除；本地 V4／V6／V7 在 1280×720、1280×800、1920×1080 均为单行。未签到版保留飞书二维码显示逻辑，但本次只读发现生产 `ROOM_DISPLAY_CHECKIN_URLS` 当前为空，真实二维码预览没有可用来源；未伪造二维码或代填链接。配置真实官方链接后才能显示对应房间的二维码。

## 检查结果

- 本地 Ruff 0.16.7、411 项后端（隔离 Redis，无跳过）、npm ci、类型检查／构建和 Chromium 151 项全量通过。
- 两次生产构建、Ruff、后端 411 项均通过；最终生产 Nginx 语法检查、服务启动及 HTTPS 通过。
- 独立回环 Nginx＋假上游先复现旧代理 403，修复后 8 项全通过；拒绝非设备路径、非法 ID、子路径与 PATCH，生产请求数 0。
- 首次生产构建 Chromium 151 项全量通过。最终构建全量为 149 通过、2 项计时／页面发布检查波动：一项为结束测试后尚未完成的 route 回调，另一项为虚拟时钟下未观察到导航；随后相关两个测试文件单进程 **11 项全部通过**，未改代码或放宽断言。
- 真实后台确认／取消、两个软硬件选项、CSRF 与匿名边界通过。模拟用例不作为官方扫码、实机布局、GPIO、PoE 或长稳验收。

## 私有备份与回退

发布前 SQLite／配置和设备、版本、房间、策略、17 条记录基线：`/data/roombeacon/backups/catalog-56-20261009T023109Z`；真实核对 `verified.json`、浏览器 `live-browser.json`、截图及检查日志均留在该私有目录，不进入 Git。

部署脚本备份分别为 `/data/roombeacon/backups/v6-20261009T023444Z`（原 `5b9fe3c`）和 `/data/roombeacon/backups/v6-20261009T024411Z`（中间 `45bc7bc`）。备份保存旧应用／虚拟环境软链接目标、Nginx、管理 SQLite 及相关配置。

当前没有设备删除。应用回退前核对在途释放并保留现有 Redis／SQLite，只切换准确应用与 Nginx；不要整库覆盖后续账号、设备、交付或业务变化。回到中间 `45bc7bc` 会恢复 DELETE 拦截，不能作为该按钮的最终可用版本。若回退整个功能到 `5b9fe3c`，模板显示差异需按[整理回退边界](catalog-device-cleanup.md)逐项处理。以后实际删除发生后，不能直接回到不理解 `deleted` 的旧后端，须保留删除兼容。

## 剩余本地分支

以最终应用 `3d0b1e1` 对应的 `origin/main` 为基准，GitHub 状态与本地模拟合并一致：

| 分支 | 当前提交／PR | 合并与上线状态 |
|---|---|---|
| `codex/52-native-health-receipts` | `61dee6d`，[PR #55](https://github.com/arthurxbwang/roombeacon/pull/55) | 未合并、未部署；APK 0.7.1（11）未签名安装，生产仍 0.7.0。与 main 有 4 处冲突：CHANGELOG、installation_admin.py、current-state.md、V6Control.vue，需接续处理并重新验证。 |
| `codex/41-stage-report-archive` | `48e7a18`，[PR #42](https://github.com/arthurxbwang/roombeacon/pull/42) | 未合并；只有脱敏 HTML／PDF 资料，无业务部署。CHANGELOG 冲突；独立工作树 `.local-tools/report-publication` 干净并保留。 |

上述两个分支均已存在远程备份，没有仅本地的未推送提交；本次保留其工作树和历史。`main` 同步后，#56 的临时分支可按仓库规范清理，已合并历史继续保留在 main。既有未跟踪 `output/` 是生成材料，未上传或用于发布。
