# V6 发布与样机验证（2026-09-22）

## 发布范围与版本

用户明确授权一次性开发并直接上线 V6，角色简化为管理员/只读，平板兼容 Wi-Fi 与有线/PoE。飞书开发者后台配置由用户稍后补齐，不把模拟登录算作真实扫码通过。

- 生产：`https://roombeacon.thundersoft.com`，SSH8081，目录 `/data/roombeacon`。
- 后端/前端准确 SHA：`9cd01a820e6d732611519a0f66eac0e3ddaa8528`；从 GitHub 拉取后在服务器安装依赖、构建并验证。
- 主功能 PR [#11](https://github.com/arthurxbwang/roombeacon/pull/11)，发布健康检查修复 PR [#12](https://github.com/arthurxbwang/roombeacon/pull/12)。需求 [#10](https://github.com/arthurxbwang/roombeacon/issues/10)。
- APK：V6 / `0.6.1-debug`，versionCode8，沿用测试包名与签名。SHA-256 `65760f3367658c1493b389a62de4d00448da6c85efecd5d11c959368812ec975`。
- 发布前后旧 `rooms:device:*` 凭证摘要一致；343间缓存目录可读；V5写入范围仍只有IT灯塔-Test，不重置预约保护状态，不创建/取消真实预约。

## 检查与上线结果

- Ruff0.16.7通过；后端267项全部通过，无跳过，使用隔离Redis。生产安装目录再次267项通过。
- 前端npm ci/build通过；Chromium89项全部通过，包含旧门牌与新V6后台。高并发首轮出现既有倒计时用例的时间抖动，降低到2 workers后全量通过；未放宽业务断言。
- Android JDK17/SDK35，14项单元测试、lintDebug、assembleDebug通过。
- 发布探针2项隔离回归通过：暂时404会等待，持续失败仍回退。
- `/control`、`/control/legacy`、V6页面和认证引导HTTPS200。真实主控凭证建立管理会话200，Cookie为Secure/HttpOnly，me返回admin；退出200，随后未授权管理请求401。
- 管理数据库位于 `/data/roombeacon/shared/management/v6.sqlite3`；服务只放开该持久目录写入，私有环境配置在 `shared/config/v6.env`。飞书入口已准备，真实扫码尚待用户回调配置。

## 样机结果

### BX68 / IT灯塔-Test

- Wi-Fi直连生产HTTPS，无ADB转发。升级前保存旧APK；V6首次启动自动注册，待激活页实际显示六位短码、SN和Wi-Fi/有线MAC。
- 唯一码 `W9T W7S`，0.6.0→0.6.1升级后身份与短码保持；普通应用权限读取厂商提供的只读网卡地址，不提升root或Device Owner权限。
- 从主后台API核对设备并认领至原IT灯塔-Test，配置版本2自动应用，后台真实回执2/2、在线、无错误；真实门牌显示房间、服务器缓存与V5状态。
- 后台远程刷新发布版本3，真实回执3/3；配置发布和实际生效分别记录。
- 默认桌面由已记录的 `com.android.launcher3/.uioverrides.QuickstepLauncher` 切为RoomBeacon HOME；第一次重启发现厂商固件仍打开 `com.bjw.ComAssistant`，没有将此轮计为自动恢复通过。
- 已查明厂商 `persist.sys.openapp=com.bjw.ComAssistant` 覆盖普通桌面流程；保存原值后改为 `com.roombeacon.shell.debug` 并再次重启。此后原IP/ADB与后台心跳暂时离线，已向用户请求现场状态/新IP；最终开机恢复未验收通过。不恢复出厂、不设置Device Owner。恢复厂商原启动项可用ADB `setprop persist.sys.openapp com.bjw.ComAssistant`，恢复默认桌面使用上述原组件。

### 旧 RK3568 / 北京201

- 已安装V6 0.6.1，原生待部署页正常，普通应用可读Wi-Fi/有线MAC；SN未获系统提供，明确显示不可用。
- 当前网段10.0.69.*使用公共DNS223.5.5.5，生产内网域名解析失败；到生产10.0.53.174的TCP443、8080均超时。企业DNS10.0.52.52可ping，不代表业务端口可达。
- 尚未自动注册、认领或验证会议室页面。保持待部署/连接失败提示，没有用临时ADB隧道或假数据冒充直连完成。需网络侧允许访问生产HTTPS，并提供正确企业DNS。

## 待完成的外部验收

1. 用户补齐飞书应用回调、可用范围并实际扫码，完成管理员/只读真实账号验收。
2. 旧样机接入可访问生产域名的网络后自动注册，再从后台分配北京201。
3. 现场插接以太网/PoE，验证实际供电、网线拔插及Wi-Fi切换。代码兼容及接口上报不等于PoE实机通过。
4. 72小时/7天长稳单独记录，本轮短时验证不能替代。

## 回退与首轮恢复证据

首次发布SHA9e4e00e后端已就绪，Nginx重载后立即探测HTTPS返回404，自动回退到旧后端/前端成功。随后分别等待后端、Nginx、HTTPS就绪，重试发布成功，未放宽TLS验证。

当前成功发布备份：`/data/roombeacon/backups/v6-20260922T101929Z/`。首次自动回退备份：`/data/roombeacon/backups/v6-20260922T101507Z/`。

旧后端：`3b0bf39cdfdb92e421882444615f8ab7bcb76c8c`，旧静态：`43d8b8f18d5569940cecce53217e7822459191e1`；Python依赖未变，沿用原venv。手动回退按备份backend.before、nginx.before与dropin.before恢复链接/配置并重启服务；保留新SQLite台账，不清空Redis。旧APK保存在开发机私有 `.local-tools/v6-release/*-before.apk`，不提交Git。
