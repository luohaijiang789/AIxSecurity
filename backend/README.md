# 后端目录骨架

后端采用模块化单体。API、两个 Celery Worker 和 Beat 以后共用同一份后端代码与镜像，只通过运行角色选择入口和依赖，不把业务模块拆成独立服务。

```text
backend/
├── modules/          M1—M8 业务模块及 Coverage
├── execution/        查询、工具网关、Agent Runtime、Runner 端口
├── platform/         任务、工件、身份、策略、模型网关和观测
├── entrypoints/      API、Celery、Beat、CLI 薄入口
├── composition/      按 api/process/audit/beat 角色装配依赖
├── migrations/       B1 开始建立数据库迁移
└── tests/            架构、契约、单元、集成和端到端测试
```

当前只建立目录和职责说明，没有 Python 包、依赖、入口、数据库表、任务或测试实现。实施顺序仍以 `docs/backend-implementation.md` 的 B0—B8 为准。

模块所有权和依赖规则见 [代码模块边界](../docs/module-boundaries.md)。
