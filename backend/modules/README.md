# 业务模块

模块按业务数据的写入所有权划分，每个模块内部再按实际复杂度建立 domain、application 和 adapters；当前不创建空代码层。

| 目录 | 逻辑模块 | 职责 |
|---|---|---|
| repositories | M1 | Project、Repository、RepoRevision |
| preparation | M2 | 准备任务、步骤、构建诊断 |
| assets | M3 | AssetSnapshot、资产、关系、能力和质量 |
| scans | M4 | ScanPlan、ScanSpec、ScanRun |
| orchestration | M5 | 阶段依赖、推进、恢复和取消协调 |
| investigation | M6 | CaseRevision、Claim、证据和调查轨迹 |
| verification | M7 | VerificationRun、Verdict、Assurance |
| coverage | 横跨流程 | 分母、计数规则和 CoverageSnapshot |
| reporting | M8 | Finding、报告索引和报告工件 |

跨模块只能通过公开用例或契约协作，不能直接修改其他模块的数据。
