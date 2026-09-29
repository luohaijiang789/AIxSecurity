# AIxSecurity 核心领域模型

状态：目标设计基线。本文定义系统中稳定身份、不可变版本、执行实例、调查对象和验证结果之间的关系，避免后续实现把“仓库、快照、扫描、Case、Finding”混为一体。

## 1. 三类对象先分清

AIxSecurity 的领域对象分为三类：

1. **稳定身份**：长期存在、可被多个版本引用，例如 Project、Repository、Service。
2. **不可变版本**：描述某一时刻的事实，例如 RepoRevision、AssetSnapshot、ScanSpec、CaseRevision。
3. **运行实例**：描述一次执行及其过程，例如 PreparationJob、ScanRun、AgentSession、VerificationRun。

原则：稳定身份可以更新元数据；不可变版本发布后不原地改；运行失败创建新的 attempt，不覆盖历史事实。

## 2. 代码与资产域

```text
Project
  ├─ Repository
  │    └─ RepoRevision(repo + commit)
  │          └─ PreparationJob
  │                └─ AssetSnapshot
  └─ Service / Module mappings

RepositorySet
  └─ RepositorySetSnapshot
       ├─ AssetSnapshot A
       ├─ AssetSnapshot B
       └─ ...
```

### Project
长期项目目录和权限边界，不承担代码版本身份。

### Repository
代码仓稳定身份，记录规范 URL、代码宿主、默认分支等。

### RepoRevision
固定代码版本，核心身份是 `repo_id + commit`。任何正式证据最终都必须能落到具体 RepoRevision。

### PreparationJob
一次资产准备运行。输入包括 RepoRevision、PreparationProfile、工具版本和构建上下文；输出工件、诊断和 AssetSnapshot。

### AssetSnapshot
不可变的“Security Analysis Workspace”发布版本，包含：
- 代码/文件 manifest；
- 构建和依赖事实；
- Sourcebot/代码搜索能力；
- Entry / Source / Sink / Guard / Data Asset；
- 程序/安全关系；
- CodeQL/程序分析工件引用；
- capability matrix；
- quality / gap。

### RepositorySetSnapshot
多仓分析的不可变成员清单。多个 commit 组成一个分析集合，不自动表示真实生产部署；部署一致性需要额外证据。

## 3. 安全知识与策略域

```text
VulnerabilityProfile
       │
       ├─ Framework Models
       ├─ Source / Sink / Guard Semantics
       ├─ Search Strategies
       └─ Verification Rules

Skill
  └─ Agent 专业操作方法

ScanPlan
  └─ 组合 Profile + 方法 + 深度 + Budget + Verification Policy
```

### VulnerabilityProfile
描述“某类漏洞专业上如何分析”，是规则、框架语义和验证约束的版本化知识对象。

### Skill
描述 Agent 在某类调查任务中的操作手册。Skill 可以引用 Profile，但不能替代 Profile 的结构化安全语义。

### ScanPlan
团队维护的版本化执行模板。定义允许的方法、深度、默认预算、必需 capability、VerificationPolicy 和输出要求。验证方法是可组合维度，不使用单一“等级”替代实际方法。

## 4. 扫描控制域

```text
ScanIntent
   ↓ normalize / validate
ScanSpec (immutable)
   ↓
ScanRun
   ├─ AnalysisTask
   ├─ AgentSession
   ├─ VerificationRun
   └─ ReportGeneration
```

### ScanIntent
用户在工作台表达的选择：目标、专项、范围、深度、预算等。它仍可修改。

### ScanSpec
服务端校验后冻结的不可变执行契约，至少绑定：
- snapshot_refs / repository_set_snapshot_ref；
- plan/version；
- profile_refs；
- analysis_scope；
- context_scope；
- authorized_snapshots；
- analysis_methods；
- allowed_tools；
- policy_snapshot_ref / data_policy_ref；
- agent_budget；
- verification_policy；
- output_policy。

ScanRun 执行过程中不得重新解析代码/资产的“latest”。安全 Policy 属于例外的保护边界：ScanSpec 记录创建时的 policy revision 以便复盘，但运行时当前 Policy 可以撤权或收紧，不能在未经新授权的情况下比 ScanSpec 创建时更宽松。每次敏感 Tool/Model/Runner 调用记录实际生效的 policy revision。

### ScanRun
一次执行实例。状态、Coverage、任务和最终报告都关联到它，但 ScanRun 不改变 ScanSpec。

## 5. 调查域

```text
Trigger / Candidate
       ↓
Security Case
       ↓
CaseRevision
  ├─ Hypothesis
  ├─ Claim[]
  │    ├─ Supporting Evidence
  │    ├─ Counter Evidence
  │    ├─ Assumptions
  │    └─ Gap
  └─ Analysis Trace
```

### Candidate / Trigger
规则、Source-first、Sink-first、CodeQL、代码搜索、图查询或 Agent 产生的候选线索。候选不是漏洞。

### Security Case
一个需要调查和裁决的安全问题稳定身份。多种分析方法可汇聚到同一 Case。

### CaseRevision
Case 的不可变证据版本。支持证据、反证或关键前提变化后创建新 revision，并计算新的 evidence_digest。

### Hypothesis
Agent 当前需要证明或否定的安全假设，不属于最终事实。

### Claim
把漏洞成立条件拆成可独立验证的声明，例如“输入可控”“路径可达”“Guard 不生效”“Sink 实际执行”“影响成立”。

Claim 至少包含：
- claim_id；
- kind；
- statement；
- required_by_profile；
- status：supported / contradicted / unresolved / not_applicable；
- supporting_evidence_refs；
- counter_evidence_refs；
- assumptions；
- gap_refs。

Verdict 应基于 Profile Verification Rules 对必需 Claims 的组合进行裁决，不基于整段 Agent 自然语言或模型投票。

### Gap
尚不能回答的关键问题，例如：
- 未支持框架；
- 远端服务关系未解析；
- 工具失败；
- 需要部署配置；
- 需要运行态事实；
- 预算耗尽。

Gap 是正式产品数据，不是日志里的异常文本。

## 6. 证据域

### EvidenceRef
指向可复核证据，至少包含：
- evidence_id；
- evidence_kind；
- repo / commit / snapshot；
- path / symbol / line range；
- tool + version；
- query / parameters；
- artifact digest；
- precision；
- acquisition method；
- created_at。

### ToolCall / ToolResult
工具调用轨迹和返回值。ToolResult 通过版本、来源和完整性校验后，才能升级为 Evidence。

### Evidence Bundle
一个 CaseRevision 可形成支持证据、反证、程序路径、源码片段、配置和运行时证据的集合。Evidence Bundle 是 Verifier 的主要输入。

## 7. 验证与结果域

```text
CaseRevision
    ↓
VerificationRun
    ↓
Verdict
    ↓
Finding
```

### VerificationPolicy
定义当前 Plan / Case **允许和要求**使用的验证方法，例如：
- STATIC_PROGRAM_REVIEW；
- INDEPENDENT_AGENT；
- ADVERSARIAL_DEBATE；
- RUNTIME_SANDBOX；
- AUTHORIZED_BLACKBOX；
- HUMAN_REVIEW。

这些方法可以组合，并不构成严格单调的强弱等级。

### VerificationRun
一次具体复核执行，绑定：
- case_revision；
- evidence_digest；
- method；
- verifier runtime / model / version；
- input_claims；
- claim_reviews；
- environment（动态验证时）；
- result artifacts。

### AssuranceState
描述当前 Case 的可信状态，而不是把某个验证方法直接当“等级”：
- candidate；
- reviewed；
- corroborated；
- reproduced。

其中 reproduced 必须绑定实际 environment_scope；corroborated 表示关键 Claims 得到独立验证路径或独立证据源支持。

### Verdict
对特定 CaseRevision + EvidenceDigest 的版本化裁决：
- confirmed；
- suspicious；
- rejected；
- needs_external_fact；
- unreviewed。

Verdict 同时保存：
- assurance_state；
- verification_methods_completed；
- verification_methods_required；
- unresolved_assumptions；
- environment_scope（如有）。

证据变化后旧 Verdict 保留审计记录但不再有效。

### Finding
报告层问题。只有有效 Verdict 满足输出策略时才生成 Finding。Finding 不是 Case，也不是 Verdict。

## 8. Coverage 域

CoverageSnapshot 绑定 ScanRun + 明确分母，保存：
- eligible；
- analyzed；
- resolved；
- unsupported；
- failed；
- skipped_by_policy；
- unknown。

Coverage 不能从 Case 数量反推。详细定义见 [Coverage 模型](../subsystems/coverage-model.md)。

## 9. 关键不变量

1. AssetSnapshot READY 后不可原地修改。
2. ScanSpec 创建后不可修改 Scope/Profile/版本；改变需求创建新 ScanSpec。
3. Agent 不能将 context_scope 中发现的新问题自动升级为 analysis_scope Finding。
4. Tool Result 与 Agent Reasoning 分开存。
5. Profile 要求的关键 Claim 未关闭时，不能仅因 Agent 同意而产生 confirmed Verdict。
6. CaseRevision 改变 EvidenceDigest 后旧 Verdict 失效。
7. Finding 必须能追溯到有效 Verdict、CaseRevision、Claims 和固定源码版本。
8. 动态/黑盒验证必须记录实际环境，不能外推成所有环境均可利用。
9. Coverage 只对定义过的分母有意义。
10. RepositorySetSnapshot 的成员不可在运行中替换。
11. 任何 provider（Sourcebot/CodeQL/Agent）都不能成为唯一业务事实源。
12. Repository Content 永远是数据，不得改变 ScanSpec、Policy、Skill 或 Tool 权限。
