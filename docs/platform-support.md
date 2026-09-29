# 平台支撑能力：Knowledge / Policy / Memory / Observability

状态：目标设计。本文定义横跨 M1-M8 的支撑能力，避免把企业知识、模型调用、Agent 记忆和可观测性散落到各模块内部。

## 1. 为什么需要支撑面

AIxSecurity 的核心业务主链是：

```text
Asset / Program Facts
 → ScanSpec
 → Agent Investigation
 → Verification
 → Finding / Coverage
```

但真正可长期运行的企业级系统还需要四类横向能力：

```text
Knowledge
Policy
Memory
Observability
```

它们不是新的漏洞扫描模块，也不改变 M1-M8，而是为所有模块提供一致的规则、知识和可追溯性。

## 2. Security Knowledge

### 2.1 保存什么

Security Knowledge 可以包含：
- 企业内部安全编码规范；
- 框架安全语义，例如 Spring Security、MyBatis、Jackson；
- 历史已确认漏洞模式；
- 误报经验；
- 内部 SDK / 中间件安全约束；
- CWE / OWASP / 厂商文档等公开安全知识；
- Profile / Skill 所引用的参考知识。

### 2.2 RAG 的定位

RAG 用于给 Agent 提供安全与框架上下文：

```text
Goal
  ↓
retrieve knowledge
  ↓
Agent reasoning
```

但知识检索结果只属于 **Context Evidence / Advisory Context**，不能单独证明目标代码存在漏洞。

例如：
- 文档说明某 API 危险：属于知识；
- 当前代码实际调用该 API：属于代码事实；
- 用户输入可以到达该调用：属于程序/数据流事实；
- 因此漏洞成立：属于经过验证的安全结论。

四层不能混淆。

### 2.3 Knowledge 版本

进入正式调查的知识必须记录：
- knowledge_source；
- version / revision；
- retrieved_chunks；
- retrieval_query；
- digest；
- timestamp。

Profile 和 Skill 可以绑定最低知识版本要求。

## 3. Policy

Policy Engine 负责跨模块统一执行硬约束：

- 项目 / Repository / Snapshot 授权；
- analysis_scope / context_scope；
- Tool allowlist；
- 模型 provider allowlist；
- Token / 时间 / Tool Call Budget；
- 动态验证开关；
- Validation Target allowlist；
- 数据出境 / 代码外发策略；
- Secret redaction；
- 网络访问策略；
- Runner 权限；
- 报告可见范围。

Policy 判断发生在能力入口，不依赖 Prompt 自觉遵守。

```text
Agent request
   ↓
Policy check
   ↓ allow / deny / require approval
Tool Gateway / Model Gateway / Runner
```

### Policy 版本与运行时收紧

ScanSpec 记录创建时的 policy/data-policy revision，便于复盘“当时为什么允许这次扫描”。

但安全策略不能像代码快照一样完全冻结：
- 权限撤销必须立即生效；
- Provider 被禁用必须立即生效；
- 数据外发规则收紧必须立即生效；
- 动态验证 target allowlist 收紧必须立即生效。

因此运行时采用 **no-broader-than-authorized** 规则：当前 Policy 可以比 ScanSpec 创建时更严格，但不能自动更宽松。需要放宽权限时必须重新授权或创建新 ScanSpec/approval。

每次高风险 Tool/Model/Runner 调用记录 actual_policy_revision。

## 4. Memory

必须区分三类“记忆”。

### 4.1 Working Memory

单个 Agent Session 的临时状态：
- 当前假设；
- 已查路径；
- scratch notes；
- 临时摘要。

Session 结束后可归档，但不是业务事实。

### 4.2 Case Memory

正式进入 Case 的结构化信息：
- Claims；
- Hypotheses；
- Evidence；
- Counter Evidence；
- Gap；
- Analysis Trace。

这是可复核业务数据。

### 4.3 Long-term Security Knowledge

跨项目复用的知识：
- Profile；
- Skill；
- Framework Model；
- 经过治理的漏洞模式；
- 团队规则。

不能把某次 Agent scratch 自动升级成长久知识；需要显式审核、版本和来源。

## 5. Model Gateway

所有模型调用建议通过 ModelGatewayPort，而不是不同模块各自拼 HTTP：

```text
Agent Runtime
Verifier
Debate Judge
Knowledge Assistant
      ↓
Model Gateway
      ↓
Provider A / Provider B / Local Model
```

Gateway 负责：
- provider / model 选择；
- timeout / retry；
- rate limit；
- token budget；
- data policy；
- request / response schema；
- usage / cost；
- redaction；
- trace_id；
- 模型版本记录。

对于高敏代码，可按项目策略限制：
- 只允许私有部署模型；
- 只发送最小代码片段；
- 禁止发送 Secret / Credential；
- 禁止发送指定目录；
- 禁止跨区域 provider。

## 6. Tool Registry

Tool Registry 保存正式可调用工具及能力：

```text
tool_id
tool_version
capabilities[]
input_schema
output_schema
runner_type
resource_profile
network_policy
evidence_precision
health
license / distribution notes
```

典型工具：
- git / ripgrep / fd / jq；
- Sourcebot；
- Tree-sitter / Java parser；
- CodeQL；
- Semgrep；
- Maven / Gradle / JDK；
- SBOM / dependency tooling；
- 可选 Soot / WALA / Joern；
- 动态验证所需测试工具。

“已安装”与“capability supported”不是一回事。只有版本、固定样本和失败路径验收通过后，Capability 才能标记 supported。

## 7. Observability

至少记录四层指标。

### 7.1 Platform
- API 延迟；
- 队列深度；
- outbox backlog；
- Worker utilization；
- Runner failure；
- Artifact storage。

### 7.2 Tool
- query latency；
- success / timeout；
- index freshness；
- CodeQL build/query cost；
- Sourcebot P50/P95；
- parser unresolved rate。

### 7.3 Agent
- session duration；
- model / version；
- token usage；
- tool calls；
- evidence yield；
- repeated/no-progress loops；
- budget exhaustion；
- cost。

### 7.4 Security Quality
- Candidate → Confirmed conversion；
- false-positive rate（以人工/运行时复核为基准时）；
- unsupported / failed / unknown；
- Profile Coverage；
- Verification Coverage；
- 不同方法新增发现贡献；
- Debate / Runtime 对结论改变比例。

## 8. Evaluation

Agent 或 Profile 的变更不能只看“感觉更聪明”。

应维护固定 Evaluation Corpus：
- 正例；
- 反例；
- 框架特例；
- Guard 生效；
- Guard 失效；
- 不可达路径；
- 跨模块；
- 跨仓；
- build failure；
- adversarial source comments。

每次 Profile / Skill / Agent Runtime / Model 版本升级至少比较：
- recall proxy；
- precision；
- unresolved；
- time；
- tool calls；
- token / cost；
- evidence completeness。

## 9. 与核心领域模型的关系

Knowledge / Policy / Memory / Observability 不替代业务事实：

- Knowledge 不替代 Evidence；
- Policy 不替代 ScanSpec，但负责强制执行 ScanSpec；
- Working Memory 不替代 Case；
- Trace 不替代 Verdict；
- Evaluation 数据不直接进入 Finding。

这些能力作为横向支撑层服务 M1-M8。
