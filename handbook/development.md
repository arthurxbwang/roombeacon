# 开发与验证

## GitHub 接续

从[当前状态](../docs/current-state.md)和[下一阶段计划](../plan/next-phase.md)选择 Issue，自最新 main 创建 `codex/<issue>-<topic>` 分支；并行工作使用独立工作树。PR 记录行为、回归与边界，合并后更新 Issue／文档并清理分支。生产部署另行确定 SHA、目标、配置和回退；归档会话不代表未完成事项已验收。

> 新增改期自动核验回归与日历测试工具，外部调用仍由mock隔离；真实权限和日历测试未通过前不能据此宣称线上验收。见[测试说明](../docs/v5-reschedule-autoverify.md)。

> 版本: 0.1 | 作者: RoomBeacon Team | 更新日期: 2026-09-16

---

## 目录

- [1. 安装](#1-安装)
- [2. 检查](#2-检查)
- [3. 迁移测试边界](#3-迁移测试边界)

## 1. 安装

Python 3.13、Node 20。仓库根创建 .venv，执行 `.venv/bin/pip install -r backend/requirements-test.txt`；frontend 中执行 `npm ci`。运行真实服务需要本机 Redis 和私有环境配置；单元测试不需要真实飞书或 Redis。

## 2. 检查

V5 的原子状态测试需要本地 `redis-server`（可通过 `ROOMBEACON_TEST_REDIS_SERVER` 指定可执行文件）。测试自行启动仅监听临时 Unix socket 的 Redis，不连接配置中的已有实例；没有该程序时这些用例会跳过，V5 验收不得把跳过算作通过。前端测试应在隔离构建目录运行，避免覆盖现有样机使用的 dist；非默认端口需同步调整测试副本中的页面发布 URL。

```bash
make lint
make test
make build
cd frontend
npx playwright install chromium
npm test
```

Playwright 自动启动 127.0.0.1:4178 的构建预览，API 全部使用 fixture。依赖 mock 通过只证明代码行为，不能宣称服务器或硬件验收。

## 3. 迁移测试边界

原独立服务、采集器、日程、太阳时间、层级与二维码测试继续运行。设备撤销/轮换断言从平台测试抽出，验证 RoomBeacon 的真实设备认证函数。

Argus 平台管理页面和 webhook 需要用户 JWT/DB 等，不属于独立服务，本次不为运行旧平台测试而引入整套 Argus。它们完整保存在 docs/archive/platform/，没有在源仓库删除或跳过测试。

浏览器用例中的“管理员可预览并确认生成凭证”只针对已排除的平台页面，保存在完整历史 spec 文本中；剩余独立 H5/中控用例全部迁入。验证报告需明确此范围，不把归档用例算作通过。

新增测试重点为独立配置不加载 DB、精简飞书传输的正常/非法响应与敏感日志行为。

## 4. Android 外壳（2026-09-20）

Android 已启动实施，构建步骤见 [Android README](../android/README.md)。执行 `./gradlew testDebugUnitTest lintDebug assembleDebug`；单元测试覆盖来源限制、密码验证与退避边界。设备安装后验证 WebView、网络异常、页面升级和恢复，结果单独记录。使用模拟服务时必须保留测试标识；正式服务端、飞书及 72 小时/7 天长稳另行验收。ESP 构建仍未建立。

本地灯控额外验证三路 GPIO 白名单、写入失败/读回不一致时熄灯、网页状态契约和失效边界；实机另测正常应用权限、页面卡顿超时、后台熄灯及恢复。测试使用独立且明确标识的测试页，不在真实日程页伪造业务状态；结束后删除测试页、恢复真实绑定页面。见 [灯控记录](../docs/android-led-investigation.md)。
