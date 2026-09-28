# 文档入口：唯一阅读顺序

更新：2026-09-28。代码基线 **0.8.0**。本轮暂停前端实现，先统一方法论与系统设计。

| 顺序 | 主文档 | 回答的问题 |
|---|---|---|
| 1 | [方法论](methodology.md) | 原始思路是什么？如何从资产、程序事实到 Case、复核、报告？ |
| 2 | [架构设计](architecture.md) | Vue/Python 怎么分离？八模块、进程、数据、接口如何组成？ |
| 3 | [实施计划](plan.md) | 当前有什么？先做什么？各阶段如何交付？ |
| 4 | [验收标准](testing.md) | 哪些验证过？怎样证明分离、闭环和效果？ |

## 当前与目标不要混淆

- 当前：Python 提供原生静态页面和 HTTP API，同进程后台线程执行；不是独立 Vue 工程。
- 目标：同仓 Vue 前端 + Python API + 独立 Worker，后端保持模块化单体，不拆成八个微服务。
- 核心：自动准备资产并结束 → 人工选择 READY 版本和策略 → 多方法/Agent 调查 → 独立复核 → 报告。
- 不做：自动修复目标代码；本轮不继续前端原型，不搬目录，不新增扫描代码。
- 待补：规范资产关系、正式 Case、多方法与精确路径、稳定模型闭环、多仓求解及效果实验。

[项目首页](../README.md)提供当前启动方法；[变更记录](../CHANGELOG.md)记录已交付版本。
[历史设计](archive/2026-09-28-before-realignment/README.md)仅供追溯，不作为当前实施依据。
GitHub：[项目仓库](https://github.com/luohaijiang789/AIxSecurity)、[在线文档入口](https://github.com/luohaijiang789/AIxSecurity/tree/main/docs)。

维护规则：方法变更写 methodology，组件与契约写 architecture，阶段状态写 plan，证据与验收写 testing。
不再把不同时间的“当前状态”堆叠在架构末尾，也不因界面缺少按钮就改变后端方法论。
