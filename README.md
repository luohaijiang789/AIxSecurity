# AIxSecurity

面向企业 Java / 微服务代码仓的 **AI 辅助白盒安全审计平台**。

AIxSecurity 不是“把整个仓库丢给大模型找漏洞”。它先把固定版本代码构建成可复用的 **Security Analysis Workspace**，再由人工选择 Scan Plan，由 Claude Code / Codex 等 Agent 在 Profile、Skill、Goal、Scope、Budget 和 Tool Policy 约束下进行调查，最后通过独立 Agent、双 Agent 互辩、运行时或授权黑盒验证提高漏洞结论可信度。

## 核心链路

```text
Repository / Commit
        ↓
资产与程序能力准备
        ↓
Security Analysis Workspace
  ├─ 固定源码 / Build Context
  ├─ Sourcebot 快速代码检索
  ├─ Entry / Source / Sink / Guard
  ├─ Program / Security Relations
  ├─ CodeQL / Data-flow Capability
  └─ Capability / Quality / Gap
        ↓
READY
        ↓
人工选择 Scan Plan / Profile / Scope / Budget
        ↓
Multi-method Analysis + Agent Runtime
        ↓
Security Case
        ↓
Claims + Evidence + Counter Evidence + Gap
        ↓
Trusted Verification
        ↓
Verdict + Assurance
        ↓
Finding / Coverage / Report
```

**READY 后默认停止，不自动开始审计。** 审计必须由人工发起，或由用户明确授权的版本化周期策略触发。

## 设计来源

当前方案收敛此前几条技术主线：

- **SAIL**：代码拉取、构建、CodeQL、资产提取、异步任务与工程化落库。
- **AI4PA**：All Code is a Graph；程序分析负责确定性事实，LLM 负责安全与业务语义。
- **Chimera**：人选扫描模式、多 Agent 分工、反证与多阶段验证。
- **Sourcebot**：前置多仓索引、快速搜索、Definition / Reference、commit/diff 上下文。
- **Coding Agent**：Claude Code / Codex 等作为可替换 Agent Runtime，不成为领域模型本身。

## 八个逻辑模块

M1 资产管理 → M2 代码处理 → M3 安全资产 → M4 扫描计划 → M5 编排与查询 → M6 Case 调查 → M7 可信验证 → M8 报告与 Coverage。

后端采用模块化单体，不按 M1-M8 拆成八个微服务。

## 关键原则

- Asset First；不让 Agent 从零自由理解整仓。
- 扫描计划由人选择；Agent 不自行扩大扫描范围。
- Source-Driven，但不 Source-only。
- Sourcebot 搜索不是程序路径证明；CodeQL 路径也不是最终安全结论。
- Profile、Skill、Goal、Plan 分层。
- Candidate 先进入 Case；漏洞成立条件拆成 Claims；Finding 必须经过有效 Verdict。
- 支持证据和反证同等重要。
- Coverage 必须绑定明确分母，unsupported / failed / unknown 不能被隐藏。
- 固定 commit、不可变 Snapshot、EvidenceDigest 和版本绑定贯穿整条责任链。
- Build Runner、Agent Runner、Validation Runner 权限隔离。
- Repository Content 永远是不可信数据，不能通过注释/README 改变 Policy、Scope 或 Tool 权限。
- Security Knowledge/RAG 只提供上下文，不替代代码与程序 Evidence；模型调用经 Model Gateway / DataPolicy。
- 不自动修改被审计代码；动态/黑盒验证默认关闭并要求明确授权。

## 技术与部署基线

- Vue + FastAPI。
- Celery：准备/程序分析与 Agent/验证任务。
- Redis：消息 broker，不是审计事实源。
- MySQL：业务状态、Case、Evidence 索引、Verdict、Coverage、报告索引。
- Artifact Store：固定源码、CodeQL DB、工具输出、验证工件与报告。
- Sourcebot：首选 Code Intelligence / Fast Search Layer。
- CodeQL / Semgrep / 其他程序分析工具：通过适配器接入。
- Claude Code / Codex：通过 AgentRuntimePort 接入。

Core 当前按七个常驻容器设计；Sourcebot、Runner、对象存储、监控等属于 Tool/Execution Services，不计入 Core 七容器。

## 文档入口

1. [愿景与设计来源](docs/foundation/vision.md)
2. [完整系统架构](docs/architecture/architecture.md)
3. [核心领域模型](docs/foundation/domain-model.md)
4. [白盒审计方法论](docs/foundation/methodology.md)
5. [Sourcebot 集成](docs/subsystems/sourcebot-integration.md)
6. [Agent Runtime / Skill / Goal](docs/subsystems/agent-runtime.md)
7. [可信验证体系](docs/subsystems/verification.md)
8. [Coverage 模型](docs/subsystems/coverage-model.md)
9. [平台支撑能力](docs/subsystems/platform-support.md)
10. [安全与信任边界](docs/architecture/security-boundaries.md)
11. [部署与存储](docs/delivery/deployment-storage.md)
12. [后端实施计划 B0-B8](docs/delivery/backend-implementation.md)
13. [代码模块与依赖边界](docs/architecture/module-boundaries.md)

目录入口：[后端骨架](backend/README.md)、[前端骨架](frontend/README.md)、[契约目录](contracts/README.md)。

## 当前状态

项目目前仍是重建设计基线：已经建立后端、前端和契约目录骨架及职责说明，尚无新的业务实现。Compose 配置存在，但“配置可解析”不代表完整系统已可运行。

下一步仍按 [B0-B8 后端实施计划](docs/delivery/backend-implementation.md)逐阶段落地。第一阶段目标不是一次实现所有扫描器，而是先跑通 **固定代码版本 → READY Workspace → ScanSpec → 单专项 Case → Claims/Evidence → Static Program Review + Independent Agent → Assurance/Coverage/Report** 的真实闭环。
