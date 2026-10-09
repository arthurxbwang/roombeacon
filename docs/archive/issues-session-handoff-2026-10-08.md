# “分析未解决 GitHub Issues”任务关闭交接

归档日期：2026-10-08。任务范围：读取全部 Issue、对照最新 V6 重构及生产代码、完成已批准的 PR 合并和待办校准、检查源码与构建产物一致性。以下保存决策、执行结果和接续入口，不是逐字聊天导出。原任务在应用中保留；私有配置、凭证和原始人员资料不进入仓库。

## 已完成并保存到 GitHub

1. 2026-09-24 首轮读取全部 14 个 Issue 正文和评论，区分实际功能缺口、真实验收缺口、已上线待合并以及已接受限制。后来新增 #29，逐项对照后明确自动关闭网络 ADB 与无 ADB 升级维护的分工。
2. 用户批准优先完成三项源码收尾及待办校准。PR [#24](https://github.com/arthurxbwang/roombeacon/pull/24) → [#26](https://github.com/arthurxbwang/roombeacon/pull/26) → [#28](https://github.com/arthurxbwang/roombeacon/pull/28) 已按依赖顺序合入 main，保留 merge commit 历史；#26 移出草稿，后两项改为 main 基线。准确提交见[合并回执](../issue-reconciliation-2026-09-24.md)。
3. Issue #23/#25/#27 按 completed 关闭，原交付内容保留。#10 收敛为设备接入、PoE/有线与长稳验收；#16 收敛为无 ADB H5/APK 更新及现场恢复；#2/#3 更新启用条件和新版操作流程，#6 更新总规划。联系人 #1 保持 not_planned，不重复实施或重新排查。
4. 维护文档经 [PR #30](https://github.com/arthurxbwang/roombeacon/pull/30) 合入，main 为 `78207f323915874707656506850fe9bd3003e656`；162 个本地链接、差异和新增敏感值检查通过。四个已合并短期分支已清理，历史提交在 main 中保留。#27 的旧分支链接已固定到提交，避免清理后失效。
5. 本任务没有部署应用、改写生产配置、安装 APK、修改飞书预约或清空保护记录。合并和文档整理不等于授权全部后续研发或生产操作。

联系人保留“联系人优先 → 可确认的组织者兜底 → 信息不可见”规则，接受现有限制，采集未实现，见[分析归档](issue-1-meeting-contact-2026-09-22.md)。#8 SDK 资料整理、#17 飞书登录及首位管理员、#20 退出按钮均已完成关闭；不因本次任务归档重新列为待办。

## 补存：最后一次一致性核查（2026-09-24）

此部分原先只在任务对话和临时文件中，2026-10-08 按原工具输出及结论补存。不是今天重跑的生产检查，不能作为当前生产状态。原临时报告和临时构建目录已不在原路径；不虚构完整逐文件哈希清单。

| 检查 | 当时结果与边界 |
|---|---|
| 本地 / GitHub main | 均为 `78207f3`，本任务结束时工作区干净 |
| main / 生产应用 | 生产为 `3359332b5b84343318693f7266d7966d3a950619`，相对 main 只有文档差异；#24/#26/#28 各 head 及生产提交均在 main 祖先历史中 |
| 服务器文件 | 核对 backend、frontend、android、scripts 中 192 个受 Git 管理的非 Markdown 文件；191 个逐字节一致，无缺失文件，无额外后端/前端源码 |
| 唯一文件差异 | `android/gradlew.bat`：生产 CRLF、本地 LF；统一换行后 SHA-256 均为 `2209f919a22528af59a2af2ad97e8d056cca18e39f7d87aa3fd549a73b180150`。该文件是 Windows 构建入口，不影响生产 Linux 业务运行 |
| 实际运行 | 服务进程工作目录及前端发布目录指向 `3359332`；真实 `/`、`/control`、`/room-display.html` 均返回 200，与发布 HTML 字节一致 |
| HTTP 路由边界 | `/index.html` 返回 404，符合当时 Nginx 只公开固定入口的配置；不据此认定页面发布失败 |
| 静态资源 | 实际请求的 JS/CSS/GIF 与生产磁盘内容一致；用于入口的资源为 `main-room-display-BQW-wO_P.js` 和 `main-room-display-Cb3egZPe.css` |
| 隔离重建 | 从当时 main 导出 frontend，复用既有 node_modules，显式设置 `ROOMBEACON_WEB_RELEASE=3359332b5b84343318693f7266d7966d3a950619`；类型检查和 Vite 构建通过，5 个新产物逐字节匹配生产 |
| 配置迁移 | 迁移标记存在，硬件版本和软件版本均无悬空关联；设备 active、APK 0.7.0-debug、协议 3、回执 7/7、无错误；房间策略 applied |
| 定向回归 | 配置目录、配置交付、SQLite 初始化、V6 模板和型号模板的 44 项测试通过；外部系统由 mock 隔离，不操作生产 |
| 业务范围 | 当时日历映射为 0，写入白名单 1 间；后台重构没有消除真实预约联调、长稳和无 ADB 更新缺口 |

5 个重建产物为 `index.html`、`room-display.html`、上述 JS/CSS，以及 `room-checkin-brand-Cj7hKss9.gif`。历史测试命令：

```bash
python -m pytest -q tests/test_configuration_catalog.py \
  tests/test_configuration_delivery.py \
  tests/test_management_store_initialization.py \
  tests/test_v6_templates.py tests/test_device_templates.py
```

受限执行环境首次运行无进展，停止后在允许本机测试通信的环境重跑，44 项通过；没有把中断的一轮当作通过，也没有重复运行整套业务测试。

当时本地 `frontend/dist` 是旧构建，直接预览会看到旧界面。Git 合并不刷新生成文件；隔离重建与生产一致已排除合并造成的业务混版。此发现是历史生成产物残留，不是当前版本永久缺陷，不另开失效待办。今后本地预览前构建，发布从固定 Git SHA 生成，不复制旧 dist。

## 关闭前当前状态核对（2026-10-08）

归档开始时本地和 GitHub main 均为 `858038c3f3632e2ad4d118b9294afa42006f796e`，已经包含后续 V7、正式发布和首装工作。因此不能继续把本任务 2026-09-24 的 `3359332`、7/7、日历映射 0 当作现状。

根据当前仓库最新发布记录和 Issue #2 的最新评论，10 月 8 日已接入一个实际可读来源日历；真实释放/改期及其他来源仍待验收。首装生产记录已推进到 PR #50，正式 APK 安装、短码关联及旧身份变化见[当前状态](../current-state.md)、[首装操作记录](../installation-delivery.md)和[就绪核查](../production-readiness-2026-10-08.md)。本次归档未重新 SSH 检查这些后续发布。

GitHub 快照共 21 个 Issue，其中开放 11 个：#2/#3/#4/#5/#6/#10/#16/#29/#41/#43/#52。最新事实以正文、最新评论和最新发布记录共同判断；总规划正文中保留的 9 月版本是历史，后续不要覆盖更新的事实。关闭本任务不关闭尚未完成的 Issue。

| 接续入口 | 当前需跟踪的工作 |
|---|---|
| [#2](https://github.com/arthurxbwang/roombeacon/issues/2) / [#3](https://github.com/arthurxbwang/roombeacon/issues/3) | 来源日历真实预约联调、改期单实例释放、周/月重复、故障和业务长稳 |
| [#4](https://github.com/arthurxbwang/roombeacon/issues/4) | 504 脱敏诊断及根因闭环 |
| [#5](https://github.com/arthurxbwang/roombeacon/issues/5) | RS485 传感器只读接入 |
| [#10](https://github.com/arthurxbwang/roombeacon/issues/10) / [#16](https://github.com/arthurxbwang/roombeacon/issues/16) / [#29](https://github.com/arthurxbwang/roombeacon/issues/29) | 设备交付、PoE/网络/长稳、无 ADB 更新恢复、自动关闭 ADB 与现场维护 |
| [#41](https://github.com/arthurxbwang/roombeacon/issues/41) / [PR #42](https://github.com/arthurxbwang/roombeacon/pull/42) | 其他任务的脱敏阶段汇报已提交到远端分支，归档检查时 PR 尚开放，本任务不合并 |
| [#43](https://github.com/arthurxbwang/roombeacon/issues/43) | 首装与批量交付，单台首装通过不代表全部交付验收通过 |
| [#52](https://github.com/arthurxbwang/roombeacon/issues/52) | 其他任务正在处理灯控恢复回执与独立页面运行健康上报，本任务不接管或中断 |
| [#6](https://github.com/arthurxbwang/roombeacon/issues/6) | 总规划与以上各项交叉入口 |

## 保存范围与接续方式

本任务没有未提交业务源码。关闭检查时共享开发目录有其他任务的分支及未跟踪输出；本归档使用独立工作树，只提交本任务文档。阶段汇报和截图等原始输出由 #41/#43 等任务负责，原始人员资料和凭证不得因“全部保存”而上传公开仓库。私有环境目录不读取、不打包，也不视为漏提交的业务源码。

下一任务从最新 main 读取 [当前状态](../current-state.md)、[下一阶段计划](../../plan/next-phase.md)和相关 Issue 的最新评论，再按需阅读本归档、[原合并回执](../issue-reconciliation-2026-09-24.md)及 [ADR 0005](../adr/0005-versioned-configuration.md)。无需重读本任务全部聊天即可恢复决策与验证边界。
