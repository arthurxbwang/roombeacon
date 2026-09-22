# RK3568 门牌 SDK 开发摘要

更新：2026-09-22。供 RoomBeacon 开发及 Agent 按需查阅，依据用户提供的《开发文档-3568.pdf》（91 页）提炼，仅保留与门牌相关的技术信息。原始 PDF、页面图片和 SDK 二进制不上传仓库。

来源文件 SHA-256：`83b421f6b2e86681ce6d3f292ed7b354107f85733278e9abe896fcb6154f842a`。下文页码均为手册**正文页码**，PDF 阅读器页码需加 8，例如正文 62 页对应 PDF 第 70 页。

## 先读结论

- 手册描述厂家 `ysapi.jar` / `MyManager` 系统接口；**当前 RoomBeacon 未接入该 SDK**，本次仅整理资料，没有调用接口或进行样机验证。
- 型号同为 RK3568 不代表系统服务、接口或整机接线一致。必须取得与目标固件匹配的 JAR、服务版本及端子定义，核对实际方法签名。
- 当前已实现的全屏、WebView 恢复和侧灯无需因这份手册而重写。优先研究只读诊断、亮度和启动策略，GPIO 适配另做实机验证。
- 手册示例存在方法名、类型和枚举矛盾；下文保留可定位的接口信息及疑点，不提供可直接执行的整套初始化脚本。

## 现有代码与 SDK 的关系

核对基线为 `190e11dbeb3d84d803a95267e1be2780f754fe58`，APK 0.2.4。后续以最新源码为准。

| 能力 | 当前实现 | SDK 可能补充的部分 |
|---|---|---|
| 全屏及维护入口 | [MainActivity.kt](../../android/app/src/main/java/com/roombeacon/shell/MainActivity.kt)：沉浸式显示、维护 PIN；Device Owner 条件满足时进入锁定任务 | 系统导航栏、通知栏控制；不等于自动获得 Device Owner |
| 页面异常恢复 | [WebShell.kt](../../android/app/src/main/java/com/roombeacon/shell/WebShell.kt)：加载超时、页面心跳、渲染进程退出恢复 | 厂家进程守护；不能替代页面及服务器业务健康检查 |
| 上电启动 | [AndroidManifest.xml](../../android/app/src/main/AndroidManifest.xml)：HOME 别名默认禁用，由维护流程启用并选择桌面 | 固件自启、默认桌面设置，尚未调用 |
| 侧灯 | [RoomLight.kt](../../android/app/src/main/java/com/roombeacon/shell/RoomLight.kt)：型号与固件白名单、sysfs 写入及读回 | 厂家 GPIO 接口；索引映射尚未确认 |
| APK 升级、RS485 | 自动升级和传感器串口驱动均未实现 | 静默安装可后续评估；本摘要中的 GPIO 接口不能替代 RS485 驱动 |

构建配置见 [build.gradle.kts](../../android/app/build.gradle.kts)：当前没有 `ysapi.jar` 依赖。正式包名为 `com.roombeacon.shell`，调试包为 `com.roombeacon.shell.debug`，配置启动或守护时须匹配实际安装包。

## SDK 连接生命周期

手册正文 1—2、15 页：将厂家 `ysapi.jar` 放入应用模块 `libs` 并加入依赖；自 **V5.3-20211028** 起，所有 API 调用改为通过 AIDL 服务连接。

手册给出的顺序是：

1. `MyManager.getInstance(context)` 获取实例。
2. `bindAIDLService(context)` 绑定服务。
3. 通过 `setConnectClickInterface(...)` 注册 `MyManager.ServiceConnectedInterface`，等待 `onConnect()` 后调用接口。
4. Activity 销毁时调用 `unBindAIDLService(context)`；注意名称中的大写 `B`。

**项目接入建议**：由一个明确的生命周期所有者管理绑定，不在每次业务调用前重复绑定。以实际 SDK 确认监听注册时序、断连回调和重连方式；连接未就绪、超时或失败时禁用对应硬件功能并给出诊断，不能报告操作成功。JAR 的导入包名、目标固件权限和服务是否预装仍需厂家样例或实物核对。

## 优先保留的接口

以下签名和语义来自手册，尚未在本项目调用验证。

### 只读设备诊断

| 方法及返回值 | 含义与注意点 | 正文页 |
|---|---|---|
| `String getApiVersion()` | SDK 版本及日期，用于兼容性记录 | 3 |
| `String getAndroidModle()` | 型号；`Modle` 是手册原拼写，不自行改成 `Model` | 3—4 |
| `String getAndroidVersion()` | 示例 Android 7.1 返回字符串 `25`，应按 API 等级核对，不能直接当作系统版本名称 | 4—5 |
| `String getKernelVersion()` | 固件内核版本 | 8 |
| `String getAndroidDisplay()` | 固件版本与编译信息 | 8—9 |
| `String getFirmwareDate()` | 固件编译时间 | 9—10 |
| `int getDisplayWidth(Context context)` | 屏幕像素宽度；高度方法在手册中有冲突，见勘误 | 17—18 |

**项目接入建议**：诊断同时保留 Android 标准的型号、固件与系统版本，增加 SDK 版本以便匹配能力。屏幕物理像素不等于 WebView 的 CSS 宽高；页面适配仍须核对视口及 `devicePixelRatio`，不能仅凭 1920×1080 判断布局。

### 屏幕、导航栏与通知栏

| 方法及返回值 | 参数或结果 | 正文页 |
|---|---|---|
| `void hideNavBar(boolean hide)` / `boolean getNavBarHideState()` | 写入或读回 `true` 表示隐藏导航栏 | 18—20 |
| `void setSlideShowNavBar(boolean flag)` | `false` 禁止滑出导航栏，`true` 允许 | 20—21 |
| `void setSlideShowNotificationBar(boolean enable)` | `false` 禁止下拉通知栏，`true` 允许 | 22 |
| `boolean isSlideShowNotificationBarOpen()` | `true` 表示允许下拉；原文示例调用了错误方法 | 23 |
| `void hideStatusBar(boolean hide)` / `boolean getStatusBar()` | `true` 表示隐藏状态栏，查询结果不是“是否显示” | 28—29 |
| `void changeScreenLight(int value)` | 写入范围 **1—100**，不可按 Android 常见的 0—255 传入 | 23—24 |
| `int getSystemBrightness()` | 手册读取范围为 **0—100**，与设置范围不同 | 26 |
| `void turnOffBacklight()` / `void turnOnBacklight()` | 关／开背光；手册称关闭背光不休眠，软件继续运行 | 24—25 |
| `boolean isBacklightOn()` | `true` 表示背光打开 | 25—26 |

**项目接入建议**：先保留维护退出路径再控制系统栏，重启后读回设置。关闭背光与应用仍在线是不同状态；不能仅凭心跳判断门牌可见，也不能把背光关闭当作已完成节能与恢复验收。

### 开机启动、守护与升级

| 接口 | 关键语义 | 正文页 |
|---|---|---|
| `void setDefaultLauncher(String packageAndClassName)` | 参数为 `包名/启动类名`，不是只有包名；需匹配实际启用的 HOME 组件 | 77 |
| `void selfStart(String packagname)` | 参数为应用包名；与选择默认桌面是不同配置 | 78—79 |
| `daemon(String packageName, int value)` | 守护间隔枚举：`0`→30 秒、`1`→60 秒、`2`→180 秒，默认 30 秒；原文未给返回类型 | 79 |
| `boolean silentInstallApk(String apkPath)` | 文件须完整存在，传入绝对路径；手册说明使用 `pm install -r` | 35—36 |

手册称守护包名 `none` 表示无，但没有说明完整停用流程，也没有明确守护的是进程存活还是界面响应。不得据此认定能恢复所有强停、卡死或启动失败。

**项目接入建议**：在样机分别验证冷启动、进程退出、页面卡死、维护退出与重启后设置保留。记录原桌面以便回退。安装成功还需核对包名、签名、版本、启动结果及绑定数据保留；调试包和正式包不是同一安装身份。当前不实现自动升级。

## GPIO 与 RS485 的边界

手册第九章将参数称为 **GPIO 索引值**，不能直接套用 Linux sysfs 的 GPIO 编号。

| 接口 | 参数或结果 | 正文页 |
|---|---|---|
| `boolean setGpioDirection(int gpio, int arg)` | `arg=1` 输入、`arg=0` 输出；返回设置是否成功 | 62 |
| `String getGpioDirection(int gpio)` | `in` / `out`；无返回值表示该 GPIO 不可用 | 63 |
| `boolean writeGpioValue(int gpio, String arg)` | 仅用于输出口；字符串 `"1"` 高电平、`"0"` 低电平 | 63—64 |
| `String getGpioValue(int gpio)` | 字符串 `"1"` / `"0"` | 64—65 |

当前侧灯直接操作 GPIO154、148、147，白名单分别为旧机高电平 RGB 和 BX68 低电平 GRB，完整映射见[型号与灯控接线](../android-device-profiles.md)。**尚无证据证明 SDK 索引 1 对应 GPIO154**；改用 SDK 前必须确认端子映射、有效电平和读回结果，不扩大到继电器或其他输出。

DP72 的 RS485 A/B 通信另走串口与 Modbus 协议，不能通过这里的 GPIO 高低电平 API 读取人员状态。已有 `/dev/ttyS0` 链路记录及下一步条件见 [DP72 交接与勘误](dp72-rs485-handoff.md)；真实传感器驱动仍待实现。无效、超时或过期数据保持“未知”，不据此自动签到或释放会议。

## 手册中必须避开的歧义

| 位置 | 原文问题 | 开发处理 |
|---|---|---|
| 正文 17—18 页：屏幕高度 | 函数标题为 `getScreenHeight()`，注释及示例为 `getDisplayHeight(Context)` | 用实际 JAR 确认名称及参数，不能凭摘要猜测可编译签名 |
| 正文 21—23 页：滑出栏查询／通知栏控制 | 导航栏查询示例漏括号；通知栏两处示例误用了导航栏方法 | 按实际 SDK 核对，禁止整段复制示例 |
| 正文 24—25 页：背光 | 注释写 `BackLight`，函数标题及调用示例写 `Backlight` | 表中沿用标题；接入时核对大小写 |
| 正文 32—33 页：`setDpi(int value)` | 480 DPI 的枚举在注释为 `4`，参数表为 `3` | 未核实前不设置 DPI，不用该枚举修补页面布局 |
| 正文 63—64 页：GPIO 写入 | 签名为 `String arg`，示例却传整数 `1` | 以实际签名为准，不能假定存在整数重载 |
| 正文 34—35 页：`rebootRecovery()` | 描述同时出现进入 recovery 和恢复出厂设置 | 不纳入日常异常恢复流程 |

## 后续实施入口

1. 获取匹配样机固件的 SDK 与厂家样例，确认服务、权限、方法签名及 GPIO 映射；只读诊断先行。
2. 每次只接入明确需要的一项能力，覆盖未连接、断连、返回失败、生命周期释放及配置回退；再做对应实机验收。
3. 保留现有 WebView 恢复、型号白名单和业务状态保护。业务页面继续在 `frontend/`，硬件接口由 Android 管理，不新增任意网页可调用的系统控制桥。
4. 若后续确需节能，另评估第八章定时开关机（正文 54—61 页）；断电期间没有门牌心跳，不能沿用在线设备的自动释放判断。

网络、音量、开机动画等通用功能本次未摘录；固件升级及恢复出厂设置不作为本项目的常规恢复手段。开发构建见 [Android 说明](../../android/README.md)，传感器工作见 [Issue #5](https://github.com/arthurxbwang/roombeacon/issues/5)。
