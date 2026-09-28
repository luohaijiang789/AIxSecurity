# AIxSecurity

面向 Java 代码仓的 AI 辅助白盒安全审计平台。

**只做：资产准备 → 安全问题发现 → 证据调查 → 独立复核 → 报告。**
不自动修改被审计代码。支持人工发起，以及明确启用的定时拉仓、准备和审计策略。

## 当前状态

项目已清理为重建基线：只保留主线设计与 Compose 配置，尚无新后端/前端业务实现。
旧代码、测试、运行记录、截图、历史文档和构建产物已移出工作区。没有继承旧版本的“已完成”结论。

## 主线架构

- Vue 前端与 FastAPI 后端分离。
- `celery-process`：代码准备、构建/建库协调、程序分析。
- `celery-worker`：Agent 调查、独立复核、报告和维护。
- Beat：周期触发；Redis：任务消息；MySQL：业务状态与审计结果。
- 源码、程序库、证据与报告文件：持久工件存储。
- CodeQL、Sourcebot 等工具通过适配器接入，不预先宣称可用。

资产准备完成即结束，不默认触发审计；人工选择或授权定时策略创建固定版本的审计计划。

## 阅读与实施

1. [方法论](docs/methodology.md)：必须保留的分析与证据原则。
2. [系统架构](docs/architecture.md)：八个业务模块与流程。
3. [部署与存储](docs/deployment-storage.md)：七容器、数据归属和定时协作。
4. [后端实施计划](docs/backend-implementation.md)：技术选型、接口/表/状态、B0—B8工单和验收。
5. [部署操作](deploy/README.md)：Compose挂载、配置与入口契约。

下一步只实施 **B0 工程与契约骨架**，通过验收再进入 B1。暂不铺开前端和所有扫描能力。

## 当前可执行的检查

```sh
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env.example -f deploy/compose.yaml --profile app config --quiet
```

上述仅验证部署配置；应用镜像、Python入口和Vue产物尚待实现。
本地 `.env` 仅保留凭据，不在此展示或提交；新部署按 deploy 文档配置独立 secrets。
