# 2026-09-20 源码备份说明

用户授权整理现有代码并推送 GitHub，以防本地源码丢失。仓库为 `git@github.com:arthurxbwang/roombeacon.git`，备份分支为 `codex/beijing-203-1080p`。本次是开发源码快照，不代表新的服务部署、正式APK发布或V5真实释放验收；不推送或合并main。

## 收录范围

- `android/`：WebView外壳0.2.3、维护与恢复、两套样机接线配置、Gradle Wrapper、原生测试和明确标注的模拟测试工具。
- `frontend/`：V1—V5页面、中控、官方签到、页面更新、灯控契约、1080P有效视口布局和动图前景修复，以及浏览器测试。
- `backend/`：独立采集与缓存、组织者补全、V5认证和保护流程、房间规则与受控释放代码，以及隔离测试。开关与服务器运行状态以专门运维记录为准。
- `scripts/`、`docs/`、`handbook/`、`plan/`：部署模板、设计决策、真实验证边界、开发运维与后续计划。

完整工作区被作为一个可恢复的开发快照保存。现有 `codex/v5-control-release` 分支及历史发布提交保持独立，不用本次快照自动替换运行服务。

## 不进入Git的内容

`.env`、真实App Secret、主控或维护密码、设备/操作凭证、官方签到resource_token、SSH私钥、签名密钥、`.local-tools/`、SDK/JDK、依赖目录、构建产物、截图及测试日志均不纳入提交。Gradle Wrapper JAR和已有品牌GIF是项目必需文件，保留在源码中。

因此克隆仓库可以恢复代码与文档，不能恢复私有运行配置或现有设备绑定。私有配置仍须使用管理员已有的安全备份恢复，不应将其加入Git作为普通源码备份。

## 恢复源码

```bash
git clone --branch codex/beijing-203-1080p git@github.com:arthurxbwang/roombeacon.git roombeacon
cd roombeacon
```

按 `handbook/development.md` 安装依赖，按 `android/README.md` 配置JDK17和SDK35。需要部署时另行指定准确提交SHA、目标环境和回退方案。

## 快照检查

在独立源码副本中完成检查，避免影响正在运行的样机页面服务：

- 后端：Ruff 0.16.7通过；pytest 136项通过，使用隔离Redis实例，上游由mock隔离。
- 前端：`npm ci`、生产构建通过；Playwright Chromium 67项通过。
- Android：JDK17、SDK35、缓存的Gradle 8.9离线执行 `testDebugUnitTest lintDebug assembleDebug` 通过。
- 源码凭证扫描未发现真实凭证或签到令牌；文件长度检查通过。提交前执行 `git diff --check`。

浏览器和原生自动测试不替代实机验收；203样机的分辨率、灯光和动图验证结果见 `docs/android-203-1080p-verification.md`。
