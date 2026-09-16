# 独立迁移验证记录

> 版本: 0.1 | 作者: RoomBeacon Team | 更新日期: 2026-09-16

---

## 目录

- [1. 本轮验证](#1-本轮验证)
- [2. 未验证范围](#2-未验证范围)

## 1. 本轮验证

迁移基线 Argus c34a5614bdb5e86305e40deb0d5c36807ccd0b03。独立源码在隔离目录安装自身精简依赖进行检查，没有引用 Argus node_modules 或 Python 包路径。

| 检查 | 结果 |
|---|---|
| Python 3.13.5 新 venv 安装 requirements-test.txt | 成功 |
| Ruff 0.16.7 check backend | 通过 |
| pytest -q | 57 passed，4.34秒 |
| npm 精简 lockfile，npm ci --ignore-scripts | 成功 |
| vue-tsc -b && vite build | 通过，Vite 6.4.2，90 modules |
| Playwright Chromium，独立预览端口4178 | 37 passed，24.0秒 |
| 远程 git ls-remote | 成功，无 refs；新仓库尚无提交 |

保留独立中控、V1/V2/V3、跨日、历史缓存、认证失效、主题、二维码、不同屏幕比例用例。平台专属用例归档范围见 handbook/development.md，归档测试不计入通过数。

本次构建产物、node_modules、虚拟环境和测试缓存不纳入迁移源码。交接基于本会话和所核对代码，不是完整 Codex 会话数据库导出。

## 2. 未验证范围

未请求真实飞书，未读取或迁移运行服务器密钥；未登录 10.0.24.208、切换服务、配置 HTTPS、推送 GitHub 或发布版本。公司艺术码实物扫码、Tab S8、ESP、PoE 和长期稳定性均需后续实机验证。

迁移结果不能当作 APK/ESP 已实现、生产验收或独立新仓库已上线。
