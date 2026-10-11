# RoomBeacon Android 外壳

> 2026-10-11当前：默认首装包为正式0.7.1（11），两台同签名ADB覆盖和运行回执已有；BDC5ZS首轮4/4及部分业务闭环通过。无ADB APK升级、普通应用厂家接口、关闭后真PoE、自启动和量产型号长稳仍待验收。13.3寸量产批次已采购、预计两周内到货，执行[采购计划](../plan/procurement-rollout-20261011.md)及[逐台交付清单](../docs/13-inch-delivery-checklist.md)。

> 2026-10-09：正式 APK 0.7.1（11）已沿用项目签名真实覆盖升级 BDC5ZS，原身份和配置保持；页面／灯控独立运行回执已上线，实际 H5 与 WebView 版本可在后台查看。该次升级通过 ADB，后台自动升级仍待实施；构建、签名、实机证据与回退见[升级回执](../docs/production-native-health-upgrade-2026-10-09.md)。下方早期版本流程用于追溯。

> 2026-10-08：正式 0.7.0（10）已安装，BDC5ZS 已绑定 IT灯塔-Test，2/2 和真实业务心跳正常。#52 的 0.7.1（11）新增灯控故障恢复及独立页面运行回执，尚未发布；须先升级后端再升级 APK。详见[本轮说明](../docs/android-runtime-health.md)。下方旧版维护说明由待办 #54 统一校准。

> V6 / APK 0.6.1：启动后自动连接生产主域名，进入原生待部署页，由 `/control` 后台认领和配置。正常流程不再输入维护密码、服务器或房间凭证。以下手动配置说明为 0.2.x 历史能力；最新流程及边界见 [V6 文档](../docs/v6-device-management.md)。

系统 WebView 加载服务器门牌页面，业务页面不打包进 APK。支持 Android 8.0+（API 26），当前首个实机目标为 Android 11 / WebView 106 / RK3568 / 2GB。支持范围不等于所有系统已完成实测。

> 本地待发布 0.6.2：增加固件与配置能力上报、执行后台选定的型号模板接线及昼夜／语言入口参数（型号差异由后台确认）。先升级后端，再升级 APK；尚未安装样机，见[型号模板说明](../docs/device-model-templates.md)。

## 构建

需要 JDK 17、Android SDK 平台 35 和 Build Tools 34.0.0。配置 `ANDROID_HOME` 或本目录被忽略的 `local.properties` 中的 `sdk.dir`。

```bash
./gradlew testDebugUnitTest lintDebug assembleDebug
```

测试包：`app/build/outputs/apk/debug/app-debug.apk`，包名 `com.roombeacon.shell.debug`。正式包名为 `com.roombeacon.shell`；正式签名密钥独立保管，不写仓库。`assembleRelease` 只产出未签名包，部署前需明确签名与分发方案。

## 配置和维护

当前正式托管流程为：APK连接固定生产管理域名、生成并安全保存独立设备身份，显示六位短码；管理员核对实物后认领、选择房间和明确软硬件版本，设备取配置并上报运行与修订回执。正常流程不输入维护密码或手工门牌凭证。管理域名当前写在原生程序中，换服务器IP可保持域名，换origin需另做兼容迁移。

已有集中台账、配置和H5更新能力；设备凭证损坏、撤销换机、APK升级和现场救援须按#16／#29闭环。正式包关闭CDP并启用FLAG_SECURE，远程截图不能作为现有保证能力，现场画面仍须验收。Device Owner仅有条件使用分支，不代表当前设备已获得权限；普通应用自启动依赖固件与默认桌面，须真断电复验。

### 历史手动配置

以下为0.2.x历史能力，用于追溯；不是当前托管APK的维护入口。

首次启动输入服务器 origin（例如 `https://rooms.example.com`，不含路径或凭证）与 6—64 位维护密码。默认横屏，0.2.1 起打开服务器根入口 `/`（不固定 UI 版本，网页当前默认 V4），网页内录入管理员签发的单会议室凭证。凭证不随 APK 分发。

长按屏幕右上角小点打开密码验证；5 次失败等待 30 秒。维护界面 2 分钟后回到门牌。可修改服务器、方向和密码，查看 WebView/APK 版本，重新加载。更换 origin 需要确认清除网页存储并重新绑定。

正式包只允许 HTTPS；调试包额外允许本机 `127.0.0.1` 和 `localhost` HTTP。0.2.4 为已授权的局域网样机测试增加精确地址 `http://10.0.24.208:80`（可省略默认端口），其他明文地址不接受，不放行整个私网段。此测试入口依赖设备网络直接可达服务器，不使用ADB转发；HTTP测试不等于正式HTTPS接入。TLS 错误不能忽略。页面及资源限制同一 origin，因此字体、图片、API 应同源部署，不依赖外部 CDN。

全屏与专用设备锁定分开。管理员可启用 HOME 入口，在系统默认桌面中选择 RoomBeacon，随后验证开机恢复。Device Owner 配置须另行确认设备交付状态后执行，不能擅自恢复出厂；只有成为 Device Owner 后，维护页才允许启用 lock task。当前不自动改变默认桌面、设备所有者或系统电源设置。

## 无真实服务端的样机测试

`tools/fixture_server.py` 只监听回环，返回固定结构的模拟日程，页面明确标记“仅样机测试”。合成凭证只对该测试服务有效，绝不能把测试结果称为飞书线上验证。

在仓库根构建前端后：

```bash
python3 android/tools/fixture_server.py --dist frontend/dist --state /path/to/test-state.json
adb connect DEVICE_IP:5555
adb -s DEVICE_IP:5555 reverse tcp:8765 tcp:8765
adb -s DEVICE_IP:5555 install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s DEVICE_IP:5555 shell am start -n com.roombeacon.shell.debug/com.roombeacon.shell.MainActivity
```

设备配置为 `http://127.0.0.1:8765`。测试状态文件可设置 `release`、`api_status`、`page_status`、`skip_binding`；API 正常默认 200。先改成 503 检查未知状态，再恢复 200；改成 401 检查解绑。测试期间状态文件不存真实凭证。

从仓库根运行 `ROOMBEACON_TEST_SERIAL=DEVICE_IP:5555 node android/tools/device-smoke.mjs` 可做实机自动化（先执行前端 `npm ci`；ADB 可通过 `ROOMBEACON_ADB` 指定）。脚本仅允许本机模拟页面，结果与截图默认写入被忽略的 `.local-tools/device-test/`。本次结果见 [样机验证记录](../docs/android-sample-verification.md)。

调试包开放 WebView 调试并允许截图；正式包关闭 WebView 调试并启用安全窗口。仅授权开发网络开放 ADB。

## 页面发布契约

前端构建时可指定 `ROOMBEACON_WEB_RELEASE`（只允许字母、数字、点、下划线和横线，最多 100 字符）；未指定则生成构建 UUID。已绑定门牌每 5 分钟检查同源入口 HTML 标识，资源可用后刷新；同一会话 10 分钟内不重复自动刷新。中控和未绑定页不自动刷新。检查只读公开静态 HTML，不增加未经认证的业务 API。

服务器应让入口 HTML `no-cache`/重新验证；哈希资源不可变且保留上一版，原子发布，回退时恢复旧入口和资源。仅检测入口脚本存在不能替代完整版本验收，样机灰度仍必需。页面检查故障不清除绑定，不打断现有日程显示。

## 当前边界

厂家接口按需参考 [RK3568 SDK 开发摘要](../docs/hardware/rk3568-sdk-guide.md)，其中包含接入前提、常用参数和手册勘误；当前 APK 未集成 `ysapi.jar`。其他硬件资料见[开发资料索引](../docs/reference/README.md)。

0.2.0 增加可选本地侧灯同步。在维护页勾选“同步侧边灯”，仅接受完整型号/固件白名单：旧机 `rk3568_r` / `rk3568-11.0-20230426.150223`；0.2.2 新增 `RK3568` / `RK3568_BX68_Android 11_64-20260331.094925_ZX-keys`。0.2.3 根据用户现场校准将新机修正为低电平 GRB（IO1绿、IO2红、IO3蓝，111 全灭），旧机维持高电平 RGB（000 全灭）。此前 0.2.2 不适用于新机灯色验收。完整接线与匹配条件见 [型号映射](../docs/android-device-profiles.md)。空闲绿、使用中红、即将开始黄，其余熄灯；网页状态由协议 1 属性提供，原生每秒读取，3 秒无响应熄灯。只操作 GPIO154/148/147，不操作继电器，也不调用 root/chmod。首次升级 APK 后，后续业务页面仍可在服务器更新。

实际硬件断电、进程强杀或 GPIO 写入失败不保证熄灯；此灯是预约状态提示，不能用作门禁控制。型号相同不保证所有整机接线相同，未经逐路验证的设备不要启用。

- 页面已加载后由 H5 标记失联和过期；断网冷启动由原生提示，不保证持久离线日程。
- 旧逐房间凭证的30天到期和轮换语义保留；当前托管设备已有独立身份和短期网页会话续期，身份损坏／撤销换机不自动重置。
- 集中设备台账、远程配置与持续运行回执已上线；无ADB APK升级、系统WebView更新管理及厂家守护尚未完成。
- APP 被系统强制停止后不能自行保证启动；上电自启动依赖设备固件及默认桌面策略。
- 72 小时和 7 天长稳测试必须在明确环境下独立记录，短期检查不能代替。
