# 历史维护任务与分支整理（2026-09-22）

用户确认按“固定标签 → GitHub 计划和待办 → 清理分支与工作树 → 归档旧任务”执行。此文保存交接与清理依据，最终执行回执写入 GitHub 总规划，不将清理旧任务视为业务验收完成。

## 保留与恢复

全部历史提交已进入 main。标签分别固定源码基线和已有生产前后端，见[当前状态](current-state.md)。私有本地备份放在 `.local-tools/archive-20260922/`（忽略入库、目录权限700），含已验证的 Git bundle、原分支头和临时工作树产物；SDK、主工作区和私有配置不在本次删除范围。

清理前全部分支独有未合并提交数为0，各工作树无未提交源码、无使用该目录的运行进程。移除的是分支引用与临时工作目录，原提交继续可由 main、标签及下表查找。需要恢复历史分支时从表中 SHA 创建新分支，不移动版本标签。

| 历史分支 | 清理前提交 |
|---|---|
| `codex/android-webview-shell` | `b62df0d08b01ddc045ca6c6c19385b22a81e05f0` |
| `codex/beijing-203-1080p` | `f0b2df76988309c3396af62aebcbd6bd6d109905` |
| `codex/checkin-release-plan` | `b62df0d08b01ddc045ca6c6c19385b22a81e05f0` |
| `codex/consolidate-20260922` | `15c1652dc8adf43adf1e7231689189c9d6349db1` |
| `codex/deploy-newserver` | `375727068ab08e14d10c581564a64a74f005b281` |
| `codex/import-roombeacon` | `b62df0d08b01ddc045ca6c6c19385b22a81e05f0` |
| `codex/production-20260922` | `a7b273b22aa28d918b32c553ecab4f723e9fbf65` |
| `codex/production-v5-checkin-20260922` | `dc9ca443ee4977e73f6c0a183ceb4fe36355d382` |
| `codex/v5-control-release` | `3b0bf39cdfdb92e421882444615f8ab7bcb76c8c` |

临时工作树范围仅为 `.local-tools/consolidate-20260922`、`.local-tools/production-checkin/release`、`.local-tools/v5/deployment` 和 `/tmp/roombeacon-production-release`。依赖和编译缓存可重建；测试截图、结果与 dist 在移除前另存私有归档。不递归清理整个 `.local-tools`。

## 任务移交

| 旧任务 | 任务 ID | 新入口 |
|---|---|---|
| 检查 10.0.68.146 网络 ADB | `01a0be39-7746-7180-b7a5-1534806407cb` | [生产签到与样机记录](production-v5-checkin-2026-09-22.md) |
| 分析签到二维码与会议室 UUID 匹配 | `01a0bdd0-5f7c-7682-b5ee-674b16d4b88d` | [飞书权限](feishu-permissions.md)、[V5 验收](v5-acceptance-checklist.md) |
| 阅读开发文档 | `01a0bdb3-6c31-75e0-bea2-fee900936179` | [传感器资料与勘误](hardware/dp72-rs485-handoff.md) |
| 评估门牌机设备配置 | `01a0ad62-446d-77f1-aa48-c897ac5b2bf8` | [型号灯控](android-device-profiles.md)、[历史 V4 样机](android-live-201-verification.md) |

上述四项资料完成移交后归档。当前整理任务暂保留作入口，因为可用工具没有 `create_thread`；[新任务开场说明](new-planning-task.md)已准备好，可在现有项目下新建“RoomBeacon 下一阶段规划”。不归档其他项目任务，不更改 GitHub 仓库的可写状态。

## 本轮验证

只修改文档和维护元数据：检查引用文件、Issue URL、标签与提交对应、敏感信息、原始资料校验、文档 diff，以及各分支完整合入 main。传感器五条引用报文 CRC 重新计算通过。没有重跑业务测试，也没有把此前250／84／11项基线测试称作此次新验收。
