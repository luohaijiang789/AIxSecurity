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

## 本轮决策

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
