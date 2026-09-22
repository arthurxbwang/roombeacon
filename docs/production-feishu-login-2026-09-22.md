# 飞书登录与首位管理员发布（2026-09-22）

需求 [#17](https://github.com/arthurxbwang/roombeacon/issues/17)，实现PR [#18](https://github.com/arthurxbwang/roombeacon/pull/18)。用户确认飞书回调配置完成，授权首页使用飞书扫码/快捷登录，并仅此次将首位成功登录员工设置为唯一初始管理员。

## 生产结果

- 前后端SHA：`8915b38b05ec54ef3ef186803afb38d7ef9ff9e4`，生产服务器从GitHub取代码、构建测试后发布；APK保持0.6.1，未重新开启ADB。
- 普通首页进入`/control`，只显示飞书登录；`/?version=v6&managed=1`及`/room-display.html`继续用于门牌。
- 生产首页、后台、受管页面及新JS资源均HTTPS200；新资源含飞书登录界面。真实OAuth引导返回302至`accounts.feishu.cn`，携带一次性state，浏览器Cookie为Secure，回调为`https://roombeacon.thundersoft.com/api/v6/auth/feishu/callback`。
- 私有`v6.env`已开启`ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE=true`。发布后检查员工0、员工管理员0、初始化未消费，等待用户真实登录；探测没有交换员工授权码或创建测试账号。
- BX68原设备短码保持，管理心跳1秒、回执4/4、error为空。本次没有发送新配置或操作真实预约。
- 本地Ruff、后端280项（隔离Redis、无跳过）、前端npm ci/build与Chromium91项通过；生产再次280项通过；发布探针2项通过。Android未修改，不重复运行APK构建。

## 一次性权限规则

发布后用户已实际登录并确认是本人，生产只读核验员工1、管理员1，获选账号为admin，企业锁定一致，初始化消费记录存在且first-admin审计恰好1条；Issue #17已验收关闭。后续登录不会自动成为管理员。员工姓名和身份标识不写入公开记录。

1. 验证浏览器state及飞书授权码，服务端取得真实身份。
2. 使用本应用企业令牌查询该open_id的通讯录记录；读取失败、非本企业可见成员、已离职/冻结/退出均不能初始化。首次登录员工须处于现有应用和通讯录可读范围。
3. SQLite写事务内复核企业、管理员及消费记录；仅一人获admin，记录`meta.feishu_first_admin`、企业锁定`meta.feishu_login_tenant`及`first-admin`审计。8路并发回归只有一个管理员。
4. 后续员工默认为pending，需管理员手动授权。管理员被停用、服务重启或开关再次启用不会重新选举；已有管理员时只记录跳过，不替换或新增管理员。
5. 主控凭证保留既有API和旧主控页的兼容、应急能力，不在V6登录页公开为另一种登录方式；“唯一初始管理员”指这次初始化授予的员工账号，不撤销既有服务维护凭证。

企业信息查询接口当前缺少对应权限，本次没有追加飞书权限。首位员工归属采用现有通讯录用户读取接口验证，核验不成功时不降级为无校验授权。真实扫码与员工核验结果待用户操作，按Issue #17继续记录。

## 回退

本次备份：`/data/roombeacon/backups/v6-20260922T111556Z/`；初始化开关启用前配置另存`/data/roombeacon/backups/v6.env.before-first-admin-20260922T111555Z`。

前后端回退目标：`9cd01a820e6d732611519a0f66eac0e3ddaa8528`。按备份恢复应用链接与Nginx配置、重启服务；如取消待执行初始化，将私有开关设为false。保留当前SQLite及任何已经产生的管理员、企业锁定、消费记录与审计，禁止恢复旧空库重新发放管理员；不清空Redis。旧代码本身不自动初始化管理员，也不识别新企业锁定逻辑，因此已使用后的回退须按运维记录复核登录范围。
