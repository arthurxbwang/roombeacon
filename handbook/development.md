# 开发与验证

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

新增测试重点为独立配置不加载 DB、精简飞书传输的正常/非法响应与敏感日志行为。APK/ESP 构建与实机测试目前不存在。
