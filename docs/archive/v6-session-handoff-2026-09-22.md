# V6会话归档与接续（2026-09-22）

用户要求本次改动推送GitHub并归档会话。以下为本会话已确认的交付和最后一次发布回执，不覆盖其他任务之后的变更。接续优先读本文件、[当前状态](../current-state.md)及对应GitHub Issue。

## 已推送与交付

- V6设备自动注册、后台认领、六位辅助码/SN/MAC、管理员/只读、配置历史/模板/回执/回退、远程刷新：PR [#11](https://github.com/arthurxbwang/roombeacon/pull/11)。地区节点只预留协议，尚未实现异地分布式部署。
- 发布健康探针修复及首次回退证据：PR [#12](https://github.com/arthurxbwang/roombeacon/pull/12)。硬件MAC与APK交付：PR [#15](https://github.com/arthurxbwang/roombeacon/pull/15)。
- 飞书登录首页、事务内首位员工管理员初始化：PR [#18](https://github.com/arthurxbwang/roombeacon/pull/18)，发布记录PR [#19](https://github.com/arthurxbwang/roombeacon/pull/19)。用户已真实登录并确认本人，核验唯一员工管理员、企业锁定及一次消费审计通过，[#17](https://github.com/arthurxbwang/roombeacon/issues/17)已关闭。
- 退出按钮：匿名隐藏、已认证待授权显示“退出登录”、后台右上角退出；失败保留重试。PR [#21](https://github.com/arthurxbwang/roombeacon/pull/21)已合并，[#20](https://github.com/arthurxbwang/roombeacon/issues/20)已关闭并保存准确静态发布/回退回执。
- 测试包：[V6 / 0.6.1-debug](https://github.com/arthurxbwang/roombeacon/releases/tag/v0.6.1)，versionCode8。APK SHA-256：`65760f3367658c1493b389a62de4d00448da6c85efecd5d11c959368812ec975`。

## 最后一次生产回执

| 项目 | 版本或位置 |
|---|---|
| 生产域名 | `https://roombeacon.thundersoft.com`，SSH8081，`/data/roombeacon` |
| 后端SHA | `8915b38b05ec54ef3ef186803afb38d7ef9ff9e4` |
| 静态SHA | `921ba26457e84a1bdc4c81c213f323941e633122` |
| APK | 0.6.1-debug；本轮网页修复没有更新APK |
| 最新静态备份 | `/data/roombeacon/backups/logout-ui-20260922T112637Z/nginx.before` |
| 登录发布备份 | `/data/roombeacon/backups/v6-20260922T111556Z/` |

静态发布从GitHub取源码、服务器构建后切换Nginx root，后端PID未变。静态回退恢复上述nginx.before并检查、reload，后端不需重启。登录发布完整回退见[登录记录](../production-feishu-login-2026-09-22.md)。源码、静态和APK版本分别管理，归档文档合并不意味着再次部署。

一次性管理员初始化已消费：必须保留SQLite内`feishu_first_admin`、`feishu_login_tenant`及审计，不删除或恢复旧空库重开。开关即使仍为true也不会再授予管理员；后续员工pending，权限由管理员明确授予。既有主控API保留应急兼容，不属于另一个员工账号。公开归档不包含员工姓名、身份标识、授权码或凭证。

## 样机与ADB

- BX68：自动纳管、升级保留身份、配置回执、厂商启动项适配及修正历史SSID后的开机恢复已实测。
- 用户已在厂商后台关闭BX68网络ADB；两次探测5555拒绝连接，回到RoomBeacon后管理心跳恢复，纯HTTPS远程刷新真实回执4/4，网页业务心跳ready。此结果限于当时测试路径，不等于重启持久性或全端口审计通过。
- 原生管理轮询在Activity暂停时停止；停留厂商设置页时心跳暂停，不能直接归因于关闭ADB。
- 旧北京201：最后复测仍存在DNS/生产网络障碍，未注册V6，5555仍开放；不能把BX68验收套用到旧机。

## 检查与后续工作

已完成的检查：后端280项（隔离Redis、无跳过，生产再次通过）、最新前端94项Chromium及构建、Android0.6.1的14项单元测试/lint/build、发布探针2项。此归档只改文档，不将这些历史结果称为重新执行。

- [#10 V6剩余实机验收](https://github.com/arthurxbwang/roombeacon/issues/10)：旧北京201接入、PoE/网线切换、72小时/7天长稳。飞书首位管理员已验收，不再作为缺失条件。
- [#16 无ADB更新与维护](https://github.com/arthurxbwang/roombeacon/issues/16)：关闭ADB的重启保持、真实页面升级/回退、APK安全更新通道、无ADB诊断与现场恢复。当前网页/配置管理可用，但远程APK安装、完整MDM和远程控制尚未实现。
- 后续硬件/型号模板任务按各自分支和Issue继续，不混同于本会话已发布的0.6.1。未提交开发内容不因本会话归档而自动获得发布或验收结论。
