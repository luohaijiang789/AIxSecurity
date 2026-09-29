# AIxSecurity 系统架构

状态：重建设计，业务代码待实现。详细编码规范见 [后端实施计划](backend-implementation.md)。

## 1. 目标与技术边界

Java优先，支持一个或多个代码仓的资产模型；首轮以单仓专项闭环验收。
只发现安全问题、调查补证、独立复核和报告，不自动修复目标代码。
采用Vue、FastAPI、两个Celery Worker、Beat、Redis、MySQL七容器；后端保持模块化单体，不按业务模块拆微服务。

## 2. 八个逻辑模块

| 模块 | 输入与职责 | 输出 |
|---|---|---|
| M1 资产管理 | 仓库URL/ref、项目与服务映射；固定commit | Repository、RepoRevision、准备请求 |
| M2 代码处理 | 固定版本、配置；源码镜像、基础解析、Sourcebot 快速索引、隔离构建/建库 | 源码清单、搜索索引能力、工具产物、构建诊断 |
| M3 安全资产 | 归一化Entry/Source/Sink/Guard与关系、质量检查 | 不可变AssetSnapshot、集合快照、能力清单 |
| M4 扫描计划 | 人工或授权周期策略选择READY版本、专项/方法、范围、预算 | 不可变ScanSpec、ScanRun |
| M5 编排与查询 | 按计划拆分方法/Case任务；通过 Query Service 统一访问 Sourcebot、程序分析、资产关系与源码 | 子任务、证据引用、覆盖与缺口 |
| M6 Case调查 | Profile、触发线索与程序事实；模型调查和反证 | Case版本、支持/反证、调查轨迹 |
| M7 独立验证 | 原始证据、Case版本与验证规则 | 版本绑定Verdict、理由与限制 |
| M8 报告 | 有效裁决、证据、运行与覆盖状态 | Finding、JSON/Markdown、报告索引 |

公共任务与定时能力只触发/执行这些用例，不另造一套业务规则。Agent没有直接写最终裁决或扩大范围的权力。

## 3. 三条流程

### 自动准备
登记 → 固定commit → 源码镜像 → Sourcebot 索引/探测 + 无构建基础解析 → 隔离构建/增强提取 → 资产归一化 → 质量/能力门禁 → 发布READY → 结束。
必需步骤失败保留诊断，不降级伪装READY。新版本失败不覆盖旧快照。

### 人工审计
选READY版本 → 选择Plan/Profile/方法/范围/预算 → 后端再次校验 → 固定ScanSpec → 多方法候选 → Case调查 → 独立复核 → 报告。
候选不是漏洞，模型赞同不是程序证明，未调查不是安全。

### 周期自动化
用户启用版本化策略 → Beat tick → 校验授权/预算/重叠 → 创建幂等周期实例 → 进入准备或审计。
定时拉仓与定时审计独立开关；只有显式refresh_then_scan策略才在准备完成后自动审计。每次运行冻结具体版本。

## 4. 代码与数据边界

入口 → 应用用例 → 领域规则；适配器实现端口，composition装配。API/CLI/Celery复用业务包。
MySQL保存业务事实，Redis只传消息；任务与outbox同事务，提交结果检查attempt/token与资源版本。
程序库、源码和大型证据存在工件存储；MySQL保存索引/哈希。Sourcebot 作为 Code Intelligence / Fast Search Layer 负责跨仓快速搜索、源码读取和 Definition/Reference 导航；CodeQL/程序分析负责精确程序路径与数据流；二者都不替代业务安全资产库。详见 [Sourcebot 集成设计](sourcebot-integration.md)。
单仓快照与多仓集合不可变；多个commit不自动代表同一次生产部署。未解析远端边明确作为缺口。
Case/证据变更使旧裁决失效；报告只能引用匹配的有效裁决。

## 5. 部署与已知取舍

frontend只经API访问数据；API不执行长扫描；prepare/analysis与audit/maintenance分两个Worker。
backend内部relay简化部署，但API全停会暂停后续outbox投递；恢复后继续。需要更强独立性时再拆dispatcher。
长任务与维护任务可能竞争执行槽位，应测排队时延；七容器不是高可用或实时保证。
构建在受控Runner中进行，不给第三方脚本数据库/模型凭据。Runner未验收时构建blocked，不在宿主执行。
工件共享卷首版限定单机。更多隔离/授权和扩展门禁见 [部署设计](deployment-storage.md)。

## 6. 实施入口

唯一工单顺序见 [B0—B8后端计划](backend-implementation.md)。先契约和基础设施，再准备闭环、Case/复核/报告、定时与整体联调，最后扩分析能力。
前端后置。每个工单必须包含真实验证和失败路径；不以目录存在、Compose可解析或mock成功代替完成。
