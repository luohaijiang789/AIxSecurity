# 后端模块设计与编码实施规范

更新：2026-09-28。状态：重建的唯一后端编码计划。旧实现已移出工作区；当前仅保留设计与部署配置，后端业务尚未实现。

本文负责“后端怎么写”；[方法论](../foundation/methodology.md)负责分析原则，[架构](../architecture/architecture.md)负责系统边界，[部署设计](deployment-storage.md)负责容器/存储；本文 B0—B8 工单负责实施与验收状态。冲突时先修正文档，不让开发者自行猜测。

## 1. 架构评审结论与约束

七容器、模块化后端适合当前单机 Java 审计平台：请求与长任务分离，工具准备与模型调查分队列，MySQL 可追溯，工件单独存储。八业务模块不拆八个微服务。

必须接受或后续解决的取舍：

1. API 内 outbox relay 简化部署，但 API 全停会暂停后续投递。恢复后继续；如需完全独立推进再拆 dispatcher。
2. 一个审计 Worker 同时消费 audit/maintenance，不保证维护任务实时。限制任务时长、记录排队时间；超出验收阈值再拆 control Worker。
3. Celery 提供执行和消息传递，不提供本产品的不可变证据、业务事务或 exactly-once。状态与去重必须在 MySQL 实现。
4. 共用工件卷适合单机，不构成跨租户隔离；不直接挂到公网静态目录。
5. Compose 当前禁用 Runner。隔离器没有通过验证前，构建/建库返回 blocked，不执行宿主脚本。
6. CodeQL/Sourcebot 仍待工具验证；Sourcebot 已确定为首选快速代码检索/导航层，但只有通过固定版本、权限、性能和结果一致性验收后才能把对应 capability 标成 supported。
7. 不追求一轮实现全量方法：先以单仓 Java 专项贯通正式模型，再补齐精确路径、多方法和多仓。

## 2. 技术选型与使用规则

以下是目标选型；精确补丁版本在 B0 做兼容测试后锁入依赖锁文件，不将网页最新版本直接视为验收版本。

| 层次 | 选用 | 原因与约束 |
|---|---|---|
| 运行时 | Python 3.12 作为重写基线候选 | 先验证 Celery/驱动/工具组合；Semgrep/CodeQL 留在工具环境，不混装全部依赖 |
| API | FastAPI + Uvicorn | 路由和 OpenAPI；请求只验证、查询、受理，不运行扫描 |
| 输入/配置 | Pydantic 2 + pydantic-settings | DTO 与分角色配置；领域对象不直接使用 HTTP DTO 或 ORM |
| 持久层 | SQLAlchemy 2 同步 Session + PyMySQL | 统一 API/Celery 同步用例，避免两套事务模型；真实 MySQL 测试 |
| 数据库演进 | Alembic + MySQL 8.4 系列 | 独立迁移步骤，不由所有 Worker 争相迁移 |
| 异步任务 | Celery + Redis broker | 显式队列、任务名、消息版本；result backend 非业务事实源 |
| 模型传输 | HTTPX 同步客户端 | 有连接/读/总预算限制；接口适配现有模型代理，密钥不进入任务消息 |
| 工件 | 文件系统 ArtifactStore 端口 | SHA256、manifest、attempt 临时区；未来换对象存储 |
| 测试与质量 | pytest；Ruff、mypy | 单测/契约/真实服务集成分层；按新契约建立测试 |

同步数据库调用使用 FastAPI 普通 `def` 路由/依赖，避免在事件循环直接执行阻塞 IO；relay 使用受管理线程或显式线程卸载。参考 [FastAPI 同步/异步说明](https://fastapi.tiangolo.com/async/)。
Session 每个用例/任务独占，事务边界由 UnitOfWork 管理，不能跨线程或 Celery fork 共享活动连接；Worker 子进程初始化连接池。[SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
Alembic 负责 schema 演进，不是运行时随意 create_all 的替代名。[Alembic 文档](https://alembic.sqlalchemy.org/en/latest/)
配置模块显式实现 `AIX_*_FILE` 读取与角色校验，不假设任意后缀都自动生效。[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

## 3. 工程目录（骨架已创建，内部代码待实现）

```text
backend/
  modules/                           M1—M8 与 Coverage，按业务所有权组织
  execution/                         Query、Tool Gateway、Agent Runtime、Runners
  platform/                          jobs、artifacts、identity、policy 等横向能力
  entrypoints/                       api、tasks、beat、cli 薄入口
  composition/                       按 api/process/audit/beat 角色装配
  migrations/                        Alembic revisions（B1 开始实现）
  tests/                             architecture/unit/contract/integration/e2e
frontend/                            Vue 目录骨架，业务后置
contracts/                           真实实现导出的 OpenAPI/消息/工件 schema
```

模块内部按实际复杂度再增加 domain/application/adapters，不预建空代码层。跨模块只通过公开用例和契约协作；composition 是唯一具体依赖装配位置。
API/任务入口只做身份上下文、反序列化、调用用例、错误映射。不在 router/task 中堆 ORM、Prompt、shell 和报告逻辑。完整规则见 [代码模块边界](../architecture/module-boundaries.md)。

## 4. 模块、接口与验收责任

以下名称是将实现的用例契约，不是已经可调用的 Python API。

| 模块 | 用例/输入 → 输出 | 写入对象 | 最小验收 |
|---|---|---|---|
| M1 资产管理 | RegisterRepository、RequestPreparation、ListRevisions；项目/URL/ref/幂等键 → 身份/准备任务 | 项目、仓库、revision、准备请求 | 重复登记不重复任务，非法输入零工具调用 |
| M2 代码处理 | PrepareRevision；固定commit/配置 → 源码清单、构建/工具工件 | 步骤/attempt、工具产物引用 | 隔离失败blocked；篡改哈希拒绝；超时可恢复 |
| M3 安全资产 | NormalizeAssets、PublishSnapshot；工具事实 → 不可变资产/质量/能力 | snapshots、assets、relations、集合成员 | 必需能力缺失不READY；多来源冲突可见 |
| M4 扫描计划 | PreviewScan、CreateScan、CancelScan；快照/Plan/Profile/范围/预算 → 固定Spec/Run | scan_specs/runs、任务/outbox | 服务端验证可信版本；漂移与越界拒绝 |
| M5 编排/查询 | AdvanceRun、DispatchMethod、QueryEvidence、StartAgentSession；Spec/步骤 → AnalysisTask/ToolResult/Candidate | jobs/steps、查询/工具轨迹、coverage增量 | Query Service/Tool Gateway 统一版本与范围；不阻塞等待Celery子任务；重复事件无重复推进 |
| M6 Case调查 | OpenCase、AppendEvidence、UpsertClaim、InvestigateCase；Case/Profile/Skill/Goal/预算 → CaseRevision | Hypothesis、Claims、支持/反证、Gap、Agent轨迹 | Agent受Scope/Tool/Budget约束；关键Claim可追溯；同证据去重；预算耗尽留下Gap |
| M7 可信验证 | VerifyCase、RunDebate、RequestDynamicValidation；revision/digest/Claims/VerificationPolicy → VerificationRun/Verdict | ClaimReview、AssuranceState、版本绑定裁决、验证工件 | 旧证据复核不能提交；必需Claim未关闭不能靠Agent投票确认；动态验证未授权即拒绝；失败不转rejected |
| M8 报告/覆盖 | GenerateReport、BuildCoverage；运行/有效裁决/明确分母 → JSON+Markdown+Coverage | CoverageSnapshot、报告manifest、Finding与索引 | Coverage有分母且unsupported/failed/unknown可下钻；下载/表格/结构化结果一致 |
| 公共任务基础 | Enqueue、Claim、Renew、Complete、Reconcile | outbox、attempt、幂等记录 | 投递丢失/重复、租约失效、取消均可验证 |
| 定时自动化 | SaveSchedule、EvaluateDue、CreateOccurrence | schedule版本/周期实例 | 显式授权、周期去重、漏跑/重叠、暂停有效 |

定时模块不是第九个漏洞分析模块，而是复用 M1/M4 入口的触发能力。查询/报告走只读端口，工具与模型由明确执行器调用。
准备阶段只产程序事实；未选扫描计划前不调用调查模型。审计可由用户当次发起或经明确批准的周期策略发起。

## 5. MySQL 最小数据契约

统一：ID 采用应用生成 UUID（首版 CHAR(36)）；UTC DATETIME(6)；摘要 CHAR(64)；显式业务外键与 project_id。
稳定身份、不可变版本、运行尝试分表。JSON 仅存扩展配置和结构化载荷，常用筛选/关联字段单列，不把所有业务塞入一个 JSON 表。

| 表组 | 核心字段/约束 |
|---|---|
| repositories / repo_revisions | project_id、规范URL、ref、commit；revision唯一(repo_id,commit) |
| preparation_jobs / job_steps | revision_id、profile_version、input_digest、state、error_code、attempt；步骤唯一(job_id,step_key) |
| task_attempts | task_id、attempt_no、token、lease_expires_at、heartbeat、checkpoint；唯一(task_id,attempt_no) |
| asset_snapshots / assets / relations / capabilities | revision/config/tool摘要、capability/quality/gap、artifact refs；发布后不可变 |
| repository_sets / snapshot_members | set_id、repo_id、snapshot_id、服务映射；唯一(set_id,repo_id) |
| scan_specs / scan_runs / coverage_snapshots | Spec不可变；plan/profile/skill引用、snapshot_refs、scope/budget/verification_policy；Run单独状态；Coverage绑定明确分母 |
| cases / case_revisions / case_claims | case_id、revision、branch、evidence_digest；Hypothesis/Claim/Gap；Claim含required/status/assumptions和支持/反证引用 |
| evidence_refs / tool_calls / agent_sessions | 工具/commit/位置/哈希/precision；Agent与Tool轨迹可追溯 |
| verification_runs / verdicts | method/claim_reviews/environment/assurance_state；裁决绑定case_revision+evidence_digest+verifier_version |
| reports / artifacts | run_id、generation、kind、digest、storage_key、size；完整文件发布后再引用 |
| idempotency_keys | actor_id、operation、key唯一；payload_digest、resource_id；同键异载荷冲突 |
| outbox_events | event_id、kind、schema_version、resource_id、payload、next_attempt_at、lease、published_at |
| schedules / revisions / occurrences | 定时策略、授权/预算/版本选择；唯一(schedule_id,revision,scheduled_for) |
| audit_events | actor/request_id、动作、资源、时间和脱敏结果；不记录原始密钥 |

M1登记、M4创建运行及下一步推进：业务数据+outbox 同一事务。工具IO/模型调用禁止占用长数据库事务。
领取使用行锁/条件更新；完成时检查 token、租约、预期版本。唯一键处理并发，不能只靠“先查有没有”。
必备索引：项目+创建时间+ID分页；任务state/next_attempt；outbox未投递/下次尝试；Case run_id/state；周期到期时间。B1 冻结具体 DDL 与删除策略。
删除项目先禁用新任务；被运行、报告或审计记录引用的版本禁止级联清空。需要导入外部数据时另行批准并核对ID及工件哈希。

## 6. 状态机和错误语义

| 维度 | 目标状态 |
|---|---|
| 准备任务 | queued → running → succeeded；分支 blocked/failed/cancel_requested/cancelled |
| 资产版本 | draft → validating → ready；分支 partial/failed；ready版本不原地覆盖 |
| 审计运行 | queued → running → completed；分支 blocked/failed/cancel_requested/cancelled |
| Case | open → investigating → ready_for_verification → reviewed |
| 裁决 | confirmed / suspicious / rejected；无裁决另记unreviewed，不混为rejected |
| 覆盖 | complete / partial / unknown，绑定明确分母 |
| 报告 | pending / generating / ready / failed，独立于扫描是否完成 |

失败后重试创建新 attempt；修改准备配置或扫描 Spec 创建新业务运行，保留原始失败。READY 与任务 succeeded 只有发布事务通过后才对应。
典型错误码：INVALID_INPUT、SNAPSHOT_NOT_READY、CAPABILITY_MISSING、VERSION_CONFLICT、IDEMPOTENCY_CONFLICT、RUNNER_UNAVAILABLE、AGENT_RUNTIME_UNAVAILABLE、TOOL_TIMEOUT、MODEL_UNAVAILABLE、BUDGET_EXHAUSTED、VERIFICATION_NOT_AUTHORIZED、STALE_ATTEMPT。
HTTP/任务/日志使用同一业务错误码，附 request_id；脱敏 details，不直接回传完整异常栈。

## 7. API 契约清单（/api/v1，待实现）

| 方法/路径 | 语义 | 成功状态 |
|---|---|---|
| POST /projects；POST /projects/{id}/repositories | 建目录、纳入仓库，仓库纳入事务触发准备 | 201目录；202纳入操作 |
| GET /projects、/projects/{id} | 列表/详情、当前与历史版本摘要 | 200 |
| POST /repositories/{id}/preparations | 显式准备/刷新 | 202 |
| GET /preparations/{id} | 步骤、诊断、工件索引、阻塞原因 | 200 |
| GET /snapshots/{id}、/snapshots/{id}/assets | 固定版本质量/能力/资产分页 | 200 |
| GET /profiles、/plans | 支持状态、版本、必要能力 | 200 |
| POST /scans/preview | 校验并返回固定版本和规范化Spec摘要 | 200，不创建任务 |
| POST /scans；GET /scans/{id} | 复核版本后创建；读取状态/覆盖 | 202；200 |
| POST /scans/{id}/cancel | 请求取消，异步确认 | 202 |
| GET /scans/{id}/cases、/cases/{id} | Case版本、支持/反证/缺口与裁决 | 200 |
| GET /reports/{id}、/reports/{id}/download | 索引与经授权下载，format白名单 | 200；未生成409 |
| POST /schedules；PATCH /schedules/{id} | 新建策略；按预期revision更新/暂停 | 201；200 |
| GET /schedules/{id}/occurrences | 实际触发/跳过/失败的周期记录 | 200 |
| GET /health/live、/health/ready | 存活；MySQL/schema/Redis/relay准备状态 | 200或503 |

创建任务要求 Idempotency-Key。列表默认50、最大200，使用(created_at,id)稳定游标；过滤字段白名单。
拒绝：422格式错误、401未认证、403资源权限不足、404不存在、409版本/幂等/状态冲突、503暂不可受理。业务资源失败不把GET状态查询变成500。
错误体统一 `{error:{code,message,details},request_id}`；受理体含 operation_id、resource_id、status_url。
预览不是授权令牌；提交时再次检查actor、snapshot、Profile与能力。ScanSpec 记录创建时 policy/data-policy revision，但执行期权限撤销和安全策略收紧必须立即生效；实际 Tool/Model/Runner 调用记录 effective policy revision。后续 OpenAPI 将提供每项成功/失败样例，而非只列路径。

## 8. Celery、消息和配置契约

| 队列 | 任务名称草案 | 消费容器 |
|---|---|---|
| prepare | prepare.fetch / prepare.build / prepare.extract / prepare.publish | celery-process |
| analysis | analysis.query / analysis.run_method | celery-process |
| audit | audit.investigate / audit.verify / audit.report | celery-worker |
| maintenance | schedules.evaluate / jobs.reconcile / artifacts.collect | celery-worker |

消息：schema_version、event_id、task_id、kind、expected_resource_revision、trace_id；JSON序列化，不传ORM/源码/密钥，不接收任意Python对象。
消息里的资源引用仍从数据库复核；未知版本拒绝并记录待处理，不静默吞掉。attempt token 在实际领取时生成。
子步骤通过完成事务/outbox 触发，不调用 Celery result.get 同步等待。不依赖 chain/chord 状态替代MySQL状态机。
配置明确 acks、worker_lost、visibility timeout、soft/hard timeout 与续租的组合；先通过故障矩阵再设生产值，不假定一个参数能保证不丢任务。

配置按 api/process/audit/beat 角色读取：Core 的 api/process/audit/beat 都不持有模型 provider 长期 key；Agent Runner / Model Gateway 单独装配模型凭据和 DataPolicy。Beat 导入任务包不能触发DB/模型连接。
Compose 入口固定为 `aixsecurity.entrypoints.api.app:app` 与 `aixsecurity.entrypoints.tasks.app:app`；导入无IO，连接在启动或任务进程初始化创建。
日志关联 request_id/run_id/task_id/attempt/case_id，正文与模型密钥脱敏；指标记录排队、outbox积压、过期租约、模型错误与维护延迟。

## 9. 身份、证据与执行边界

首轮验收可限定本机单用户，但固定 RequestContext(actor_id,project_permissions,request_id) 端口；测试身份适配器不得用于对外部署。
共享部署前实现真实身份验证与项目授权，检查每个快照、Case、报告引用；前端传project_id不等于已获权限。
授权/预算检查既在受理时也在定时触发、敏感工具读取时执行；代码注释和模型输出不能改变权限。
模型返回按schema校验，只能提出调查/判断，不能直接写裁决或SQL。复核独立上下文，提交版本条件检查。
Runner 通过端口调用受控执行器；构建超时/取消要结束对应子进程，禁止直接挂Docker socket到普通应用容器。
MySQL最小角色权限在B1设计；当前Compose共用应用账号属于单用户过渡配置，不宣传已完成组件级最小权限。

## 10. 后端开发工单与顺序

以下为唯一实施工单顺序，全部待开始。Vue 功能开发在后端契约与闭环稳定后进入。

| 工单 | 前置 | 产物 | 必须通过 |
|---|---|---|---|
| B0 工程与契约骨架 | 本文评审 | 依赖锁、目标包、角色配置、错误/DTO/领域边界、OpenAPI样例 | 冷导入无IO；Beat无需模型/DB；架构测试；Compose入口一致 |
| B1 持久与工件 | B0 | MySQL表/约束、Alembic、UoW、工件端口、数据初始化规范 | 真MySQL事务/唯一键并发；工件哈希；迁移和恢复 |
| B2 可靠任务 | B1 | outbox relay、Celery路由、attempt/取消/恢复 | 发布后崩溃重投不重复副作用；旧token拒绝；API停机恢复 |
| B3 资产纵切 | B2 | M1→M2→M3与API，BuildRunnerPort 最小适配；Sourcebot CodeSearch/Navigation 适配与能力探测 | 固定真实Java样本到READY；固定commit源码与搜索结果一致；恶意/失败构建不能逃逸Runner；索引失败/版本不匹配可见；构建失败不发布；零自动扫描 |
| B4 计划/Workspace/Case骨架 | B3 | M4/M5、Query Service、Tool Gateway、Policy骨架、Coverage骨架、Case/Claim/Evidence契约 | 真快照预览/提交；版本漂移；analysis/context scope；Sourcebot/CodeQL结果版本绑定；Claim可追溯；明确Coverage分母；多方法线索不重复加权 |
| B5 Agent调查到可信报告 | B4 | M6/M7/M8；AgentRuntimePort、ModelGatewayPort、首个Skill/Goal、STATIC_PROGRAM_REVIEW + INDEPENDENT_AGENT，先单一Java专项 | Claude/Codex适配可替换；受控补证和反证；关键Claim关闭规则；源码Prompt Injection不能改Policy/Tool权限；DataPolicy拒绝可验证；旧证据Verdict失效；模型故障；Assurance/Coverage/报告一致 |
| B6 定时自动化 | B2且对应业务切片可用 | schedule策略/tick/occurrence、维护 | 时区/重叠/漏跑/停用/授权撤销；定时与手动共用用例 |
| B7 打包与完整后端验收 | B3—B6 | 镜像、schema发布步骤、七容器联调、运维记录 | 外部依赖真实连接、重启恢复、工件权限、历史保留、真实闭环 |
| B8 增强方法与验证 | B7 | 精确程序路径、更多Profile/Skill、Knowledge/RAG、多仓、ADVERSARIAL_DEBATE、经授权RUNTIME_SANDBOX / AUTHORIZED_BLACKBOX | 每项能力独立正反例；互辩不能靠投票；RAG不能替代代码证据；动态验证隔离/白名单/审计；真实效果、Coverage与成本验收 |

完成定义：业务规则单测 + API/消息契约 + 真实依赖集成 + 错误路径 + 文档同步 + Git可追溯。mock通过不等于MySQL/Celery/模型联调通过。
首个可运行后端里程碑是 B3；首个完整审计后端里程碑是 B7，不能把空路由/启动健康检查算整套完成。

## 11. 当前状态与后续编码提示

当前没有应用代码、ORM、路由、测试或已构建应用镜像。Compose只完成配置验证；MySQL/Celery运行和真实审计均待实施验收。
下一轮先执行 B0，随后 B1；每个工单评审后再推进，不并发推倒重写所有模块。

```text
实施 AIxSecurity 后端工单 B<n>。先读 docs/delivery/backend-implementation.md 与对应方法论/部署契约，检查真实代码和未提交改动。
只做该工单，保留八业务模块和人工/授权定时入口；MySQL为业务事实，Celery为执行，固定快照、Claim/Evidence责任链与可信验证不变。
先写输入输出/错误与验收测试，再实现领域、用例、适配器和薄入口；不把业务逻辑塞进FastAPI路由或Celery task。
记录本轮真实执行、未验证项和迁移回退；只有验收通过才更新工单状态。不得把配置可解析或mock成功写成系统闭环成功。
```

## 12. 初始化与发布要求

后续bootstrap按：环境与配置校验 → 镜像/挂载检查 → MySQL/Redis健康等待 → 单次Alembic迁移 → 幂等Plan/Profile种子 → 权限检查 → API/Worker/Beat启动 → 队列与工件自检。
迁移失败必须非零退出，不打印成功；必须有初始revision并验证关键表，不能用create_all或固定sleep假装就绪。
重复初始化不覆盖密钥、不清数据、不重复种子；每个注册任务对应实际消费队列；不同容器的读写路径和运行UID必须实测。
B0定义bootstrap契约，B1实现迁移与种子，B2实现队列自检，B7验证空环境、重复执行及故障恢复。


## 13. Agent / Runner 实施边界

后端实现必须区分三类执行器：

- **BuildRunnerPort**：运行 Maven/Gradle、CodeQL 建库等不可信项目操作；无业务数据库和模型长期凭据。
- **AgentRuntimePort**：启动 Claude Code/Codex 等隔离调查会话；输入 AgentTask，工具能力来自 Tool Gateway，默认不运行目标构建脚本；Repository Content 只作为不可信数据，不能改变 Policy/Scope/Tool 权限。
- **ValidationRunnerPort**：仅在 VerificationPolicy 显式允许时进行运行时/黑盒验证，绑定目标白名单、速率、凭据和非破坏策略。

三类执行器不共享默认权限。celery-process / celery-worker 是编排进程，不等于 Runner 本身。模型调用统一通过 ModelGatewayPort 应用 provider、数据外发、Secret redaction、预算和审计策略。完整边界见 [security-boundaries.md](../architecture/security-boundaries.md)。

## 14. 领域与 Coverage 契约

领域对象和不变量以 [domain-model.md](../foundation/domain-model.md) 为准；Coverage 以 [coverage-model.md](../subsystems/coverage-model.md) 为准；Knowledge/Policy/Memory/Observability 以 [platform-support.md](../subsystems/platform-support.md) 为准。实现时禁止用一个通用 scan_task 表或 vulnerability 表包揽 Snapshot、Run、Case、Verdict、Finding 和 Coverage。

首个闭环就必须能解释：
- 当前固定的 repo/commit/snapshot；
- 当前 ScanSpec 的 Scope/Profile/Plan；
- Candidate 如何进入 Case；
- 漏洞成立条件如何拆成 Claims；
- Evidence 和 Counter Evidence 分别支持/反驳哪些 Claim；
- Verdict 绑定哪个 CaseRevision/EvidenceDigest；
- Coverage 的分母和缺口是什么。
