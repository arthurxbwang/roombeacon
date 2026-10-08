# 首装与交付：IP 检测和初始化（#43）

更新：2026-10-08。本次简化日常安装流程；正式 APK 和真实首装仍待验收。对应 [Issue #43](https://github.com/arthurxbwang/roombeacon/issues/43)，阶段边界见[完整计划](../plan/device-delivery-maintenance.md)。

## 当前可以做什么

后台 `/control` → **首装与交付**，默认仅显示设备 IP 和“检测设备”。后台直连 ADB，返回型号、序列号、Android 版本和已有门牌应用情况。检测不安装、不启动应用、不修改设备设置。通过后点击“确认初始化”，自动安装默认正式 APK、拉回核验并启动，然后在下方任务关联屏幕短码、配置会议室和记录现场验收。

“高级设置与现场助手”默认收起。只有后台无法访问设备网络时，才使用原现场助手和批次清单；日常直连流程不需要登记电脑、手填序列号或粘贴 APK JSON。

初始化是应用首装，不是恢复出厂设置。已装门牌的设备提示前往设备台账核对短码；默认 APK 缺失、签名未通过、型号不匹配时给出具体原因。正式签名证书由发布负责人审批保管，系统不生成或传输签名私钥。正式 APK 配置完成前可以检测设备，但不能以现有调试包冒充正式初始化。

本轮只修改首装模块及其执行配置、测试和文档。沿用现有待部署短码、房间配置和原生回执；Android、门牌业务、签到和模板逻辑没有变更。ADB 手动关闭、PoE 断电复验继续使用原交付记录。

## 后台直连的一次性配置

配置由运维完成，保存在服务器私有环境文件；不要提交密钥或 APK 到仓库。工具和正式 APK 使用固定绝对路径，应用账号只读。服务端环境变量：

| 变量 | 用途 |
|---|---|
| `ROOM_DISPLAY_INSTALL_NETWORKS` | 允许访问的 RFC1918 IPv4 CIDR，逗号分隔；默认空，禁止探测。初次可仅放行测试机 `/32`，批量交付前配置批准的实际设备网段 |
| `ROOM_DISPLAY_INSTALL_PORT` | ADB 端口，默认 5555；输入 IP 不可连接其他端口 |
| `ROOM_DISPLAY_INSTALL_ADB` | 受控 ADB 工具路径，须支持 transport ID |
| `ROOM_DISPLAY_INSTALL_APK` | 默认已批准的正式 APK 文件路径 |
| `ROOM_DISPLAY_INSTALL_AAPT` / `ROOM_DISPLAY_INSTALL_APKSIGNER` | SDK 工具路径；apksigner 需要 Java |
| `ROOM_DISPLAY_INSTALL_CERT_SHA256` | 发布负责人批准的签名证书 SHA-256，64 位十六进制 |
| `ROOM_DISPLAY_INSTALL_MODELS` | APK 适用的准确型号，逗号分隔 |

安装前自动从 APK 快照生成清单，核对正式包名、非 debuggable、单一签名、批准的证书指纹、文件摘要和型号，不需要在后台手工登记 JSON。更换 APK 后旧检测结果不能用于安装。

生产 ADB 建议采用仓库 `scripts/production/roombeacon-installation-adb.service`：专用无登录账号 `roombeacon-adb`，账号 home 为 `/data/roombeacon/shared/installation`，目录属该账号且 0700；受控 ADB 位于 `/data/roombeacon/tools/installation/adb`。服务只监听回环 5041，默认 ADB 密钥由这个独立账号在其 home 中生成，保留用于重启后连接，不复制开发机密钥。服务关闭 mDNS 自动连接与模拟器端口扫描。

后台在单独的 `80-installation.conf` drop-in 引用私有 `installation.env`，加 `ANDROID_ADB_SERVER_PORT=5041`。正常应用部署不会覆盖此 drop-in；ADB 进程独立于应用重启。只配置网段和 ADB 即可先检测，正式 APK 缺失会显示未就绪。系统不开放公网 ADB，也不提供任意命令接口。

## 直连任务和故障处理

检测结果有效 5 分钟并绑定当前管理员。更改 IP 或过期需重新检测；确认请求只传检测 ID。后台保存探测身份和清单，安装时重新读取序列号、型号，并固定 ADB transport ID，防止 IP 被另一台设备复用。点击确认后持久化任务，再启动后台执行；重复确认或响应丢失后重试都返回同一任务。

后台直连同一时刻只执行一台；现场助手与后台直连共用 IP／SN 占用保护。执行期限十分钟，进程退出、未预期错误或过期进入“结果待核实”，不会自动重装。失败后核实设备再重新检测；待核实任务需确认原进程已停止、等期限结束并显式结束任务后再检测。已安装的应用可通过原设备台账完成配置，不会为重试而卸载。

新增接口均位于原安装模块：只读 `GET /server`；管理员及 CSRF 保护的 `POST /probe`、`POST /initialize`。新增 `install_probes` 表，其他表和设备协议兼容。真实检测结果只保存在受保护的安装接口和审计，不把 ADB 原始输出放入日志。

以下为保留的现场助手方式。

## 现场准备

1. 新设备接电并手动联网，记录实际型号、序列号、IP、ADB 端口。首版接受 RFC1918 内网 IPv4；每批最多 100 台。
2. 现场电脑安装 Python 3.10+、Android SDK platform-tools（ADB，支持 `transport_id`）和 build-tools（`aapt`、`apksigner`），以及运行 apksigner 所需 Java。助手仅使用 Python 标准库。Windows 可指定 SDK 的 `.exe`／`.bat` 路径；当前自动测试在 Linux，Windows 现场兼容性另验。
3. 核对生产域名 HTTPS、设备可联网且首次 ADB 授权已完成。电脑须能够访问后台和这批设备；设备须能访问生产域名。不会扫描网段或自动接受设备授权。
4. 取得同一正式签名的、非 debuggable 的完整单 APK。当前样机 `com.roombeacon.shell.debug` 不属于本工具的覆盖迁移目标；不能以卸载样机、清数据或临时调试签名代替正式发布。

## 现场助手首装操作（网络不通时备用）

以下为准备好正式 APK 后的命令示例，不代表该文件已生成或可直接发布。先验证并导出清单，型号必须是设备 `ro.product.model` 的准确值：

```bash
python scripts/roombeacon_installer.py inspect-apk \
  --apk /secure/releases/roombeacon-release.apk \
  --model BX68 \
  --aapt /opt/android/build-tools/35.0.0/aapt \
  --apksigner /opt/android/build-tools/35.0.0/apksigner
```

1. 在后台登记电脑名称，生成一天有效的助手凭证。凭证只展示一次，离开页面即清除；丢失时撤销并重新登记。
2. 在后台登记命令输出的清单。核对包名、版本、文件 SHA-256、证书 SHA-256 和适用型号；后台登记是管理员批准，实际签名验证由助手的 `apksigner verify` 完成。
3. 选择助手和清单，粘贴每行 `IP 序列号 [端口]`。默认端口 5555，预览实际目标后提交。相同请求重放不创建重复任务；排队、执行中或待核实任务会占用 IP 和序列号。
4. 在这台现场电脑启动助手，传入同一 APK 和允许访问的具体网段。按提示隐藏输入助手凭证；不要把凭证写入命令行、提交记录或截图。也支持受控环境变量 `ROOMBEACON_INSTALLER_TOKEN`，不会传给 ADB 子进程。

```bash
python scripts/roombeacon_installer.py run \
  --server https://roombeacon.thundersoft.com \
  --apk /secure/releases/roombeacon-release.apk \
  --allow-network 10.0.51.0/24 \
  --adb /opt/android/platform-tools/adb \
  --aapt /opt/android/build-tools/35.0.0/aapt \
  --apksigner /opt/android/build-tools/35.0.0/apksigner
```

5. 助手逐台完成本地 APK 快照校验、连接、序列号／型号核对、安装、拉取实际 APK 复核和启动。连接用 ADB transport ID 固定；不会在断连后自动按 IP 重连继续安装。已存在完全相同 APK 时跳过安装并核验启动；已有调试包或不同 APK 则停止该台。没有覆盖、降级、卸载、清数据、root 或任意 shell 接口。
6. 无可领取任务时助手退出；新增任务后重新运行。同一助手按顺序执行；普通失败不阻断后续设备，通信中断或未知执行结果需要先核实。
7. 门牌自动注册后，后台按六位短码关联任务。须核对实物序列号与屏幕；Android 普通应用可能无法上报 SN，因此不以 IP／SN 自动推断注册身份。若原生能上报 SN，则服务端要求一致；型号与 APK 版本也必须一致。
8. 点“房间配置”复用已有软硬件模板部署。等待设备在线、配置回执一致且无错误，逐项完成画面及业务数据新鲜度、灯控、冷启动、手动关闭 ADB、关闭后 PoE 真断电复验，并登记安装位置和交换机物理端口。

关闭 ADB 后要从现场确认连接失败；再次 PoE 断电上电后确认身份、房间、画面与灯控保持、ADB 仍关闭。交换机管理重启不一定切断 PoE，数据端口禁用也不等于断电。页面的五项勾选是具名人工验收记录，不是自动电源或页面健康探测。

## 中断、重试与撤销

| 状态 | 含义与处理 |
|---|---|
| 等待助手领取 | 可取消；取消不涉及设备。助手过期后仍排队的任务也可以取消，换新助手重新登记 |
| 安装执行中 | 十分钟执行期限内独占任务；此时不能取消或转交，撤销 HTTP 凭证无法撤回已经运行的 ADB 命令 |
| 安装失败 | 查看固定错误类别，处理现场问题；等待原执行期限结束并停止旧助手，再明确确认重试 |
| 结果待核实 | 领取响应丢失、助手退出或执行期限结束后不能确定结果；不会自动重新排队，也不继续该助手的下一台 |
| 核实后重试 | 停止旧助手、核实实物、执行期限结束且助手凭证仍有效后重排；相同 APK 将只恢复启动 |
| 结束待核实任务 | 停止旧助手并等待期限结束后归档；释放目标占用，可换新助手新建任务；不会卸载已安装 APK |
| 安装完成，等待关联 | 仅证明助手已核验安装和启动，还要短码关联、房间配置与现场验收 |
| 已记录现场验收 | 保存当时的设备修订、房间、位置、端口和人员；当前在线状态单独展示，配置、版本或身份变化后须重新验收 |

报错只上传固定类别，ADB／厂家命令原始输出和设备凭证不上传。不同助手不能领取或回报他人的任务；管理员凭证不能用作助手凭证。凭证到期或撤销即阻止后续领取、核验和回报；现场独立停止已启动操作仍由人员完成。迟到回报不能覆盖新一轮结果。安装后回报丢失可在原任务上幂等重放，但助手首版不保存执行凭证至磁盘，进程退出后的未知状态由人工核实。

## 接口与持久化

- 管理员／只读会话：`GET /api/v6/admin/installation` 返回助手（无密钥）、批准清单、最近 1000 条任务和验收状态。
- 管理员写接口：同前缀 `/executors`、`/executors/{id}/revoke`、`/releases`、`/batches`、`/jobs/{id}/{cancel,retry,resolve,associate,accept}`。浏览器写入校验 CSRF，所有任务写入检查修订号。
- 助手专用凭证：`POST /api/v6/installer/claim`、`/jobs/{id}/check`、`/jobs/{id}/report`。任务执行凭证仅发给所属助手，不出现在列表和审计中。
- 原有 V6 SQLite 库新增 `install_executors`、`install_releases`、`install_batches`、`install_jobs`。凭证只保存摘要；任务领取在数据库事务中串行化；现场助手和后台直连各自使用受控 ADB 连接。
- 原有设备、模板、API、Redis 键和浏览器存储协议保持兼容；新表自动创建。安装动作、短码关联和配置部署各自有审计，不扩大业务写入白名单或复制签到资格。

## 原现场助手版本验证（PR #44）

- Ruff 0.16.7 与 `git diff --check` 通过；Python 单文件与 Vue 单文件符合仓库行数限制。
- 后端全量 383 项通过、无跳过，包含新增 API／现场助手 25 项。测试 Redis 使用临时 Unix socket；飞书、ADB 设备与安装操作隔离模拟。
- `npm ci`、TypeScript／Vite 隔离构建通过；Chromium 全量 140 项通过，含新增首装范围预览、幂等重试、短码关联、配置入口、验收、只读权限及凭证清理 4 项。浏览器截图为测试数据，已检查实际页面布局。
- 本地 SDK 35 的 `aapt`／`apksigner` 对仓库现有 `app-debug.apk` 和 `app-release-unsigned.apk` 执行真实检查，助手均以 `apk_invalid` 拒绝。未安装任何设备，也未生成正式发布密钥。
- Python 测试保留现有 Starlette／httpx 弃用提醒，不影响通过结果。本轮 Android 源码未变，未重复进行 APK 构建或将浏览器测试视为原生验收。

## 发布与回退

原现场助手版本从 GitHub 部署 `3d0542dde4677ed1c43ae09b90051379f1d9fc08`（PR #44），历史验证见[首次发布回执](production-installation-2026-10-08.md)。IP 流程对应 [PR #46](https://github.com/arthurxbwang/roombeacon/pull/46)，专用 ADB 服务参数修正见 [PR #47](https://github.com/arthurxbwang/roombeacon/pull/47)；生产切换须记录准确合并 SHA，回退应用为上述 `3d0542d`，不恢复旧数据库或 Redis。首次配置时仅放行样机 `10.0.51.221/32`；新设备交付前由运维扩展批准网段。正式装机前仍须明确正式 APK 签名／摘要、助手脚本版本、单台试点和窗口；首台真实通过后再扩批。

应用回退前停止现场助手、撤销凭证、核实在途任务并备份当前 SQLite（含 WAL 的一致性备份）。旧应用可忽略新增表，但不得恢复旧库覆盖新设备身份和配置。APK 首装不自动回退：失败设备保留现场状态，按批准的恢复方式处理，不能以卸载清数据实现默认回退。

未验证项：正式发布密钥／正式包、新批次 ADB 首次授权、Windows 工具调用、真实冷启动和 PoE 关闭保持、2GB 长稳、厂家静默安装／守护权限、交换机连接器与自动电源恢复。自动测试不替代这些实机证据。

## IP 流程验证

- 本地后端 402 项通过，含首装相关 44 项；覆盖权限和 CSRF、网段／端口限制、无 APK 仍可探测、已有应用和型号不符、探测过期／归属、APK 变化、并发幂等、执行超时及未知故障不误报成功。
- Chromium 143 项通过，含首装 7 项；默认高级设置收起，检测不安装，明确确认后创建任务，输入变化／过期／未授权／缺包时不能误操作。Ruff、TypeScript／Vite 与差异检查通过。
- 自动化安装场景隔离真实设备；正式签名 APK 首装、开机恢复、关闭 ADB 和 PoE 仍需独立实机验证。
