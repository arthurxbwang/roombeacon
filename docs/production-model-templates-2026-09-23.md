# 型号模板发布与 BX68 验收（2026-09-23）

## 授权、版本与范围

需求 [#23](https://github.com/arthurxbwang/roombeacon/issues/23)。用户要求先部署验收，再推送 GitHub，并明确批准本次仓库规则例外：将本地已提交的 Git bundle 导入生产仓库，由服务器按固定 SHA 检出、构建和部署；未复制未提交的源码。该例外不改变后续默认从 GitHub 发布的规则。

| 项目 | 本次记录 |
|---|---|
| 目标 | `https://roombeacon.thundersoft.com`，SSH 8081，`tsm-eed-ts-bj`，`/data/roombeacon` |
| 新前后端 | `808710d5347353c241b438eafbe9d5ccd8979db9` |
| 旧后端 | `8915b38b05ec54ef3ef186803afb38d7ef9ff9e4` |
| 旧静态 | `921ba26457e84a1bdc4c81c213f323941e633122` |
| Python 环境 | 保留 `/data/roombeacon/venvs/3b0bf39cdfdb92e421882444615f8ab7bcb76c8c` |
| 切换备份 | `/data/roombeacon/backups/v6-20260923T062248Z/` |
| 验收与配置备份 | `/data/roombeacon/backups/model-templates-20260923T062038Z/` |
| 样机 | BX68 / `RK3568`，唯一码 `W9TW7S`，IT灯塔-Test |
| 新 APK | `0.6.2-debug`，versionCode 9，`com.roombeacon.shell.debug` |

部署后补充的文档提交不代表重新部署；运行的应用提交以上表为准。原有账号、首位管理员消费记录、设备凭证、会议室绑定、保存模板和 V5 规则均保留；写入范围仍只有 IT灯塔-Test，其余 342 间不扩大权限。本轮没有创建、签到、登记释放资格或取消真实预约。

## 检查和真实结果

- 本地后端 Ruff 0.16.7 与 293 项测试通过；生产新发布目录再次构建前端、运行 Ruff 和 293 项后端测试，全部通过、无跳过。测试外部请求使用 mock，Redis 使用隔离实例。
- 前端与 Android 本轮隔离验证清单见[模板说明](device-model-templates.md)。原生 17 项测试、Lint、Debug 构建通过。隔离检查与下列真实验收分开记录。
- Nginx 配置检查及后端／Nginx／正式 HTTPS 就绪检查通过，roombeacon、nginx、roombeacon-redis 均 active。
- 正式首页、`/control`、`/control/legacy`、受管门牌和引用脚本返回 200；页面发布标识为完整 `808710d...`，新版型号目录认证后 200，匿名访问管理目录及门牌数据仍为 401。
- 部署前后及至少一个采集周期后，343 间目录、343 份有效快照均正常；对账号、管理员初始化记录、保存模板、设备身份／绑定、旧展示凭证及 V5 规则做摘要比较，一致。最终检查时没有在途监控记录。

### 样机升级和模板应用

用户临时打开网络 ADB 后，在 `10.0.51.221:5555` 备份实际安装的旧 APK，核对签名一致，再使用 `install -r` 原位升级。未清空应用数据或重新创建设备身份；ADB 仅用于安装和检查，页面始终直连正式 HTTPS。

升级前前台为厂商硬件调试应用，门牌最后一次上报约 18 小时前。升级后启动 RoomBeacon，原唯一码、IT灯塔-Test 绑定和版本 4 配置恢复，设备在线。随后通过认证管理 API，仅把原有 `device_profile=auto` 改成同型号 `bx68`；保留 V6、横屏、中文、自动昼夜、同步侧灯及刷新计数 2。发布版本 5，设备最终回执 **5/5**、心跳 2 秒内、错误为空。

设备真实上报固件 `RK3568_BX68_Android 11_64-20260331.094925_ZX-keys`、`config_schema=2`、`light_supported=true`、APK `0.6.2-debug`。同型号正常下发无需额外强制标记。

实际 WebView 1280×720、无整页横向或纵向溢出，加载新发布页面；显示真实 IT灯塔-Test 日程、中文及日间主题。配置切换过程中曾短暂显示网页操作会话失效，下一次会话同步后恢复；最终 V5 状态接口 200，已有预约显示受保护、不会自动释放，没有冒充已签到。

实际状态为使用中；红／绿／蓝 GPIO148／154／147 读回 **0／1／1**，符合 BX68 低电平红灯方案。IO4 未操作；该读回不替代现场色相观察，也不代表本轮完成全部灯色或其他型号实测。

原始实机截图和 WebView 检查结果保存在开发机 Git 忽略目录 `.local-tools/model-template-release/`，含真实人员信息，不提交仓库。

### 安装包校验

- 新 APK SHA-256：`e257ecbfeb0be21463d17c3b4a4810faef62e1078b8db6b98386ed083e96d367`。
- 升级前实际 APK SHA-256：`65760f3367658c1493b389a62de4d00448da6c85efecd5d11c959368812ec975`。
- 两包签名证书 SHA-256 相同：`180966b4bb9fc86236290425db781412cb675e390a7640879765c3568dcdf39e`。
- 旧 APK 私有备份：`.local-tools/model-template-release/BX68-before-0.6.1.apk`。新包为 `android/app/build/outputs/apk/debug/app-debug.apk`；构建产物不入 Git。

## 回退顺序与边界

备份目录包含 `backend.before`、`venv.before`、`nginx.before`、V6 环境配置／systemd 覆盖项以及 SQLite 在线备份；验收目录包含发布前摘要、Git bundle 及样机配置调整前的 `device-config.before.json`。保留这些私有文件，不能用旧 SQLite 整库覆盖当前账号或重新开放管理员初始化。

回退前重新确认在途释放状态，保留现有预约保护和所有凭证；有在途写入时先按既有运维流程处理，不能直接恢复旧预约记录。

1. 在当前后端仍运行时，将样机配置恢复为备份的 `auto` 灯控；保留当前身份与房间，使用最新 expected_revision 正常发布并确认回执。
2. 通过已授权安装通道恢复同签名 0.6.1 APK（降级需要 `adb install -r -d`，不卸载清数据）。旧 APK 上报不含新元数据字段，确认其已恢复；仍处于 0.6.2 的设备不能切到严格旧后端。
3. 如确需回退整个后端，先备份最新管理库，在事务内将受影响的当前配置去除 `device_profile`、`theme_mode`、`language` 三项扩展，保留设备身份、绑定、修订单调递增和历史审计。不要删除历史，也不要通过旧版接口重新下发含扩展字段的历史条目。本轮保存模板未改变；若回退时已有新增模板，应另外完成相同兼容处理。
4. 恢复 `backend.before` 所指 current 链接、`nginx.before` 和对应配置覆盖项，执行 `nginx -t`、systemd reload/restart，再验证本机接口、正式 HTTPS、343 间缓存和样机回执。Python 环境本轮未变，无需重建。Redis、账号、初始化消费记录和绑定库不清空。

本轮没有主动执行回退、跨昼夜切换、其他型号实机、物理 PoE 或长稳测试；强制异型号、语言与始终白天的行为由隔离回归验证。无 ADB APK 升级仍由 [#16](https://github.com/arthurxbwang/roombeacon/issues/16) 跟踪。本次临时网络 ADB 验收后应由用户关闭。
