# 背景原格式上传与比例预览上线回执（2026-10-10，#82 / PR #83）

用户明确授权生产上线。需求 [#82](https://github.com/arthurxbwang/roombeacon/issues/82) 经 [PR #83](https://github.com/arthurxbwang/roombeacon/pull/83) 合入，准确应用 **`3aaf5ee7dd91f0239d75675ee6dad8985f22687d`** 已从 GitHub 发布到独立生产 `roombeacon.thundersoft.com`、主机 `tsm-eed-ts-bj`、SSH 8081、`/data/roombeacon`。原应用／回退基线为 **`398f03d382db4e9bea6e5522ff5e1fb25483ed6b`**。

## 上传与显示

静态 PNG／JPEG／WebP 原字节上传，按原文件 3 MB／4096 像素校验；后台显示文件名、实际格式、MB／字节数及尺寸。门牌按实际显示框等比铺满居中裁切或完整显示留白，后台可按常见比例或已上报设备网页比例预览。原图保持，上传失败、取消、上传中保存及切换模板有独立保护。

原 PNG、资源 ID、软件发布／部署流程和认证保持。新增管理员背景元数据读取；终端只能读取自己已部署的资源。正式 APK 0.7.1／WebView 106 沿用，不更新 APK。

## 验证与发布窗口

- 本地 679 项后端、199 项 Chromium 全量及最终 17 项背景定向复核、Ruff 0.16.7、npm ci、类型检查、隔离构建及 diff 检查通过；新增 82 项后端和 17 项浏览器回归，先复现再修复。原图的 16:9／16:10 本地模拟画面已人工检查，不能代替实机选背景后的视觉验收。
- 生产从 GitHub 获取准确合并提交并归档构建；679 项后端、21 项背景／显示偏好 Chromium、JUnit 无失败／错误／跳过、Ruff、网页构建与本机／外网准确页面、JS／CSS 检查通过。生产后端只有两条既有上游弃用提示。
- 图片验证依赖固定为 Pillow 12.3.0。生产下载较慢时，旧服务持续运行，尚未暂停／切换；之后仅停止候选下载，复用与仓库精确版本一致的旧依赖，独立复制到新环境，不引用旧包目录。新增 wheel 经[官方 PyPI](https://pypi.org/project/pillow/12.3.0/) SHA256 核对并在服务器再次验证，离线安装；旧环境包快照前后完全相同，服务账号 JPEG／WebP 支持检查通过。未从开发机复制应用源码。
- 20:04:27（北京时间）核对无活动监控／释放、试点无正在进行或五分钟内开始的预约后，保存最终一致性备份并短窗口暂停；20:04:29 完成新应用／独立环境／Nginx 切换。20:04:28—20:05:24 首轮完整采集 343 间、18 批、失败 0。
- 用户原图真实生产 HTTPS 上传、读回和元数据均返回 200：`image/jpeg`、1,760,654 字节、2752×1536，读回逐字节与附件一致；SHA256 为 `f2b9cafe50841e1e6f69192d1e32c66030283b2480c728b99c6abe9b7bf417ee`。未认证上传、图片及元数据读取均 401。只增加这张原图资源和一条上传审计，原背景资产逐条保留；未修改模板或下发新背景。
- 切换前原 17 条预约、设备身份／配置、账号、模板／版本、规则、凭证及私有环境摘要保持；原资产／SQLite 审计逐条保留。20:09:34 两台真实门牌 BDC5ZS／6QVB94 均已自动加载准确新 H5，页面 ready、灯控 ok、无错误、配置 3/3，APK 0.7.1／WebView 106 保持；无需 ADB 或远程刷新配置。旧 W9TW7S 仍离线。
- 20:11:46 完成新鲜来源配对 343 份、两台实际 H5、权限、原记录与唯一资产／审计增量终验；20:11:47 恢复发布前 `paused=false`，实际已认证 API 复核自动核验／释放均 true、暂停 false。终验前暂停时 `release_enabled=false` 为保护状态，最终开关以恢复后的 `resume.json` 为准。

## 私有备份与回退

备份目录 **`/data/roombeacon/backups/background-82-20261010`**（0700），包含最终切换前 SQLite 一致性备份、私有配置、原应用／环境／Nginx、原记录与逐行摘要、官方 wheel 哈希和可审计发布／回退辅助脚本。新环境为 **`/data/roombeacon/venvs/background-3aaf5ee7dd91f0239d75675ee6dad8985f22687d`**；原环境 **`/data/roombeacon/venvs/3b0bf39cdfdb92e421882444615f8ab7bcb76c8c`** 保持。

回退先核对无活动监控／在途请求，保护暂停，恢复原 `current`、`venv-current` 和 Nginx，重启并核对原准确页面、完整采集及两台门牌回执后恢复发布前暂停值。**保留当前 SQLite／Redis，不整库覆盖、不清预约或设备身份。** 旧后端按数据库 MIME 可继续读取新增 JPEG／WebP；原 APK 保持。

私有备份中的辅助入口接受准确新／旧 SHA 和本次原图 SHA：

```bash
bash /data/roombeacon/backups/background-82-20261010/production-background-wrapper.sh rollback \
  3aaf5ee7dd91f0239d75675ee6dad8985f22687d \
  398f03d382db4e9bea6e5522ff5e1fb25483ed6b \
  /data/roombeacon/backups/background-82-20261010 \
  f2b9cafe50841e1e6f69192d1e32c66030283b2480c728b99c6abe9b7bf417ee
```

回退前置／健康检查不满足时保持保护状态并处置实际原因，不能绕过守卫或直接恢复整库。真实原图 HTTP 证据在备份的 `original-image-http.json`；设备与暂停终验以最终 `verify.json`／`resume.json` 为准。
