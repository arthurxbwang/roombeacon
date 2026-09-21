# RoomBeacon · 会议灯塔

面向飞书会议室的独立门牌系统。服务器集中采集并缓存日程，终端显示会议状态、时间、组织者、后续会议与官方签到二维码。

**当前Control：默认V4，保留V1–V3；V5仅IT灯塔-Test试点。** 后端c665859、静态85a3cf2，已实测非重复预约签到、自动释放、提前结束与释放后刷新；其他342间保持官方方案。重复日程与多日长稳仍未验收，新增预约仍需逐场登记非重复。见[四场实测](docs/v5-four-bookings-verification.md)及[部署回退](docs/v5-control-deployment.md)。软件仓库版本暂为0.1.0，页面版本不表示正式发布版本。

## 快速开始

需 Python 3.13、Node.js 20、独立 Redis。不要连接 Argus 生产 Redis。

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-test.txt
cp .env.example .env
chmod 600 .env
# 手动填写飞书应用及中控凭证，不要提交 .env
export ROOMBEACON_ENV_FILE="$PWD/.env"
cd backend
../.venv/bin/uvicorn app.room_display_main:app --host 127.0.0.1 --port 8088
```

另开终端：

```bash
cd frontend
npm ci
npm run dev
```

打开 Vite 给出的本地地址 `/control`，输入已配置主控凭证。设备端 `/?version=v3`；未指定时仍默认 V2。首次采集完成前会提示等待。

## 文档

- [项目交接：先读](docs/handoff.md)
- [系统架构与 API](docs/architecture.md)
- [界面与历史设计决策](docs/design.md)
- [开发与检查](handbook/development.md)
- [运行环境与部署迁移边界](handbook/operations.md)
- [Android / ESP 对照规划](plan/meeting-room-terminal-comparison.md)
- [源代码出处清单](docs/migration-manifest.json)
- [迁移验证](docs/migration-verification.md)

## 来源和维护边界

从 Argus `codex/meeting-room-standalone` 的 `c34a5614bdb5e86305e40deb0d5c36807ccd0b03` 抽取；没有导入整个 Argus Git 历史及无关平台功能。后续门牌修改只在 RoomBeacon 维护。

已有服务没有随仓库迁移而切换。历史目录、服务名和浏览器存储键保留兼容；详见交接文档。
公司提供的 ThunderSoft 品牌素材仅用于本项目，未新增开源许可证或第三方再授权承诺。

## V4 / V5 测试版本

Control 的门牌版本选择支持 V1–V5。V4 保留官方签到；V5 使用独立确认与保护协议，飞书写入默认关闭。启用和隔离验证见 [V5 说明](docs/v5-usage-verification.md)，部署回退见 [Control 更新](docs/v5-control-deployment.md)。

2026-09-20：现有 Control 已部署代码 `4ba9d38`，IT灯塔-Test 为观察模式，飞书写入保持关闭；运行验收与备份信息见上述部署记录。
