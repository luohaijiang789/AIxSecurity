# Coverage 与“测完”模型

状态：目标设计。Coverage 是 AIxSecurity 的一级产品能力，用于回答“这次到底分析了什么、还剩什么、为什么没有完成”，而不是一个装饰性的百分比。

## 1. 基本原则

任何 Coverage 百分比都必须有：
- 明确分母；
- 明确 Scope；
- 明确 Snapshot / commit；
- 明确 Profile / 方法；
- 明确时间点；
- unsupported / failed / unknown 的独立计数。

禁止：
- 用 Agent 任务全部结束表示 100%；
- 用 Case 数量表示覆盖率；
- 把 unsupported 从分母中偷偷删除；
- 把工具失败算成安全；
- 没有分母时输出“全覆盖”。

## 2. CoverageSnapshot

建议结构：

```text
CoverageSnapshot {
  run_id
  dimension
  denominator_definition
  eligible
  attempted
  analyzed
  resolved
  unsupported
  failed
  skipped_by_policy
  unknown
  updated_at
}
```

### eligible
按当前 ScanSpec/Profile 应当进入分析范围的对象。

### attempted
至少启动过一个分析动作的对象。

### analyzed
当前要求的方法已经产生有效结果或明确 Gap。

### resolved
该对象相关候选已经完成规定验证，或依据规则明确排除。

### unsupported
平台当前没有能力分析，必须带 capability / framework 原因。

### failed
本应执行但由于工具、构建、模型或系统错误失败。

### skipped_by_policy
用户 Plan、预算或显式策略决定不执行。

### unknown
分母或解析状态本身无法确定。

## 3. 主要 Coverage 维度

### 3.1 Repository / Snapshot Coverage

```text
目标仓库数
READY 快照数
PARTIAL 数
FAILED 数
缺失成员数
```

多仓扫描必须同时展示集合成员完整度。

### 3.2 Asset Coverage

例如：
- HTTP Endpoint；
- RPC Provider；
- MQ Consumer；
- Job；
- Source；
- Sink；
- Guard；
- Data Asset；
- External Client。

回答“有哪些资产被识别，哪些框架仍无法提取”。

### 3.3 Root / Source / Sink Coverage

不同 Profile 使用不同分母。

SQLi 例：

```text
eligible SQL sinks = 127
attempted          = 124
analyzed           = 119
unsupported        = 3
failed             = 2
unknown            = 3
```

鉴权例则应以 Entry / Sensitive Operation / Guard 检查对象为分母，不强行套 Source-Sink。

### 3.4 Method Coverage

记录本次实际采用：
- Source-first；
- Sink-first；
- Rule/AST；
- CodeQL/PA；
- Graph；
- Agent semantic review；
- change-driven 等。

Plan 要求的方法未执行必须显式显示。

### 3.5 Path / Relation Coverage

对需要路径证明的专项记录：
- path requested；
- path resolved；
- no-path proven；
- timeout；
- model missing；
- cross-service unresolved。

“没找到路径”与“证明不存在路径”不能混为一类。

### 3.6 Case Coverage

```text
opened
investigating
ready_for_verification
reviewed
blocked
needs_external_fact
```

Case 完成率仅表示调查流程状态，不代表代码覆盖率。

### 3.7 Claim Coverage

对进入 Case 的必需 Claim 记录：
- required claims；
- supported；
- contradicted；
- unresolved；
- not_applicable。

Claim Coverage 用于解释为什么某个 Case 仍然 suspicious / needs_external_fact，不能替代代码资产 Coverage。

### 3.8 Verification Coverage

按 Verification Policy 记录：
- 要求 STATIC_PROGRAM_REVIEW 的 Case 有多少完成；
- 要求 INDEPENDENT_AGENT / ADVERSARIAL_DEBATE 的 Case 有多少完成；
- 动态验证多少被授权、多少实际执行、多少因环境缺失无法执行；
- assurance_state 为 candidate / reviewed / corroborated / reproduced 的分布。

Verification Method 是可组合维度，不按 E1/E2/E3 单线等级统计。

## 4. Coverage 与 Gap 的关系

每一个 incomplete 都必须能归因：

```text
Coverage Missing
   ├─ unsupported framework
   ├─ tool unavailable
   ├─ build failure
   ├─ unresolved symbol
   ├─ remote edge unresolved
   ├─ budget exhausted
   ├─ permission denied
   ├─ requires runtime fact
   └─ user policy skipped
```

这样才能知道下一步应该：
- 增加分析能力；
- 修复工具；
- 补资产；
- 增加预算；
- 请求部署事实；
- 或者什么都不做，因为本来就是用户选择跳过。

## 5. 百分比计算

只有在 denominator 已知时才计算：

```text
analysis_coverage = analyzed / eligible
resolution_coverage = resolved / eligible
```

同时必须并列展示 unsupported / failed / unknown；百分比不能遮蔽这些数量。

例如：

```text
SQL Sink Analysis
119 / 127 analyzed = 93.7%

Remaining:
- unsupported: 3
- failed: 2
- unknown: 3
```

不能只显示“93.7%”。

## 6. 多仓 Coverage

RepositorySetSnapshot 的 Coverage 先分两层：

1. **Member readiness**：所有必要仓和固定版本是否存在。
2. **Cross-repo relation coverage**：HTTP/RPC/MQ 等远端关系解析到什么程度。

单仓内部分析完成，不等于多仓调用链已经完成。

对于跨服务路径至少区分：
- remote target resolved；
- target candidate；
- environment ambiguous；
- payload mapping unresolved；
- identity/tenant propagation unknown。

## 7. 变更扫描 Coverage

Change Scan 的分母不是整个仓，而是：
- changed files；
- changed symbols；
- impacted Entries；
- impacted Sources/Sinks/Guards；
- dependency / config changes；
- 受影响调用子图。

必须同时记录 impact expansion 的边界，不能因为只扫 diff 就宣称整个仓安全。

## 8. UI 建议

扫描详情页至少同时展示：

```text
Snapshot readiness
Asset coverage
Profile coverage
Method coverage
Analysis coverage
Verification coverage
Unsupported / Failed / Unknown
Top Gaps
```

用户点击任一数字都应能够下钻到具体对象和原因。

## 9. “测完”的正式定义

AIxSecurity 不提供脱离上下文的全局“测完”。

正确表述应类似：

> 对 RepositorySetSnapshot X，按照 ScanPlan Y / Profile SQLi vN，在 analysis_scope Z 内，127 个 eligible SQL Sink 中 119 个完成要求的方法和验证；3 个框架未支持、2 个工具失败、3 个关系未知，因此本次 analysis coverage 为 93.7%，状态为 partial。

这种回答才是可审计的“测没测完”。
