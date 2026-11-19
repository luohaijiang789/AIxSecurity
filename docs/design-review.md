# AIxSecurity 设计基线与决策

本文根据仓库设计文档整理，作为设计评审入口。领域定义、系统边界和交付契约以各自的主文档为准。

## 当前方案

AIxSecurity 面向企业 Java 和微服务仓库，先将固定版本的源码与分析能力整理为可复用的 Workspace，再根据明确授权进行白盒审计。当前仓库已有文档、目录骨架和 Compose 配置。前后端业务仍处于设计阶段。

| 环节 | 输入与产物 | 约束 |
|---|---|---|
| 资产准备 | 固定 commit → Workspace → AssetSnapshot | 按准备阶段要求判断 READY，记录能力、质量和缺口。准备完成后结束 |
| 计划提交 | READY 快照与用户选择 → 预览 → ScanSpec | 计划单独校验能力。执行绑定快照、范围、方法、预算和策略；运行时策略可收紧权限 |
| 静态调查 | 线索 → Case → Claims、Evidence 与 Gap | 证据可追溯到固定版本。上下文范围中的问题未经授权无法升级为扫描范围内的 Finding |
| 裁决与报告 | CaseRevision 与 EvidenceDigest → Verdict → Finding、Coverage 与 Report | 证据变化后旧裁决失效。Finding 受输出策略约束，Coverage 使用明确分母 |

系统采用模块化单体。MySQL 保存业务事实，Redis 传递任务消息，工件存储保存固定源码和分析工件。Sourcebot 提供检索与导航，CodeQL 提供程序分析能力。平台持有快照、范围、证据归属和裁决契约。

详见[系统架构](architecture/architecture.md)、[领域模型](foundation/domain-model.md)和[部署与存储](delivery/deployment-storage.md)。

## 容器与架构决策

首版采用单机 Compose。M1–M8 划分业务职责，七个 Core 服务划分运行角色。API、两组 Worker 和 Beat 共用后端包及目标镜像，由各自入口装配依赖。

| Core 服务 | 运行职责 | Compose 连接 |
|---|---|---|
| `frontend` | Nginx 托管 Vue，代理 API，提供唯一宿主 Web 端口 | `web` |
| `backend` | FastAPI 受理、查询和权限校验，内置 outbox relay | `web`、`data` |
| `celery-process` | 消费 `prepare`、`analysis`，编排资产准备与程序查询 | `data`、`egress` |
| `celery-worker` | 消费 `audit`、`maintenance`，推进案例、复核、报告及维护 | `data` |
| `beat` | 单活发送固定 tick，由 maintenance 读取到期策略 | `data` |
| `redis` | 承载 Celery 消息 | `data` |
| `mysql` | 保存业务状态、权限依据、任务租约、裁决和工件索引 | `data` |

`data` 是 Compose 内部网络。当前 Web 端口绑定宿主回环地址，`egress` 是为准备流程预留的网络连接。Sourcebot、Model Gateway 和隔离 Runner 按能力接入。Build Runner 处理不可信构建，Agent Runner 承载受控会话，Validation Runner 属于后续独立能力。首个设计切片只使用静态证据与独立复核。

### 关键调用与持久化

- **人工提交** → API 将业务任务与 outbox 事件写入同一 MySQL 事务 → relay 投递 Redis → Worker 领取 attempt 并提交结果。重投通过业务幂等键和有效 attempt 约束发布。
- **定时触发** → Beat 投递 tick → maintenance 读取并校验 MySQL 中的策略 → 满足条件时进入同一业务任务链路。
- **工件** → 两组 Worker 写工件卷，API 只读。MySQL 保存证据引用与内容摘要，Redis 消息只带任务标识和版本等必要字段。

### 取舍与交付验收

| 取舍 | 验收场景 |
|---|---|
| relay 随 API 部署，减少首版常驻服务 | API 停机后在途 Worker 可继续，新增 outbox 事件等待投递。恢复后重投且业务产物只发布一次。若以后要求 API 停机期间仍持续推进，再拆 dispatcher。 |
| 两组队列按职责共用 Worker 池 | 长步骤期间观察维护和查询延迟，验证限时、检查点和恢复。延迟超出目标时再拆 Worker。 |
| 首版采用单机工件卷 | 验证重启后的工件可读性、校验和与权限。跨主机部署以共享或对象存储为前提。 |

当前 Compose 默认包含 MySQL 和 Redis，`app` profile 补齐另外五个服务的配置。应用入口、后端镜像、Vue 构建产物和数据库迁移仍待实现。B0 校验入口契约，B1–B2 校验持久化与可靠投递，B3–B5 校验业务链路，B7 验收七容器联调和故障恢复。详细拓扑见[部署与存储](delivery/deployment-storage.md#2-七容器组织方案本轮收敛)，写入责任见[代码模块与依赖边界](architecture/module-boundaries.md)。

## 业务流程决策

| 决策 | 取舍与验收依据 |
|---|---|
| 快照按准备契约发布，计划按实际能力准入 | 同一 READY 快照可以支持基础静态评审，同时拒绝依赖缺失索引的计划。必需构建失败时保留诊断，快照停在 PARTIAL。版本不匹配的索引结果不得进入已发布工件。 |
| 首个切片采用单仓 Java 访问控制声明一致性评审 | 使用团队自有的固定版本 Spring 样本，检查纳入范围的显式路由与项目声明的访问策略是否一致。以源码和配置为证据，结论限于样本的静态契约。 |
| 分开度量分析与裁决 | 同一对象可能已完成分析且仍待裁决。只有 Gap 的对象保留在已知分母中，未完成所需方法时不计入 analyzed。 |
| 裁决按证据版本生效 | 历史报告保留生成时的证据与裁决引用。当前结果只使用与当前 CaseRevision 和 EvidenceDigest 匹配的有效裁决。 |

## 首个切片如何验收

选择一个自有、版本固定的 Spring 样本。计划分母为范围内由源码和静态配置识别出的唯一 HTTP 路由，按请求方法和规范化路由去重。样本要能独立审查以下场景。

| 样本场景 | 预期结果 |
|---|---|
| 路由声明和静态访问策略一致 | 所要求的方法完成，保留依据并记录排除 |
| 路由声明与项目规定的访问策略不一致 | 留存两处证据并交由独立复核，复核后按规则裁决 |
| 访问策略由未提供的部署配置决定 | 显示 needs_external_fact，注明缺少的事实 |
| 路由只出现在 context_scope | 可作为上下文引用，排除在分析分母和 Finding 之外 |
| 已裁决 Case 的证据发生变化 | 历史报告可查，当前结果在重新裁决前显示待复核 |

验收覆盖 [B3 至 B5](delivery/backend-implementation.md#10-后端开发工单与顺序)。先用同一固定版本验收快照，再验证计划准入和证据追溯，最后核对独立复核、Coverage 和报告。样本仓库及具体 commit 待进入该交付阶段时确定。

更细的状态和约束见[准备发布与计划准入](architecture/architecture.md#准备发布与计划准入)、[Coverage 模型](subsystems/coverage-model.md)和[裁决有效性](foundation/domain-model.md#verdict)。
