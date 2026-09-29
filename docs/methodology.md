# AIxSecurity 方法论与证据契约

状态：目标方法论；不是“全部已实现”清单。整理日期：2026-09-28。

## 1. 原始思路与不变目标

本文固定重建时保留的方法与证据原则，不记录历史执行流水。

**Asset-First、Source-Driven：资产先行，程序事实打底，人选方案，多方法调查，受控 Agent 补证，多级可信验证，证据驱动报告。**

- 目标只有发现安全问题、补证、复核、报告；不自动修复目标代码，不做规则自我进化。
- Java 优先，输入支持一个或多个微服务代码仓的设计；多仓模型保留，跨服务路径能力逐步验证。
- 资产中心自动完成准备并发布不可变 READY 版本。READY 是可复用资源，不是等人继续的扫描任务。
- 人在扫描工作台选择 READY 版本、扫描策略、专项、范围和预算，之后才开始调查和模型调用。
- Source-Driven 不是 Source-only；Sink-first、规则/AST、程序分析、关系导航与业务语义调查互补。
- “程序证据 → Agent 调查 → 多级可信验证 → 报告”是证据责任链，不是让模型改写工具结果。
- 工具输出是事实或线索，模型输出是推断，验证器按规则裁决；三者分开存储。

设计详见 [架构](architecture.md)，已实现边界见 [文档入口](README.md)。以下保留完整核心方法、字段及精度约束。

## 2. Java 静态安全资产模型（核心底座）

### 2.1 需要发现的资产

| 资产域 | 完整目标模型 | 首版建议优先提取 |
|---|---|---|
| 代码结构 | Repo、Module、Service、Package、Class、Method、Field、Annotation | Maven 模块、类/方法、注解与符号位置 |
| 触发入口 Entry | HTTP、RPC Provider、MQ Consumer、WebSocket、Listener、Job、CLI、回调 | Spring MVC HTTP、基础 Scheduled Entry |
| 数据输入 Source | HTTP 参数/body/header/cookie/upload、RPC/MQ 字段、外部文件、二阶存储输入 | Spring/Servlet 参数和上传元数据 |
| 敏感操作 Sink | SQL、文件、命令、网络、反序列化、表达式、反射、XML、敏感数据操作 | 初选漏洞 Profile 对应的 SQL/文件/命令操作 |
| 防护 Guard | 认证、授权、归属/租户、验证、净化、编码、规范化、白名单 | 常用权限注解与参数化/路径检查候选 |
| 数据资产 | 数据库/表、Redis、文件、对象存储、消息主题 | 可识别的数据访问与文件资源引用 |
| 外部交互 | HTTP Client、RPC Client、MQ Producer、第三方 SDK | HTTP 客户端和可识别目标引用 |
| 环境事实 | 依赖、构建、配置、框架、安全配置 | pom、YAML/properties/XML，依赖与框架标记 |

这是提取范围设计，不承诺首版完整理解所有框架。每类资产必须有 supported/partial/unsupported
及原因；不把首版未实现的 RPC/MQ/二阶路径从目标数据模型中删除。

### 2.2 四类对象不能混淆
- **Entry Root**：触发执行的位置，例如 HTTP Endpoint 或 Scheduled Job。
- **Taint Source**：具体可控数据，例如 endpoint 的 path 参数；与 Entry 用关系关联，不合并成一个字段。
- **Asset Root**：依赖、配置、秘密等资产检查的出发对象；不强套污点路径。
- **Security Guard**：观察到的保护机制；“发现注解/校验调用”与“对当前路径有效”是不同状态。

例如：Job 是 Entry；Job 从数据库读到的值，只有在写入来源和信任边界有证据时才能认定为
二阶不可信输入。Path.normalize 的存在不等于路径遍历已被防止。

### 2.3 字段与来源契约（草案）
- 共同字段：asset_id、kind、repo_revision、service/module、symbol、location、extractor_version、evidence_refs、resolution_status。
- Entry：协议/触发类型、路由或处理方法、绑定参数、可见性。
- Source：关联 Entry/存储资产、数据类型、trust_level、control_origin、constraints、条件证据。
- Sink：操作类别、目标符号、敏感参数位置、框架语义引用。
- Guard：保护类型、作用对象/条件、适用路径、observed/proven/unknown 状态和证据。
- Relation：from/to、关系类型、条件、来源、解析精度（确定/候选/未知）。

示例关系：CONTAINS、EXPOSES、CALLS、READS、WRITES、FLOWS_TO、GUARDED_BY、HTTP_CALL、PUBLISHES/CONSUMES。
关系图用于导航，不等于漏洞成立的精确数据流。精确路径通过 Query Service 回查并带来源。

## 3. 两阶段资产发现与快照复用

**Pass 1：No-Build。** 解析 Git 文件、Java 语法/注解、构建文件、配置和框架线索，生成基础资产。
标记 unresolved 符号和推断关系；不把文本匹配关系标为精确调用边。

**Pass 2：Build-Enhanced。** 隔离执行构建，提取类型、符号、接口实现、候选动态分派、调用与数据流，
关联分析数据库，再增强同一语义资产模型。CodeQL 是设计中的主要候选，版本/兼容性在实施前核验。

**合并规则：** 保留每个提取器来源；精确事实可增强低精度记录，但冲突保留为 conflict，不静默覆盖。
快照生成后不可原地改语义事实；新提取结果生成新 revision。

**复用键：** 不只使用 commit；还须包含源码/配置内容摘要、提取器与框架模型版本、构建上下文和分析工具版本。
同一版本的资产供 SQLi、路径、鉴权等不同扫描计划复用。结果缓存另包含 Plan/Profile/模型/提示版本。

**构建失败：** 保留 Pass 1 产物和失败诊断；必要构建失败则资产保持 PARTIAL/FAILED，
由资产中心修复或明确调整准备配置，再重新校验发布。扫描工作台不临时降级以绕过就绪条件。跨 commit 增量提取保留设计接口，首版先全量重建并验证快照复用。

### 3.1 三类查询数据加一份代码事实源

| 数据层 | 负责什么 | 不应混淆 |
|---|---|---|
| 代码镜像与 RepoRevision | 固定原始源码、文件哈希、commit | 不是分析结果 |
| 代码搜索索引（Sourcebot 首选适配） | 跨仓快速找代码、定义、引用、文件树、提交/Diff和配置上下文 | 搜索结果不是精确污点证明 |
| 程序分析数据库（CodeQL 候选） | 查询程序结构、调用/数据流及路径证据 | 工具库不是统一业务安全资产模型 |
| AIxSecurity 安全资产库/关系图 | 归一化 Entry/Source/Sink/Guard、服务和来源关系 | 不复制所有底层事实，不自动证明跨服务传播 |

Sourcebot 官方提供跨仓搜索、代码导航和带引用的代码问答；CodeQL 官方将流程区分为
数据库创建、查询执行、解释结果。这两种工具职责互补，不是二选一，也不要求首版都部署。
工具能力与 AIxSecurity 适配完成度分开：当前还没有验证本地集成、Java 框架精度或固定版本检索。
资料：[Sourcebot 官方仓库](https://github.com/sourcebot-dev/sourcebot)、[CodeQL 官方概述](https://codeql.github.com/docs/codeql-overview/about-codeql/)。

统一 Query Service 对外按功能暴露 source_search、read_symbol、lookup_asset、find_callers、
trace_flow、query_relations 等设计接口；每个结果必须带 repo/commit/asset_snapshot/来源/精度。
若索引只能给出当前分支结果，不能将它冒充固定快照证据；应重新校验文件哈希或返回版本不匹配。
尚未选择专用图数据库；上述是逻辑数据职责，不意味着部署四套数据库服务。

### 3.2 多仓微服务的版本与关联

输入可以是一个链接，也可以是链接集合。RepoRevision 固定为 repo_id + commit。
**AssetSnapshot 固定为单仓不可变版本**，绑定一个 RepoRevision、准备配置/工具/框架模型摘要和产物。
**RepositorySetSnapshot 是不可变多仓成员清单**，至少记录 set_id、每个 repo_id 对应的
asset_snapshot_id/commit、模块/服务映射、配置上下文引用及缺失成员；成员引用已发布的单仓快照。
Project 是长期目录身份，不承担版本身份。整组有必要成员缺失时不发布为可运行集合；
单仓准备成功不等于所属多仓集合准备成功。更新任一成员产生新集合，不替换旧集合成员。
多个 commit 组成分析集合，不自动代表同一时间或同一生产部署；部署关系需要独立证据。

Repo → Module → Service 不是固定一对一：一个仓可以有多个服务，一个服务也可能依赖多个仓。
服务关联可依据 HTTP 路由/客户端、RPC 接口、MQ topic、配置中的服务名等形成候选关系。

严格区分四级：代码搜索线索 → 关联关系 → 跨服务传播路径 → 已验证安全问题。
同名路由/topic 不是充分证据；还要检查环境、目标解析、消息字段、转换与身份前提。
跨进程传播由模型与证据拼接，不假设把多个 CodeQL 数据库放在一起就自动产生跨服务数据流。

多仓资产汇总可先实现，跨仓漏洞求解后实现；未解析远端边应出现在 Case/报告的缺口中。
单仓试验只是首个验收样本，不应把存储模型改成只支持一个 repository_id。

### 3.3 工具选型的精度边界（既有资料记录，集成时重新核验）

Java 建库不必然要求成功编译：GitHub 当前文档列出 Java 的 none/autobuild/manual 模式。
none 模式可能通过 Maven/Gradle 获取依赖信息，因此不代表完全不执行项目相关工具；
混合 Kotlin 项目须明确覆盖缺口。我们的“无构建基础提取”和“构建增强”是产品处理层次，
不与 CodeQL 的模式简单一一对应。准备记录必须保存实际工具版本、构建模式及提取范围。
参见 [CodeQL 构建模式](https://docs.github.com/en/enterprise-cloud%40latest/code-security/reference/code-scanning/codeql/build-options-for-compiled-languages)。

CodeQL 的全局数据流比局部分析更有成本和建模限制，不能把“抽取数据流信息”写成
“前置阶段已求出所有漏洞路径”。参见 [数据流分析说明](https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/)。
Sourcebot 作为首选检索/导航适配器进入前置代码准备，但固定版本搜索可用性、权限映射、引用精度和本地部署仍须通过真实仓库验收；详见 [Sourcebot 集成设计](sourcebot-integration.md)。
首版不同时承诺完整 Sourcebot、向量库、图数据库及所有分析器的集成。

## 4. Scan Intent、Scan Plan 与 Vulnerability Profile

### 4.1 人决定扫描策略
Intent 表达目标、范围、漏洞类别、深度、时间/调用预算；Scan Plan 是团队维护的版本化执行模板。
保留快扫、深扫、专项、变更扫描等扩展语义，不恢复动物命名，也不要求首版全部实现。
保留广泛/深度/专项三个用户可理解的选择维度（不是动物品牌模式）。
首版建议：**一个人工选择的 Java 专项深扫模板**，由 Profile 参数选择漏洞类别；初始切片采用 SQLi；命令注入和路径穿越在独立验收后扩展。

ScanSpec 至少绑定：plan_id/version、target/asset_snapshot、scope、profile_refs、analysis_methods、
build_requirements、fallback_policy、agent_budget、verification_policy、output_policy。
scope 分为 analysis_scope（允许提出候选问题的目标）和 context_scope（允许读取的依赖上下文）；
authorized_snapshots 是项目/版本硬边界。读取同版本 Service、Repository 或配置不自动扩大候选
发现范围；越界新问题只能建议另建计划。ScanSpec 固定 snapshot_refs[] 或集合引用，禁止运行时解析 latest。
计划缺少必要分析能力时在工作台禁用或验证拒绝，并指向资产中心处理，不静默关掉方法。Agent 可建议另开计划，但必须由人决定。

### 4.2 Profile 是专业分析模型，不是一段 Prompt
每个 Profile 包含：适用 Root、Source、Sink、Propagation、Sanitizer、Guard、Framework Models、
Search Strategies、Agent Playbook、Verification Rules，以及版本和测试样本。
SQLi、路径遍历、SSRF、鉴权的专业规则不同；首版只实现选定的 Profile，不在代码里锁死一种漏洞。

### 4.3 扫描深度与方法是两个维度
一个计划可以组合多种方法。同一方法也可被多个计划复用。深扫允许更多时间和调查轮次，
但仍受用户明确预算和停止条件约束，不再由实现随意统一硬编码“两轮”。

## 5. 多方法分析如何协作

1. **Source-first 主搜索**：选择 Profile 的可信 Root/Source 定义，向目标 Sink 追踪传播与边界。
2. **Sink-first 补漏**：枚举该类别 Sink，反查尚未关联的输入与调用方，保留不可解析原因。
3. **Rule/AST 补特征**：快速发现结构和模式线索，不将文本命中直接写为已确认漏洞。
4. **CodeQL/程序分析与 Graph**：提供数据流/路径证据和全局导航，支持前两条搜索。
5. **Agent 语义补充**：在计划内加载 Profile + Skill + Goal，经 Tool Gateway 审查业务前提、配置、框架保护和缺失关系，可提出新 Case；Agent 不拥有扩大 ScanSpec 的权限。

鉴权等 Profile 用 Entry → Sensitive Operation → Guard 检查链，而非强行走 Taint Source → Sink。
覆盖至少分开记录：Root/Sink 清单、实际分析项、未解析项、失败项和未支持项。
没有完整分母时不输出“覆盖率 100%”；不能用 Case 数量冒充覆盖率。

## 6. Security Case、证据与 Agent 分工调查

### 6.1 统一 Case
草案字段：case_id、profile_ref、asset_snapshot_ref、triggers、entry/source/sink/asset_refs、
path_refs、context_refs、hypotheses、claims、supporting_evidence、counter_evidence、gaps、analysis_trace、state。
跨仓 Case 使用 snapshot_refs[] 或 repository_set_snapshot_ref，不用单个快照字段冒充多仓证据。
Case 具有递增 case_revision；变更 Claim、支持、反证或关键前提后计算新的 evidence_digest。
Claim 把漏洞成立条件拆成可单独验证的声明，例如“输入可控”“路径可达”“Guard 不生效”“Sink 执行”“影响成立”；每个 Claim 绑定 supporting/counter evidence、assumptions 和 status。
Evidence 至少绑定工具与版本、查询参数、commit/快照、源码位置、工件哈希、获取方式及精度。

多方法命中同一操作时做关联，不只按行号去重；不同输入、路径和前提保留独立分支。
同一 CodeQL 路径被不同方法引用仍是同一证据，不重复加权。

Case 状态草案：open → investigating → ready_for_verification → reviewed。
执行失败单独记录，不能用 rejected 表示“没跑完”。

### 6.2 Agent 分工由编排器落实
人的选择先变成 ScanSpec，M5 按 Profile、方法、服务/模块和 Case 拆成任务，
再分配调查 worker；不是先放出多个 Agent，让它们自行决定如何扫整个仓库。
同一个 Investigator 可以加载不同 Profile/Playbook，不必每个漏洞类型常驻一个 Agent。
同 Case 的并发修改用版本检查或单写入者合并；任务失败可见，不把重复执行当独立发现。
Reviewer/Verifier 使用独立上下文，Reporter 通常无需 Agent。

### 6.3 Agent 是调查者
输入是 Case + Profile + 有限且可溯源的上下文，不是整仓任意聊天。
可读源码、查调用者、查 Source/Sink/Guard、查配置、请求精确路径、寻找支持与反证。
每个请求经过计划范围/预算检查；记录工具请求与结果引用。

停止条件：证据足够支持或否定、需要外部事实、预算耗尽、工具缺失、无新增证据。
预算耗尽输出缺口而非编造结论。工具输出和代码注释仅作数据，不能更改扫描计划或权限。

## 7. 可信验证与报告

Verifier 使用原始证据和独立上下文，按 Profile Verification Rules 逐项检查必需 Claims，而不是判断一整段 Agent 结论是否“看起来合理”。
同模型独立调用仅代表上下文分离，不能宣传模型错误独立。

Verification Method 可以组合：
- STATIC_PROGRAM_REVIEW；
- INDEPENDENT_AGENT；
- ADVERSARIAL_DEBATE；
- RUNTIME_SANDBOX；
- AUTHORIZED_BLACKBOX；
- HUMAN_REVIEW。

Verification Method 不是严格单调的强弱等级。运行时或黑盒在某个环境复现，只证明该环境与前提；双 Agent 同意也不能代替 Claim-level Evidence。

Verdict 草案：confirmed、suspicious、rejected、needs_external_fact、unreviewed。
每项绑定 assurance_state、verification_methods_completed、关键 Claims、证据、限制和 unresolved assumptions。
Verdict 必须绑定 case_revision + evidence_digest + verifier_version；Case 或证据变更后旧裁决保留审计记录但失效，报告只引用匹配当前版本的有效裁决。
动态验证不是首版必经步骤，未经运行证明的内容不能写成“已成功利用”。

报告包含：commit、资产/构建状态、Plan/Profile/Skill/工具/模型版本、实际方法、Assurance、Coverage/Gap、问题和待确认列表。
每个问题含位置、路径、Claims、支持/反证、成立条件、验证方法、environment scope 与影响说明。排除项留审计记录。
不自动改目标代码；本项目也不在此次范围实现规则自我进化与自动回灌。


## 周期自动化与人工决策的关系

人工选择既包括当次发起，也包括显式批准、版本化的周期审计策略。定时拉仓、构建与资产刷新保留；定时审计必须绑定授权范围、Plan/Profile、预算及快照选择策略。
系统为每个到期周期生成不可变 ScanSpec，不把运行中的 latest 当证据版本；周期策略不是给 Agent 自由扩扫的权限。默认纳入/READY 不自动扫描，授权的 refresh_then_scan 才允许准备成功后继续审计。
部署与调度规则统一见 [多容器设计](deployment-storage.md)。

## 8. 效果验证原则

资产复用预期减少重复准备成本，多方法预期补充覆盖，独立复核预期减少误报；这些是待验证假设，不是当前效果结论。
用同一固定版本样本、同一预算、独立标签对照比较工具基线、增加调查、增加复核、多方法组合；同时报告漏报、误报、未知、成本和覆盖分母。
新增能力必须有正例、反例、真实样本与失败路径；模型故障与证据不足不能计为排除漏洞。完整实验约定见 [后端实施与验收](backend-implementation.md)。


## 9. Agent Runtime、Skill 与 Goal

Profile、Skill、Goal、Plan 必须分开：

- **Profile**：专项漏洞的结构化安全知识和验证规则；
- **Skill**：Agent 可复用的专家调查方法；
- **Goal**：某个 Case 当前需要回答的具体问题；
- **Plan**：本次扫描允许使用的方法、范围、深度、预算和 VerificationPolicy。

Agent 输入来自固定 ScanSpec + Workspace，不是整仓自由聊天。所有关键代码读取、程序路径、资产关系和配置查询都经 Tool Gateway，接受 Scope、Budget、版本和权限检查。

Agent 的 scratch / notes 只是临时工作区；正式结论必须结构化写回 CaseRevision、Claim、Evidence、Counter Evidence 或 Gap。详细见 [Agent Runtime](agent-runtime.md)。

## 10. 可信验证与反证优先

验证阶段采用可配置 VerificationPolicy，而不是固定一次“第二个模型再看一遍”。

支持的目标模式包括：
- 静态/程序证据独立复核；
- 独立 Agent；
- 双 Agent 互辩；
- 运行时 / 沙箱验证；
- 授权黑盒验证；
- 人工复核。

双 Agent 的价值是制造有组织的反证压力，而不是模型投票。Prover 尝试证明成立，Skeptic 主动寻找不可达、有效 Guard、输入不可控、环境前提等反证；新事实仍必须通过 Tool Gateway 取得。

验证方法是可组合维度；可信状态单独记录为 candidate / reviewed / corroborated / reproduced，不用 E0-E5 单线等级代替真实方法。详细见 [可信验证](verification.md)。

## 11. Coverage 与“测完”

Coverage 必须绑定明确分母。至少区分 Repository/Snapshot、Asset、Root/Source/Sink/Guard、Method、Path/Relation、Case 和 Verification Coverage，并独立记录 unsupported、failed、unknown、skipped_by_policy。

没有分母时不能输出 100%；工具失败不能记成安全；Case 数量不能代表代码覆盖率。详细见 [Coverage 模型](coverage-model.md)。

## 12. 领域对象不可混淆

Repository、RepoRevision、AssetSnapshot、ScanSpec、ScanRun、Security Case、CaseRevision、Claim、Evidence、VerificationRun、Verdict、Finding 分别承担不同职责。稳定身份、不可变版本和运行实例必须分开，避免后续实现把所有状态塞进“扫描任务”或“漏洞表”。

完整不变量见 [领域模型](domain-model.md)。

## 13. Knowledge / Policy / Memory / Observability

企业级运行还需要横向支撑：
- Security Knowledge / RAG；
- Policy Engine；
- Working Memory / Case Memory；
- Model Gateway；
- Tool Registry；
- Observability / Evaluation。

RAG 只提供安全/框架上下文，不能替代目标代码 Evidence；Working Memory 不自动升级为长期知识；Policy 必须在 Tool/Model/Runner 入口强制执行，而不是靠 Prompt 自觉遵守。

详细见 [平台支撑能力](platform-support.md)。

## 14. 被审计代码是不可信输入

不仅 Maven/Gradle 脚本不可信，源码注释、README、字符串和工具输出也可能包含 Prompt Injection。Repository Content 永远是 Data，不得改变 ScanSpec、Policy、Skill 或 Tool 权限。

Agent 不直接持有业务数据库凭据；代码外发、模型 Provider、Secret redaction、网络与动态验证目标由 Policy / Model Gateway / Runner 强制控制。

详细见 [安全与信任边界](security-boundaries.md)。
