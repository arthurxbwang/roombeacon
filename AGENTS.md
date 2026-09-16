# RoomBeacon 工程规范

本仓库是会议室门牌的唯一后续维护仓库：git@github.com:arthurxbwang/roombeacon.git。
Argus 门牌副本冻结；不要把本仓库改动回写 Argus，也不要默认部署旧服务器。

## 开始工作

先读 README.md、docs/handoff.md、docs/architecture.md、CHANGELOG.md。
涉及测试或部署时读 handbook/development.md 和 handbook/operations.md。
当前用户授权：迁移已有代码及设计资料。Android APK 和 ESP32 固件仅做规划，不实际编写，直到用户明确启动实施。

## 目录

- backend/：独立 FastAPI、飞书只读采集与 Redis 缓存、Python 测试。
- frontend/：Vue H5、中控与浏览器测试。
- scripts/：部署模板、维护脚本。
- docs/：架构、设计、交接、来源及历史归档；archive 不作为当前部署指令。
- handbook/：开发和运维操作。
- plan/：Android/ESP 研发与对照计划。
- 原生端新增源码目录前，在本文件登记职责并补 ADR。

## 变更约束

- 使用 codex/ 分支；GitHub 管理源码，不从开发机复制源码到服务器。
- 不推送 main；未获远程提交授权不 push。本次迁移先保存在本地。
- 不迁入 .env、SSH 私钥、真实 App Secret、主控密码、设备令牌、签到 resource_token。
- 保留 API 路径、ROOM_DISPLAY_* 配置、rooms:* Redis 键和 argus_room_* 浏览器键，改变时必须设计兼容迁移。
- 每个接口都必须验证设备或主控凭证。终端仅请求缓存，不直接访问飞书。
- 失联、过期、凭证撤销不能误报空闲或已签到；不以假数据冒充线上验证。
- 不静默吞异常，不将上游响应体、凭证写入日志。不禁用 TLS 校验。
- Python 单文件 <=500 行，Vue <=400 行；计时器和请求须在卸载时清理。
- 故障修复先写回归测试；认证、缓存和外部连接器变更必须有边界与失败用例。
- 更新 CHANGELOG.md 和受影响文档，文档用简体中文。

## 检查

- backend：Ruff 0.16.7、pytest；外部系统由 mock 隔离。
- frontend：npm ci、npm run build、npm test（Playwright Chromium）。
- 新增原生端后另登记 Android/ESP 构建验证；浏览器模拟不等于实机通过。
- 提交前 git diff --check；发布/部署另行明确准确 SHA、目标环境和回退方案。
