# AIxSecurity 主线设计文档

这里只保留当前设计基线，不存历史执行流水。建议按下面顺序阅读。

| 顺序 | 文档 | 核心问题 |
|---|---|---|
| 1 | [vision.md](vision.md) | AIxSecurity 到底是什么；SAIL / Chimera / AI4PA / Sourcebot 如何融合 |
| 2 | [architecture.md](architecture.md) | 四个架构平面、M1-M8、Workspace、Agent、验证和部署边界 |
| 3 | [domain-model.md](domain-model.md) | Repository / Snapshot / Scan / Case / Evidence / Verdict / Finding 如何区分 |
| 4 | [methodology.md](methodology.md) | Asset-First、Source-Driven、多方法调查和证据原则 |
| 5 | [sourcebot-integration.md](sourcebot-integration.md) | 前置索引、快速检索、固定版本一致性与 Tool Gateway |
| 6 | [agent-runtime.md](agent-runtime.md) | Claude Code / Codex、Profile / Skill / Goal、AgentTask 与工具调用 |
| 7 | [verification.md](verification.md) | Claim-level 验证、独立 Agent、互辩、Runtime/Black-box 与 Assurance |
| 8 | [coverage-model.md](coverage-model.md) | 如何严谨回答“测了多少、测没测完” |
| 9 | [platform-support.md](platform-support.md) | Knowledge/RAG、Policy、Memory、Model Gateway、Tool Registry、Observability |
| 10 | [security-boundaries.md](security-boundaries.md) | Prompt Injection、Runner、模型数据外发、Artifact/多租户安全边界 |
| 11 | [deployment-storage.md](deployment-storage.md) | Core 七容器、三类 Runner、数据/消息/工件和定时机制 |
| 12 | [backend-implementation.md](backend-implementation.md) | 技术选型、接口/表/状态、B0-B8 工单与验收 |

[部署操作说明](../deploy/README.md)负责当前 Compose 配置。

## 文档职责边界

- **vision** 只定义目标与不变原则，不写具体 ORM/API。
- **architecture** 定义模块和边界，不把某个工具当成系统中心。
- **domain-model** 是对象命名和不变量的唯一依据。
- **methodology** 定义白盒审计方法与证据责任。
- **tool / agent / verification / coverage** 文档定义专项子系统。
- **platform-support / security-boundaries** 定义横向支撑与平台自身安全边界。
- **backend-implementation** 才定义实现顺序和验收。
- **deployment-storage** 定义运行与数据边界。

如果文档冲突，先修正文档后再编码；不要让开发者自行猜测哪一份为准。

## 当前实施状态

目前仍处于设计/重建基线阶段，业务代码尚未开始。实现按 B0 → B8 顺序推进，只有通过真实依赖、失败路径和版本一致性验收才能更新状态。

设计中出现 Sourcebot、CodeQL、Claude Code、Codex 等名称，表示目标适配器或候选实现；除非工单验收明确通过，不等于已经完成集成。
