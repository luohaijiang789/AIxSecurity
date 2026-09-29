# 代码模块与依赖边界

当前为单一 Python 发行包；模块、进程、容器不是一一对应关系。M1—M8 是产品流程，代码包按实际写入责任组织。

## Core 七容器约束

Core 固定为 `frontend`、`backend`、`celery-process`、`celery-worker`、`beat`、`redis`、`mysql` 七个常驻容器。代码目录和业务模块不得各自增加服务。

- backend、两个 Worker 和 Beat 以后共用同一后端包与镜像，通过角色装配；
- backend 承担 API 和内部 outbox relay；
- celery-process 消费 prepare/analysis，celery-worker 消费 audit/maintenance；
- Beat 只发送固定 tick，不读取 MySQL 业务策略；
- 只有 frontend 暴露 Web 端口；Redis 仅运输消息，MySQL 保存业务事实；
- Sourcebot、Build/Agent/Validation Runner、对象存储和监控属于 Tool/Execution Services，不计入 Core，也不能改变上述模块所有权；
- Runner 尚未验收时能力必须 blocked，不能在 Worker 或宿主静默执行不可信脚本。

| 模块 | 唯一写入责任 |
|---|---|
| repositories | Project、Repository、RepoRevision |
| preparation | PreparationJob、准备步骤、构建诊断 |
| assets | AssetSnapshot、RepositorySetSnapshot、成员、资产与能力 |
| scans | ScanSpec、ScanRun、计划受理/取消 |
| orchestration | 跨阶段依赖和推进记录；通过各模块公开用例请求状态变化 |
| investigation | CaseRevision、Claim、证据关联与调查结果 |
| verification | VerificationRun、Verdict、Assurance；不直接改 Case |
| coverage | CoverageSnapshot、分母和计数规则；消费执行事实 |
| reporting | Finding、报告索引/工件；不重新裁决或计算另一套 Coverage |

所有权不等于每模块独立数据库或独立事务。跨模块原子操作在 composition 装配的用例中共享 UoW，各模块只通过公开命令参与；具体事务在对应业务切片实现。

## 依赖规则

- `modules/<name>/public.py` 是跨模块公开契约入口。没有已确定契约时，不创建空 public 接口。
- `domain.py` 或 `domain/` 只依赖标准库及本模块领域代码；领域 ID/值对象通过公开契约交换。
- 模块内部用例按实际复杂度放入 `application.py` 或 `application/`；持久化与工具适配在需要时增加。
- 跨模块禁止导入对方 domain/application/adapters，禁止直接修改对方表。
- entrypoints 做输入/身份/错误转换；composition 是具体依赖装配入口。
- platform 不依赖业务模块。任务基础只维护投递、租约与 attempt，不能决定 Case/Verdict。
- 架构测试检查静态 import；动态导入/数据库写入所有权仍需代码审查，不宣称测试覆盖全部边界。

## 执行与控制

M5/orchestration 决定下一业务阶段。M6/M7 拥有各自状态与结果提交，调用 execution 的公开端口。
Agent Runtime 只执行会话；Query Service 返回固定版本程序事实；Tool Gateway 在每次调用前执行 Policy/Scope/Budget 检查并记录轨迹。
慢工具操作通过持久任务/outbox 恢复推进，不让 Celery 父任务同步等待子任务。
execution 的 provider 实现不得反向操作业务 ORM；结构化结果交给拥有该业务数据的模块验证和写回。

三类 Runner 权限继续分离。共享卷不是租户隔离；发布工件前必须由可信应用验证 attempt、路径、完整性和引用。

## 横向支撑

platform 暂只划定 jobs/artifacts/identity/policy/model_gateway/observability 包；无真实能力时不提供返回成功的占位函数。
Case Memory 随 investigation；临时 Working Memory 随 agent_runtime；Knowledge/RAG 维持 B8 后置，不先创建另一套通用知识平台。
Coverage 独立为规则所有者，M8 负责呈现其输出，不意味着新增服务。

## 实施状态

当前只建立目录骨架和职责说明，没有应用代码、依赖、API、数据库、任务、Runner、Agent、前端页面或测试实现。
目录存在不表示 B0 已完成。B0 仍须实现并验证工程入口、角色配置、错误/DTO、实际契约和架构约束。
