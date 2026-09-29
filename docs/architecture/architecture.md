# AIxSecurity 系统架构

状态：重建设计，业务代码待实现。本文定义主架构、模块边界和运行关系；方法论见 [methodology.md](../foundation/methodology.md)，领域对象见 [domain-model.md](../foundation/domain-model.md)，实施契约见 [backend-implementation.md](../delivery/backend-implementation.md)。

## 1. 架构目标

AIxSecurity 面向企业 Java / 微服务代码仓，目标不是构建一个“LLM 扫描器”，而是构建：

> **可复用的安全分析工作空间 + 人工可控扫描计划 + 多方法 Agent 调查 + 多级可信验证 + 可量化 Coverage。**

核心闭环：

```text
Repository / Fixed Commit
        ↓
Preparation
        ↓
Security Analysis Workspace
        ↓
Human-selected Scan Plan
        ↓
Multi-method Analysis
        ↓
Security Case
        ↓
Agent Investigation
        ↓
Trusted Verification
        ↓
Finding / Report / Coverage
```

READY 表示“资产可以被扫描”，不是“自动开始扫描”。未创建 ScanSpec 前不调用安全调查 Agent。

## 2. 四个架构平面

为了避免模块职责混乱，系统逻辑上分成四个平面。

### 2.1 Asset & Program Plane

负责把源码准备成可复用分析能力：
- 固定 RepoRevision；
- 源码镜像与文件摘要；
- No-Build 解析；
- Sourcebot 快速索引与代码导航；
- 隔离构建；
- CodeQL / 程序分析数据库；
- Entry / Source / Sink / Guard / Data Asset；
- 程序关系与安全关系；
- Capability / Quality / Gap；
- AssetSnapshot / RepositorySetSnapshot。

它回答：

> **“这份代码里有什么，以及我们现在能对它做什么分析？”**

### 2.2 Control Plane

负责人工决策和边界冻结：
- ScanIntent；
- ScanPlan；
- VulnerabilityProfile；
- Scope；
- Budget；
- VerificationPolicy；
- ScanSpec。

它回答：

> **“这一次允许分析什么、用什么方法、做到什么深度？”**

### 2.3 Investigation Plane

负责真正的安全调查：
- Orchestrator；
- Query Service；
- Tool Gateway；
- Agent Runtime；
- Skill / Goal；
- Candidate / Security Case；
- Evidence / Counter Evidence / Gap。

它回答：

> **“这个候选问题到底成立不成立，需要什么证据？”**

### 2.4 Trust & Reporting Plane

负责可信度和结果输出：
- Claim-level Verification；
- Independent Verification；
- 双 Agent 互辩；
- Runtime / Sandbox Validation；
- Authorized Black-box Validation；
- Assurance State；
- Verdict；
- Finding；
- Coverage；
- Report。

它回答：

> **“我们凭什么相信这个结论，以及还有什么没分析完？”**

### 2.5 横向 Platform Support

横跨四个平面的支撑能力：
- Security Knowledge / RAG；
- Policy Engine；
- Working Memory / Case Memory；
- Model Gateway；
- Tool Registry；
- Observability / Evaluation；
- Audit / Identity / Authorization。

这些能力不成为第五套业务流程，也不替代 M1-M8。它们负责统一规则、知识和可观测性，避免每个模块各自实现一套。

详细见 [platform-support.md](../subsystems/platform-support.md)。

## 3. 八个逻辑模块

八个业务模块保留，但它们是逻辑边界，不等于八个微服务。

| 模块 | 核心职责 | 主要输出 |
|---|---|---|
| M1 资产管理 | Project、Repository、服务/模块映射、固定 commit | Repository、RepoRevision、准备请求 |
| M2 代码处理 | 源码镜像、Sourcebot 索引、No-Build、隔离构建、CodeQL/工具准备 | 文件/搜索/程序分析工件、构建诊断 |
| M3 安全资产 | 归一化 Entry/Source/Sink/Guard/Data Asset/Relations，质量与能力门禁 | AssetSnapshot、RepositorySetSnapshot、Capability、Gap |
| M4 扫描计划 | 人工或授权周期策略选择 READY 版本、Profile、方法、范围、预算、验证策略 | 不可变 ScanSpec、ScanRun |
| M5 编排与查询 | 将 ScanSpec 编译为任务/DAG；统一 Query Service、Tool Gateway、Workspace、Agent Runtime 调度 | AnalysisTask、ToolResult、Candidate、Coverage 轨迹 |
| M6 Case 调查 | Profile + Skill + Goal 驱动 Agent 调查，将成立条件拆为 Claim，主动补证和找反证 | CaseRevision、Claim、Evidence、Counter Evidence、Gap、Trace |
| M7 可信验证 | 基于 Claim 进行静态复核、独立 Agent、双 Agent 互辩、可选运行时/黑盒验证 | VerificationRun、Claim Review、AssuranceState、Verdict |
| M8 报告与覆盖 | 将有效裁决、证据、Coverage 和限制组织成机器/人可读输出 | Finding、CoverageSnapshot、JSON/Markdown、报告索引 |

公共任务、定时调度、身份、审计、工件和观测属于横切基础设施，不另造另一套业务规则。

## 4. 主流程

### 4.1 自动准备

```text
登记仓库
 → 固定 commit
 → 源码镜像
 → Sourcebot 索引 / 探测
 → No-Build 基础解析
 → 隔离构建 / CodeQL / 增强提取
 → 安全资产归一化
 → Capability / Quality / Gap
 → 发布 READY AssetSnapshot
 → 结束
```

Sourcebot、No-Build 和部分依赖分析可以并行。构建失败、索引版本不一致或必要能力缺失必须显式反映在 Snapshot 状态中，不能静默降级。

### 4.2 人工审计

```text
选择 READY Snapshot
 → 选择 ScanPlan / Profile / Scope / Budget / VerificationPolicy
 → 服务端 Preview / Capability 校验
 → 固化 ScanSpec
 → 多方法产生 Candidate
 → 建立 Security Case
 → Agent Investigation
 → Trusted Verification
 → Finding / Coverage / Report
```

Agent 可以调整“下一步如何调查”，但不能改变 ScanSpec 授权边界。

### 4.3 周期自动化

周期策略只复用 M1/M4：
- 定时更新代码；
- 定时准备资产；
- 显式授权的定时审计。

每次触发都生成固定版本的业务实例。运行过程中不再读取 latest。

## 5. Security Analysis Workspace

AssetSnapshot 是 Workspace 的正式发布版本。Workspace 可以提供：

```text
Fixed Source
File Manifest / Hash
Build Context
Dependencies / SBOM Facts
Framework Facts
Sourcebot Search Index
Symbols / Definitions / References
Entry / Source / Sink / Guard
API / RPC / MQ / Job / Data Assets
Program Relations
Security Relations
CodeQL DB
Call / Data-flow Query Capability
Config / Deployment Context
Tool Versions
Capability Matrix
Quality / Gap
```

Workspace 不是“预先把所有代码塞进模型”。Agent 只通过 Tool Gateway 按 Goal 获取有限上下文。

## 6. 程序图、安全图与 Global Graph

“所有代码都是图”在 AIxSecurity 中是逻辑抽象，不要求首版把所有事实复制进专用图数据库。

### Program Facts

包括：
- AST / symbol；
- Call Graph；
- CFG；
- Def-Use；
- Data Flow；
- type / inheritance；
- dependency。

这些事实主要由编译器、Tree-sitter、CodeQL 或其他程序分析工具提供。

### Security Semantic Relations

包括：
- EXPOSES；
- FLOWS_TO；
- GUARDED_BY；
- READS / WRITES；
- HTTP_CALL；
- RPC_CALL；
- PUBLISHES / CONSUMES；
- AUTHENTICATES / AUTHORIZES；
- BELONGS_TO_SERVICE。

M3 只归一化安全分析需要的关系，不复制 CodeQL 的全部内部程序图。

### Global Security Graph

逻辑上：

```text
Program Facts
    +
Security Assets / Relations
    +
Repository / Service Relations
    =
Global Security Graph
```

跨仓路径必须逐级证明：
代码搜索线索 → 关系候选 → 传播路径 → 经验证的安全问题。

## 7. Query Service 与 Tool Gateway

M5 对 Agent 暴露统一能力，而不是让 Agent 直接理解每种工具内部协议：

```text
Code Intelligence
  search_code / read_file / list_tree
  find_definitions / find_references / get_diff

Program Analysis
  find_callers / find_callees
  trace_flow / query_dataflow / query_codeql

Security Assets
  lookup_asset / find_entries / find_sources
  find_sinks / find_guards / query_relations

Context
  read_config / lookup_dependency / framework_facts
```

职责边界：

```text
Sourcebot            -> 快速找到“代码在哪里”
CodeQL / Program PA  -> 证明“程序怎么走”
Security Asset Graph -> 描述“安全语义关系是什么”
Agent + Skill        -> 判断“这些事实意味着什么”
Verifier             -> 判断“证据是否足够成为结论”
```

详细见 [Sourcebot 集成](../subsystems/sourcebot-integration.md) 与 [Agent Runtime](../subsystems/agent-runtime.md)。

## 8. Agent Runtime、Profile、Skill 与 Goal

四个概念必须分开：

```text
Profile = 这个漏洞专业上如何定义与验证
Skill   = Agent 可复用的专家调查方法
Goal    = 当前 Case 具体要回答的问题
Plan    = 本次允许怎么做、做到什么程度
```

Claude Code、Codex 等通过 AgentRuntimePort 接入。Agent 的临时 scratch/notes 不属于正式证据；正式结果必须通过结构化写回进入 Case/Evidence。

## 9. Security Case 与 Evidence

候选不能直接成为 Finding。

```text
Candidate / Trigger
      ↓
Security Case
      ↓
Hypothesis
      ↓
Claim[]
  ├─ Supporting Evidence
  ├─ Counter Evidence
  ├─ Assumptions
  └─ Gap
      ↓
CaseRevision + EvidenceDigest
      ↓
Verification
```

Evidence 必须尽可能绑定：
repo、commit、snapshot、location、tool、tool version、query、artifact digest、precision。

Case 证据变化后创建新的 CaseRevision；旧 Verdict 不再对新 EvidenceDigest 生效。

## 10. 多维可信验证

M7 使用 VerificationPolicy，而不是一刀切“第二个 Agent 再看一次”，也不把验证方法强行排成单调的 E0-E5 强度。

可组合的 Verification Method：
- STATIC_PROGRAM_REVIEW；
- INDEPENDENT_AGENT；
- ADVERSARIAL_DEBATE；
- RUNTIME_SANDBOX；
- AUTHORIZED_BLACKBOX；
- HUMAN_REVIEW。

最终另外记录 Assurance State：
- candidate；
- reviewed；
- corroborated；
- reproduced。

双 Agent 互辩中可以设置：
- Prover：尝试证明必需 Claims 成立；
- Skeptic：主动找不可达、Guard、不可控参数、环境前提等反证；
- Judge/Verifier：依据原始 Evidence、Claim 状态和 Profile Verification Rules 裁决。

“两个 Agent 都同意”不能代替证据；黑盒在某环境复现，也不能自动外推所有环境。

运行时和黑盒验证默认关闭，必须有显式授权、目标白名单、预算和隔离环境。详细见 [verification.md](../subsystems/verification.md)。

## 11. 三类隔离执行环境

这是当前架构必须明确的安全边界。

### Build Runner

用于：
- Maven / Gradle；
- CodeQL 建库；
- 项目相关提取。

目标仓脚本属于不可信输入。Build Runner：
- 无 MySQL/Redis/模型长期凭据；
- 无宿主 Docker socket；
- 网络、CPU、内存、时间受限；
- 只能写约定工件目录。

### Agent Runner

用于 Claude Code/Codex 等调查 Agent：
- 读取固定 Snapshot 或受控 Workspace；
- 调用 Tool Gateway；
- 可以拥有模型访问能力；
- 默认不允许运行目标项目构建脚本；
- 不直接连业务数据库；
- 不拥有扩展 Scope 的能力；
- Repository 中的 README、注释、字符串都视为不可信数据，不能改变 Policy / ScanSpec / Tool 权限；
- 网络和代码外发由 Policy / Model Gateway 控制，不由 Prompt 自行决定。

### Validation Runner

仅在 VerificationPolicy 显式允许时创建：
- Runtime Harness；
- 局部组件验证；
- 授权黑盒测试。

它拥有更严格的网络目标白名单、速率、凭据和 payload 策略。Build / Agent / Validation 三种 Runner 不共享默认权限。

完整威胁模型、Prompt Injection、模型数据出境、Artifact 完整性和多租户边界见 [security-boundaries.md](security-boundaries.md)。

## 12. Coverage

Coverage 是一级业务模型，不是 UI 进度条。

至少区分：
- Repository/Snapshot；
- Asset；
- Root/Source/Sink/Guard；
- Method；
- Path/Relation；
- Case；
- Verification；
- unsupported / failed / unknown。

只有明确分母时才能计算百分比。完整定义见 [coverage-model.md](../subsystems/coverage-model.md)。

## 13. 数据与业务事实边界

- MySQL：业务事实、状态、Case、Evidence 索引、Verdict、Coverage、报告索引。
- Artifact Store：源码快照、CodeQL DB、工具原始输出、运行日志、报告文件。
- Redis：消息运输，不是审计事实源。
- Sourcebot：可重建代码搜索索引，不是证据账本。
- CodeQL DB：程序分析工件，不是业务数据库。
- Agent Workspace：临时调查目录，不是最终事实源。

## 14. 部署原则

AIxSecurity Core 保持模块化单体 + 多进程/多容器部署，不把 M1-M8 拆成八个微服务。

核心七容器仍是：
frontend、backend、celery-process、celery-worker、beat、redis、mysql。

Sourcebot、对象存储、监控、Runner 属于 Tool/Execution Services，可独立部署或 Compose profile 启用。因此“七容器”描述的是 Core，不是启用所有分析工具后的总容器数。

## 15. 实施入口

开发顺序见 [backend-implementation.md](../delivery/backend-implementation.md)。

当前优先级不是同时实现所有扫描器，而是先建立正确骨架：
1. 领域对象和不可变版本；
2. 可靠任务与工件；
3. Repo → Workspace → READY；
4. ScanSpec / Query Service / Case / Evidence；
5. 单一 Java 专项 Agent 调查 + STATIC_PROGRAM_REVIEW / INDEPENDENT_AGENT；
6. Claim / Coverage / Assurance 闭环；
7. Sourcebot / CodeQL 精度和性能实测；
8. 再逐步增加 Profile、Knowledge/RAG、多 Agent、跨仓和动态验证。

任何新增能力都必须有真实正例、反例、失败路径和 Coverage 影响，不能以“工具能启动”作为完成。
