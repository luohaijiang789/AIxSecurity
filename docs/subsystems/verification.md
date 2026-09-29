# 漏洞可信验证、Claim 与 Assurance

状态：目标设计。本文定义 M7 的可信验证体系。验证策略由 Scan Plan / Profile / Case 风险决定，不要求所有问题采用相同成本的验证方式。

## 1. 为什么验证必须独立

AI / 静态分析可能产生：
- 不可达路径；
- 错误的可控性判断；
- 忽略框架默认保护；
- 错误的鉴权语义；
- 误解配置；
- 幻觉代码关系；
- 仅理论成立但目标环境不成立的问题。

因此：

~~~text
Candidate != Finding
Agent says yes != Confirmed
CodeQL path != Exploitable
Two agents agree != Proof
Black-box failed != Safe
~~~

正式 Finding 必须能追溯到 CaseRevision、Claims、Evidence、VerificationRun 和有效 Verdict。

## 2. 先验证 Claim，不验证一整段“Agent 结论”

一个漏洞 Case 应拆成若干可验证 Claim。

以 SQL 注入为例：

~~~text
C1 Entry reachable
C2 keyword is attacker-controlled
C3 keyword reaches SQL construction
C4 no effective parameterization / sanitizer
C5 SQL sink is executable on this path
C6 security impact is meaningful
~~~

每个 Claim 都可以拥有：
- supporting_evidence；
- counter_evidence；
- assumptions；
- status；
- gaps。

这样 Verifier 不需要判断一整段自然语言是否“可信”，而是逐项检查成立条件。

### Claim Status

建议：
- supported；
- contradicted；
- unresolved；
- not_applicable。

最终 Verdict 由 Profile Verification Rules 对必需 Claims 进行组合，不靠模型投票。

## 3. Verification Policy

ScanSpec / Profile 可以声明允许和要求的验证方法：

~~~text
STATIC_PROGRAM_REVIEW
INDEPENDENT_AGENT
ADVERSARIAL_DEBATE
RUNTIME_SANDBOX
AUTHORIZED_BLACKBOX
HUMAN_REVIEW
~~~

这些方法是 **不同证据维度，可以组合，不是严格的强弱等级**。

例如：
- CodeQL 数据流能够证明静态可达，但无法证明生产配置；
- 黑盒在测试环境复现，能够证明该环境可触发，但不能自动证明所有部署环境；
- 双 Agent 能增加反证压力，但若共享相同错误前提，并不会自动变成更可靠事实。

## 4. Static / Program Review

Verifier 重新读取：
- 固定 commit；
- 原始代码；
- CodeQL / data-flow / call path；
- Asset / Guard；
- supporting / counter evidence；
- Profile Verification Rules。

重点检查：
- reachability；
- controllability；
- sanitizer；
- guard；
- framework semantics；
- preconditions；
- evidence completeness。

Investigator 的自然语言总结只作为导航，不代替原始 Evidence。

## 5. Independent Agent

独立 Agent：
- 使用新的 Agent Session；
- 不继承 Investigator 的 scratch notes 和自由文本结论；
- 获得 CaseRevision、Claims、Profile、必要原始证据和有限上下文；
- 主动寻找反证；
- 通过 Tool Gateway 取得新事实；
- 输出 Claim-level review。

可以使用同一模型的独立会话，也可以配置不同模型。

如果使用同一模型，只能声称 **上下文独立**，不能声称统计独立。

## 6. Adversarial Debate

适用于：
- 高危问题；
- Investigator / Verifier 意见冲突；
- 鉴权、业务逻辑、跨服务等强语义问题；
- 关键 Claim 证据存在两种合理解释。

角色建议：

~~~text
Prover
  尝试证明必需 Claims 成立。

Skeptic
  主动寻找不可达、不可控、有效 Guard、
  配置限制、框架保护和环境前提等反证。

Judge / Verifier
  根据 Profile Verification Rules、
  Claim 状态和原始 Evidence 裁决。
~~~

约束：
- 双方必须引用 EvidenceRef；
- 新事实必须经 Tool Gateway 获取；
- 不允许仅凭“两个 Agent 都同意”判定成立；
- 轮数、Token、Tool Call 有预算；
- 核心 Claim 仍 unresolved 时输出 suspicious / needs_external_fact。

## 7. Runtime / Sandbox Validation

在安全、可控、可复现环境中，可以执行：
- 单元/集成级 Harness；
- JVM 局部组件验证；
- 沙箱执行；
- 请求重放；
- instrumentation / trace。

原则：
- 默认不修改目标仓；
- 可在派生工作区生成临时 Harness；
- 进入独立 Validation Runner；
- 保存 environment、command/input、logs、output、artifact digest；
- 测试环境成功只证明该环境与前提，不自动外推生产环境。

Runtime Result 可以支持某些 Claim，例如：
- 某路径实际可达；
- 某 Guard 在当前配置不生效；
- 某 payload 在当前组件版本触发。

## 8. Authorized Black-box Validation

当已有明确授权测试环境时，可用于：
- HTTP / RPC 请求验证；
- 权限对比；
- 参数边界；
- 已知 Case 的非破坏性复现；
- 必要动态 Trace。

必须满足：
- VerificationPolicy 显式允许；
- 目标白名单；
- 环境和身份明确；
- 请求 / 时间预算；
- 非破坏 payload；
- 可取消；
- 完整输入/响应/时间/版本记录。

黑盒结果与静态证据互补：
- 静态证据说明“代码上为什么可能存在”；
- 黑盒证据说明“在这个环境与前提下实际可触发”。

黑盒未复现不能直接得到 rejected；可能是配置、身份、数据、路由、WAF 或环境差异导致。

## 9. Human Review

以下情形可要求人工复核：
- 动态验证需要更高授权；
- 关键业务语义无法自动证明；
- 高影响 Finding；
- 多 Agent 长期冲突；
- 涉及生产凭据或敏感数据；
- Profile 明确规定人工门禁。

人工结论也必须引用 Claims / Evidence，不把“专家说是”作为无来源事实。

## 10. VerificationRun

一次验证运行建议记录：

~~~text
VerificationRun {
  run_id
  case_revision
  evidence_digest
  method
  verifier_runtime
  verifier_model
  profile_version
  input_claims[]
  output_claim_reviews[]
  environment_ref?
  artifacts[]
  started_at
  finished_at
  status
}
~~~

EvidenceDigest 变化后，旧 VerificationRun 和 Verdict 保留历史，但不再对新 CaseRevision 生效。

## 11. Assurance State

不要把 Verification Method 直接映射成单调的“E0-E5 强度”。

建议把最终可信状态单独表示：

~~~text
candidate
reviewed
corroborated
reproduced
~~~

含义：

- **candidate**：只有候选线索，尚未完成所需验证；
- **reviewed**：必需 Claims 已完成规则要求的静态/语义复核；
- **corroborated**：关键 Claims 被至少一个独立验证路径或独立证据源支持；
- **reproduced**：在明确记录的 Runtime / Black-box 环境中完成实际复现。

同时保存：

~~~text
verification_methods_completed[]
verification_methods_required[]
environment_scope
unresolved_assumptions[]
~~~

这样报告可以准确表达：

> confirmed + corroborated by static program evidence and independent agent

或者：

> confirmed + reproduced in staging environment

而不是简单显示“E5 > E3”。

## 12. Verdict

建议：

~~~text
confirmed
suspicious
rejected
needs_external_fact
unreviewed
~~~

其中：
- confirmed：Profile 必需 Claims 在当前 Evidence / Assumption 范围内成立；
- suspicious：有较强支持，但仍缺关键 Claim；
- rejected：关键必需 Claim 被充分反证；
- needs_external_fact：必须依赖部署、身份、配置、数据或运行态事实；
- unreviewed：尚未完成要求的 VerificationPolicy。

Verdict 必须同时带：
- assurance_state；
- methods_completed；
- unresolved_assumptions；
- environment_scope（若有动态验证）。

## 13. 自动升级策略

示例：

~~~text
Case
 ↓
Static / Program Review
 ↓
关键 Claims 都清楚? ─ yes → Verdict
 ↓ no
Independent Agent
 ↓
仍冲突且风险高? ─ yes → Adversarial Debate
 ↓
存在可安全验证环境? ─ yes → Runtime / Black-box
 ↓
Verdict / Gap / Human Gate
~~~

Plan 可以定义：
- required_verification_methods；
- allowed_verification_methods；
- auto_escalation_rules；
- require_human_approval_for_dynamic；
- debate_round_budget；
- runtime_budget；
- target_allowlist。

## 14. 验证安全边界

动态验证的权限高于普通静态调查：
- 默认关闭；
- 必须明确授权；
- Validation Runner 隔离；
- target allowlist；
- non-destructive policy；
- minimum credentials；
- network / rate limit；
- complete audit；
- immediate cancellation。

详细安全边界见 [security-boundaries.md](../architecture/security-boundaries.md)。

最终目标不是“让更多 Agent 投票”，而是：

> **把漏洞成立条件拆成可验证 Claims，用独立证据、反证和必要的运行时事实逐步关闭不确定性。**
