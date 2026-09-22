# RoomBeacon Android 外壳

系统 WebView 加载服务器门牌页面，业务页面不打包进 APK。支持 Android 8.0+（API 26），当前首个实机目标为 Android 11 / WebView 106 / RK3568 / 2GB。支持范围不等于所有系统已完成实测。

## 构建

需要 JDK 17、Android SDK 平台 35 和 Build Tools 34.0.0。配置 `ANDROID_HOME` 或本目录被忽略的 `local.properties` 中的 `sdk.dir`。

```bash
./gradlew testDebugUnitTest lintDebug assembleDebug
```

测试包：`app/build/outputs/apk/debug/app-debug.apk`，包名 `com.roombeacon.shell.debug`。正式包名为 `com.roombeacon.shell`；正式签名密钥独立保管，不写仓库。`assembleRelease` 只产出未签名包，部署前需明确签名与分发方案。

## 配置和维护

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

0.2.0 增加可选本地侧灯同步。在维护页勾选“同步侧边灯”，仅接受完整型号/固件白名单：旧机 `rk3568_r` / `rk3568-11.0-20230426.150223`；0.2.2 新增 `RK3568` / `RK3568_BX68_Android 11_64-20260331.094925_ZX-keys`。0.2.3 根据用户现场校准将新机修正为低电平 GRB（IO1绿、IO2红、IO3蓝，111 全灭），旧机维持高电平 RGB（000 全灭）。此前 0.2.2 不适用于新机灯色验收。完整接线与匹配条件见 [型号映射](../docs/android-device-profiles.md)。空闲绿、使用中红、即将开始黄，其余熄灯；网页状态由协议 1 属性提供，原生每秒读取，3 秒无响应熄灯。只操作 GPIO154/148/147，不操作继电器，也不调用 root/chmod。首次升级 APK 后，后续业务页面仍可在服务器更新。

实际硬件断电、进程强杀或 GPIO 写入失败不保证熄灯；此灯是预约状态提示，不能用作门禁控制。型号相同不保证所有整机接线相同，未经逐路验证的设备不要启用。

- 页面已加载后由 H5 标记失联和过期；断网冷启动由原生提示，不保证持久离线日程。
- 30 天凭证过期、同房间凭证轮换语义仍保留；逐设备身份与自动续期尚未实施。
- 本地灯控已进入实现；远程运维后台、APK 自动升级、系统 WebView 更新管理均未实现。
- APP 被系统强制停止后不能自行保证启动；上电自启动依赖设备固件及默认桌面策略。
- 72 小时和 7 天长稳测试必须在明确环境下独立记录，短期检查不能代替。
