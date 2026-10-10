# 首装取消网段白名单上线回执（2026-10-10，#70 / PR #71）

用户明确授权上传 GitHub、PR、合并及直接生产上线。需求[#70](https://github.com/arthurxbwang/roombeacon/issues/70)经[PR #71](https://github.com/arthurxbwang/roombeacon/pull/71)合入，准确应用 **`35ca0d9fb5954308f008932fb94cd02bd3776882`** 已部署到独立生产 `roombeacon.thundersoft.com`、主机 `tsm-eed-ts-bj`、SSH8081、`/data/roombeacon`。原应用／回退基线为 **`27b4b3009b7001238636de50d1dafad75107e11f`**。

## 变化及实际检测

后台和新版现场助手取消固定 IP／CIDR 白名单。旧 `ROOM_DISPLAY_INSTALL_NETWORKS=10.0.51.221/32` 私有环境值保留，实际已认证 `/api/v6/admin/installation/server` 返回 `probe_ready=true`、`networks=""`、ADB端口5555，旧值不再拦截设备。新版助手无需 `--allow-network`；旧命令接受该参数并提示已弃用。

任意站点的 RFC1918 内网 IPv4 可作为首装目标；管理员／CSRF、ADB端口、正式APK、型号／序列号、固定transport及安装后核验保持。跨站点服务器无法直达设备时，在当地运行现场助手；取消名单不自动建立路由。公网、域名及IPv6仍不属于现有首装协议。

15:42:10通过实际生产HTTPS安装接口，只读检测用户提供的 **`10.0.51.170` 返回200**：型号 `rk3568_r`、Android11，已存在门牌应用，`can_initialize=false`，提示“已检测到门牌应用，请在设备台账中核对屏幕短码并配置会议室”。已通过原白名单拦截点；本次没有安装、启动、卸载或配置这台设备。只读检测增加检测记录和审计，不新增安装任务。

## 验证与现有状态

- 本地首装63项、全量后端590项及Chromium181项通过，无跳过；Ruff0.16.7、npm ci、隔离构建、1440px／390px渲染及diff检查通过。回归先在旧实现复现拦截，再验证名单缺失／残留／无效、其他站点、认证／端口／连接失败及助手CLI兼容。
- 生产从GitHub获取并核对准确合并SHA，使用该提交的发布脚本归档构建。生产Ruff、590项后端、npm ci／构建、181项Chromium通过，无跳过；后端保留两条既有依赖弃用提示。脚本在私有umask下修正公开dist权限，本机Nginx／外网准确页面及JS／CSS探针通过，无应用回退。
- 发布前无在途首装／释放任务，临时暂停释放。15:41:41重启后首轮采集开始，15:42:40完成343间／18批／失败0；原15条预约的状态、核验、期限和实例及原模板、版本、账号、设备身份／配置、房间策略、凭证、日历来源与私有配置摘要保持。
- 15:45:41 BDC5ZS已自动加载准确新H5 `35ca0d9`，页面ready、灯控ok、配置2/2、无错误，APK0.7.1和WebView106不变；W9TW7S仍离线，保持原12/10，不替代验收。无需ADB刷新或APK升级。
- 15:45:41恢复发布前释放开关，15:45:57最终已认证API确认 `auto_verify_enabled=true`、`release_enabled=true`、`paused=false`；343份新鲜快照与来源配对、真实业务心跳健康。`resume.json`中的 `release_enabled=false` 为恢复暂停前读取，最终状态以随后 `verify.json` 为准。

未经认证的安装状态、设备、管理及业务入口仍401；本轮不更新Android源码或APK，不下发设备模板、不关联短码、不提交签到或释放。真实新设备首装、跨站点路由及现场交付验收仍需单独执行，详情见[操作说明](installation-delivery.md#跨网段与跨站点安装)。

## 备份和准确回退

- 本轮私有备份：`/data/roombeacon/backups/install-no-allowlist-70-20261010`（0700），保存SQLite一致性备份、私有配置、Nginx、原设备／模板／策略／凭证摘要、预约、检测及部署／浏览器日志。
- 发布脚本备份：`/data/roombeacon/backups/v6-20261010T074049Z`。
- 原准确应用：`27b4b3009b7001238636de50d1dafad75107e11f`。

回退前停止新版现场助手，核实在途安装任务并暂停释放；恢复原应用软链接和脚本备份的Nginx配置，检查语法后重启应用／重载Nginx。保留当前SQLite和Redis，不整库恢复、不清记录或设备身份。私有名单环境值本轮未改，旧应用回退后会重新仅放行原样机 `/32`；需明确告知新设备检测再次受限。核对采集、准确H5／资源和真实设备健康后恢复发布前释放状态。APK及已首装设备不会随应用回退自动卸载。
