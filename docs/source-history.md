# 来源提交与迁移范围

> 版本: 0.1 | 作者: RoomBeacon Team | 更新日期: 2026-09-16

---

## 目录

- [1. 来源提交](#1-来源提交)
- [2. 原样与调整](#2-原样与调整)

## 1. 来源提交

源库 https://github.com/arthurxbwang/argus 。以下是相关路径的提交列表，不是完整 Git 历史导入。

```text
63afbe2419beca768682fa3947d625567d0c992e feat(frontend): add Feishu meeting room display on port 1000
a5e697014a53462eb2d5e8ae0207d1f1f4c53ad3 feat(deploy): isolate meeting room display on standalone HTTP host
438adf998a6e87f46853d12c02d4bca021dd180d feat(backend): add paginated room tables and location filters
823b0cc63ecc505957ccb9c33ea4cb34338cedbb feat(frontend): add room control preview and rolling 12 hour timeline
b68e44ffb928cc72b1b96028301c547bc603a5c0 style(frontend): enlarge primary meeting display and widen left column
4910a2324a67a160e6b7c26bed0bc07fffabeb47 style(frontend): center primary room information with oversized status
2313ecca22b547800fa9895a62745e7208a94c44 feat(frontend): add city daylight themes and control preview toggle
b5a355006ef1c26d58692594ddbc2c7e3b0ead79 feat(frontend): redesign room signage hierarchy and schedule states
3e814e9b15908e6104a255452fe6b49e85950536 feat(backend): allow a second independent room control credential
47e2be44a883618d9063ce846853b831d30ad22b fix(backend): allow short secondary room control passwords
d39cc92e8a26fb0428bcebeb89163f96118ac6aa feat(frontend): add switchable responsive room signage v2
884368f2a85724de149388790a8fe3c476a300c3 feat(backend): centralize room refresh and serve historical cache
6ef80da05fbf9ddd07b477d5950e671ec09bf2b4 feat(frontend): add V3 official room check-in QR display
c04ef0b8e51563edac965a86efb3668220e933f3 style(frontend): balance V3 check-in with company branding
de9b77d85a3f55dd7c59036b3cb0cbbf885f76f3 feat(frontend): refine V3 status frame and upcoming meetings
c34a5614bdb5e86305e40deb0d5c36807ccd0b03 style(frontend): enlarge V3 status and remove duplicate indicator
```

## 2. 原样与调整

docs/migration-manifest.json 记录来源文件哈希与目标路径，适用于迁入时追溯，不保证调整后的目标哈希与源一致。

UI 样式和品牌资产保留；仅去掉独立入口不能使用的 Argus 平台预览跳转与客户端管理方法。独立 RoomControl 预览维持原样。前端依赖去掉 Pinia 和 Argus 用户登录链。

Python 服务、模型、核心凭证/缓存和二维码生成保留。配置收敛为门牌需要的字段，FeishuClient 提取只读查询所需方法并移除上游敏感日志。测试配置不再依赖 DB/SECRET_KEY；独立导入测试调整为验证这些字段不属于运行配置。

平台专属后端路由、事件测试和前端管理页以 .txt 保存到 docs/archive/platform，避免误启动。通用设备凭证测试移植到独立测试，不删除源库用例。

不复制 .git、.env、密钥、node_modules、dist、虚拟环境、真实会议快照或完整会话数据库。品牌 GIF 作为现有 UI 依赖迁入，不代表授权公开分发公司素材。
