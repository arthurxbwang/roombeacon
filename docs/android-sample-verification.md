# Android 门牌样机验证（2026-09-20）

> 后续状态：样机已按用户要求切换到真实北京-201，见 [真实接口联调](android-live-201-verification.md)。本文保留此前模拟测试结果。

分支：`codex/android-webview-shell`。用户授权在到位样机实施和安装；没有推送 GitHub，也没有部署旧服务器。

## 环境与产物

- 样机：`10.0.69.167:5555`，型号 `rk3568_r`，Android 11 / API 30，ARM64，约 2GB 内存。
- 实际 WebView：`106.0.5249.79`；画面 1280×800。
- 测试 APK：`android/app/build/outputs/apk/debug/app-debug.apk`，版本 `0.1.0-debug`，包名 `com.roombeacon.shell.debug`，约 0.8MB。
- 最终 APK SHA-256：`effa35ed208963e5fa94f8b98aef88fbac58d6b70f165a48410f451f98e90160`。
- `assembleRelease` 已通过，产物未配置正式签名，不能作为正式发布交付。
- 回环模拟服务通过 `adb reverse tcp:8765 tcp:8765` 提供页面和测试日程。屏幕固定标注“仅样机测试”，签到位置显示“TEST ONLY / 非签到码”，包含实际品牌动画。

## 已通过

| 检查 | 结果与范围 |
|---|---|
| Android 构建 | JDK 17、Gradle 8.9（官方 SHA-256 核验）、AGP 8.7.3、SDK 35；debug/release 构建通过 |
| Android 单元测试 | 4 项通过，覆盖来源边界、非法配置、密码验证和退避上限 |
| Android lint | `lintDebug` 通过，未用 baseline 忽略错误 |
| 前端 | `npm ci`、`npm run build`、39 项 Chromium 回归测试通过 |
| 真实 WebView 显示 | V3、SVG 测试图片、品牌 GIF 正常显示；页面高度 800px，无横向溢出 |
| 老内核高度兼容 | WebView 106 实测不支持 `dvh`，`vh` 降级生效 |
| API 503 | 显示“状态暂不可确认”，恢复 200 后恢复会议显示 |
| 传输中断 | 移除本任务 ADB 回环隧道后转未知，恢复隧道后自动恢复；不是物理拔网线测试 |
| API 401 | 清除绑定和旧日程，提示重新绑定；仅模拟凭证 |
| 应用进程重启 | 强制停止并手动启动后保留服务器和网页绑定；不等于开机自启验收 |
| 页面发布 | 同一 APK 完成 fixture-a→b→c→a，两次升级和一次回退；实机浏览器时钟加速，测试中清除刷新冷却标记，非真实持续墙钟运行 |
| 页面更新保护 | 桌面 Chromium 验证缺失入口脚本时不刷新、自动刷新保留绑定及短期冷却 |
| 冷启动页面 503 | 原生故障覆盖层可见，迟到的页面回调不能清除故障；服务恢复后自动加载 |
| 渲染进程崩溃 | 通过调试协议主动触发；验证真实退出回调、APK 主进程 PID 不变，并自动恢复且保留绑定 |
| 原生维护入口 | 错误密码被拒绝、正确密码进入设置并返回门牌；自动化须等待设备 UI 切换稳定 |

首次真实设备测试发现 WebView 在 HTTP 错误后仍可能发送页面开始/完成回调，导致短暂隐藏错误。已修复：失败只允许由显式重试清除；最终 APK 通过该回归和渲染恢复检查。

## 内存观察

模拟页面含品牌动画，测试期间一次采样：APK 主进程 PSS 127090KB（约 124MiB），独立 WebView 渲染进程 PSS 83150KB（约 81MiB），整机 MemAvailable 978476KB（约 956MiB）。没有把主进程当成总开销，也没有把瞬时采样当成峰值、长稳或无泄漏结论。

## 复现与证据

构建、安装与模拟服务见 [Android README](../android/README.md)。自动化依赖前端 `npm ci` 安装的 Playwright；使用 Android WebView 专用连接，不套用桌面 Chrome 的浏览器上下文管理。

```bash
ROOMBEACON_TEST_SERIAL=DEVICE_IP:5555 ROOMBEACON_ADB=/path/to/adb \
  node android/tools/device-smoke.mjs
```

脚本仅接受明确目标设备与 `http://127.0.0.1:8765/` 测试页。`ROOMBEACON_TEST_FILTER` 可筛选检查；`ROOMBEACON_TEST_OUTPUT` 可指定结果目录。不会连接真实飞书。

本次本地证据（均不入库）：`.local-tools/device-test/`（显示、API 和页面更新）、`.local-tools/device-recovery-final/`（最终 APK 恢复回归）、`.local-tools/device-network-final/`（连接中断）、`.local-tools/maintenance-test.log`、`.local-tools/android-build.log`。维护密码单独保存在 `.local-tools/device-maintenance-pin.txt`，文件权限 600，不写报告或日志。

## 尚未验收

- 新独立服务端域名、TLS 和真实飞书权限/数据/官方二维码，等待用户资源。
- 默认桌面、Device Owner、断电上电自动开机：未改变样机原有系统管理配置。
- 实际拔网线/断电、看门狗、灯条接口、多型号/多 Android 版本适配。
- 72 小时与 7 天长稳；未进行持续内存趋势和帧率测量。
- 逐设备身份、30 天凭证续期、远程运维、离线冷启动日程、正式 APK 签名分发。

当前样机依赖本开发环境的模拟服务与 ADB 隧道；它是开发演示，不是独立部署。后续正式服务到位后，经维护入口更换 origin、重新绑定即可联调。
