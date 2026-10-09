# PR #55 评估、上线与 APK 覆盖升级验证

2026-10-09；用户要求评估 [PR #55](https://github.com/arthurxbwang/roombeacon/pull/55)、检查冲突，必要时合并上线并测试 APK 升级。评估确认修复有必要，已完成冲突处理、检查、合并、后台发布与单台正式 APK 升级。需求 [#52](https://github.com/arthurxbwang/roombeacon/issues/52) 已关闭。

## 冲突与评估

最新 main 中共 6 个冲突文件，已全部解决：

| 文件 | 冲突及处理 |
|---|---|
| `frontend/src/pages/V6Control.vue` | #55 页面／灯控健康列与 #56 删除操作在同一表格行；同时保留两者，管理员／只读权限不变 |
| `backend/app/management/installation_admin.py` | 管理心跳新校验与 #56 deleted 拒绝重叠；同时拒绝 revoked／deleted、离线及未来时间心跳 |
| `CHANGELOG.md` | 两个需求各自新增头部记录；按日期保留双方 |
| `docs/current-state.md` | 原生修复／绑定记录与最新上线状态重叠；保留历史并补充本轮最新状态 |
| `docs/handoff.md` | 接续摘要重叠；保留双方历史 |
| `plan/next-phase.md` | 后续事项摘要重叠；保留已上线与未完成边界 |

灯控恢复后的残留错误、配置回执无法代表持续页面健康是实际缺陷。修复按错误来源清除，页面就绪取当前同源主文档的真实 JS 探测，限制加载代际、WebView 实例和回调时间；后端叠加回执年龄。运行字段不携带会议内容或凭证，不授予签到／释放资格。身份代码、包名、Keystore 别名、设备配置及模板保持。未发现需要阻止发布的问题。

## 准确版本

- 后台／前端合并和生产应用：**`9314125493b71278de87ff3635aafdbae1df253a`**；用户批准的独立 `roombeacon.thundersoft.com`、`/data/roombeacon`，SSH 8081，主机 `tsm-eed-ts-bj`。
- 发布前应用：`3d0b1e1958c4961b55ecc3ed8910f901f073cfe3`。服务器直接从 GitHub 获取源码，归档准确 SHA 后构建部署；依赖和 Python 环境不变。
- 正式 APK：`com.roombeacon.shell` **0.7.1（versionCode 11）**，非 debuggable；APK SHA-256 `326790124fb239893ee35cf638b8ce519470e775ada9fe6bfebaac8d1ccc25c4`，大小 652808 字节。
- 原项目证书 SHA-256：`25507df796edaf177caafac66c3b88842fe423b002234a7cc8afa89ad54e687a`，与当前 0.7.0 相同，未生成新签名。
- APK 从已合并源码 `49f81e175675f1cf746b11946b6af2063ab157ea` 构建；该提交与最终应用的 Android 内容一致（树 `bc7467706b6a99241899bd59d10462f792c363d7`）。对齐与签名校验通过。
- 已核验包留在 `/data/roombeacon/shared/installation-packages/roombeacon-0.7.1-326790124fb2.apk`。当前默认首装包仍是 0.7.0，未扩大首装网段或批量升级；旧包及其首装历史保留。

## 后台先行与真实覆盖升级

先备份 SQLite、环境、设备配置、已发布版本、房间／主控、策略与 17 条记录，核对无 waiting／checking／releasing／end_requested 在途记录，发布兼容新 runtime 的后台。旧 APK 0.7.0 仍在线 2/2、业务心跳健康，页面健康显示未知；不能把旧包没有上报解释成页面正常。

对 BDC5ZS／`10.0.51.221:5555` 核对原首装任务对应的实物序列号、型号 RK3568及固定 ADB transport。拉回已安装 0.7.0，确认其 SHA-256 仍为 `c2a6acc96872922edcc0aefae04725352098a61fb2479d9d0094440ded445c8b`，证书与新包一致，版本从 10 升至 11；再次核对没有在途操作后执行 `install -r`，随后启动主 Activity。

真实结果：

- 安装返回 Success；安装后拉回 APK，摘要、证书与批准 0.7.1 完全一致。
- **应用 UID 和 firstInstallTime 保留，lastUpdateTime 改变**，证明是覆盖更新；没有卸载、清数据、降级、重置或更新系统 WebView。
- 仍是原 BDC5ZS、同一设备 ID 和凭证摘要，修订／回执 **2/2**，在线、无应用错误。原身份能够继续认证，配置、会议室和业务主控保持，没有新增替代设备。
- 实际新回执：page ready、light ok；H5 为 `9314125493b71278de87ff3635aafdbae1df253a`，WebView **106.0.5249.79**。实际业务数据可读，主控业务心跳健康。
- 17 条原记录 state／verified、原规则／暂停、发布版本、安装关联保持，343 间／18 批完整采集失败 0；升级后最终核对于 **11:22:27（北京时间）**完成，后续只读又观察到实际 busy 数据和正常灯控回执。
- 真实管理员后台桌面／390px 详情显示 0.7.1、页面正常、灯控正常、实际 H5／WebView；#56 删除入口仍在，移动端无横向溢出，页面错误 0。截图私密保存，未提交 Git。

本轮完成的是 **通过现有 ADB 的单台同签名覆盖升级**。现有“首装与交付”仍会拒绝覆盖不同已装 APK；后台一键升级、无 ADB 更新、升级任务队列仍由 #16 接续，不能据本轮宣称已经实现自动升级通道。首装记录继续表示原 0.7.0 安装事实，升级不自动完成冷启动、ADB 关闭、PoE 或完整交付验收。故障恢复边界由隔离测试覆盖，本轮未额外注入真实 GPIO 写入故障或 WebView 崩溃。

## 检查与回退

本地及生产后端 **446 项**全部通过，无跳过；外部系统 mock、Redis 临时隔离。npm ci、类型检查／构建、本地及生产 Chromium **158 项全量**通过；Android **31 项单测**、lintDebug、assembleDebug、assembleRelease、APK 对齐及正式签名核验通过。Ruff 0.16.7、`git diff --check`、Nginx 语法和 HTTPS 检查通过。

私密基线与升级记录：`/data/roombeacon/backups/native-health-55-20261009T030949Z`。包含 `baseline.json`、`backend-verified.json`、`apk-before.json`、拉回的旧／新 APK、`v6.before-apk.sqlite3`、`apk-install.json`、`upgrade-verified.json`、真实后台截图及检查日志；目录 0700、文件 0600，未把凭证或私钥写入公开资料。部署脚本备份：`/data/roombeacon/backups/v6-20261009T031531Z`。

新 APK 已上报 runtime，直接切回不兼容旧后台会被其严格元数据校验拒绝；回退先维持 runtime 协议兼容。APK 普通降级未验证且正式包可能被平台拒绝，不能通过卸载清数据绕过；必要时使用原签名、较高 versionCode 的修复／恢复包，保留应用数据与设备身份。不要整库覆盖后续账号、交付、设备或业务记录，不重置已保护预约。默认首装包未切换，无需回退该配置。
