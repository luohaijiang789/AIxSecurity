# AIxSecurity

面向 Java 代码仓的 AI 辅助白盒安全审计系统：**发现问题 → 补充证据 → 独立复核 → 报告，不修改目标代码。**

当前开发版本 **0.8.0**：已实现Java/Maven + SQLi、命令注入、路径穿越专项切片；不等于完整多语言、多方法或跨服务审计产品。实际验收状态见 [实施计划](docs/plan.md)。

## 核心架构：两个入口、两套任务

```text
资产管理中心
  登记一个/多个仓库 → 自动拉取并固定 commit → 隔离编译
  → 静态提取接口 / Source / Sink / Guard / SQLi 候选
  → 保存工具版本、源码哈希与分析结果 → 发布 READY 资产版本
                            ↓ 等待人工选择，不自动扫描
扫描工作台
  人选 READY 项目与支持的计划 → 固定资产版本 → 排入 scan 任务
  → 程序证据 → Agent 申请受控源码读取并判断
  → 独立上下文复核 → JSON / Markdown 报告（含覆盖缺口）
```

八模块保留为产品架构，不拆成八个微服务，也不以一个脚本替代资产平台。
Sourcebot 可用于检索，CodeQL 可用于程序分析；当前实现使用 Semgrep CE 和 SQLite 版本化准备结果，**没有冒充 CodeQL 数据库或全程序数据流**。

| 模块 | 当前实现 | 后续重点 |
|---|---|---|
| M1 资产管理 | Web/CLI 登记、任务状态、失败重试 | 更新与版本选择、权限 |
| M2 代码处理 | GitHub HTTPS、固定 commit、Docker Maven compile | Gradle、构建配置、取消/心跳 |
| M3 安全资产 | Java AST 观察、源码哈希、准备快照、READY 门禁 | 规范化资产库、调用关系、质量覆盖 |
| M4 扫描计划 | 人工选择 READY 和专项，版本/能力门禁，持久 scan | 广泛/深度/专项的真实能力组合 |
| M5 分析 | Semgrep CE 三类 taint 候选 | 跨方法数据流、Source/Sink 多方法互证 |
| M6 调查 | 有预算模型调用、受控源码读、过程记录 | 多轮补证、正式 Case 生命周期 |
| M7 复核 | 不共享初判的独立上下文复核 | 程序路径证明、版本失效、不同模型复评 |
| M8 报告 | 结构化结果与 Markdown 导出、未覆盖范围 | 效果基线、历史差异 |

## 界面模块

- **项目总览**：真实资产、准备任务、审计任务和需关注状态。
- **资产中心**：登记仓库、查看固定版本、显式重新准备；旧READY在新准备期间仍可用。
- **扫描工作台**：按该版本真实能力选择SQL注入、命令注入或路径穿越专项。
- **审计报告**：按任务查看复核、覆盖缺口、折叠证据与下载。
- **能力目录**：后端实际注册的专项与资产能力要求，不展示虚假可用模式。

旧SQLi资产不会自动获得新能力，需重新准备。每个扫描固定项目、Profile与预览的资产版本；版本变化会提示重新选择。新规则是单函数候选分析，不代表跨方法完整数据流。

## 代码组织

```text
src/aixsecurity/
  domain/          领域规则与不可变契约，不依赖数据库/网络
  application/     用例、端口、确定性报告排版
  adapters/        SQLite、任务、工件、Git/Java、模型与执行器
  entrypoints/     CLI、回环 HTTP API、静态 Web 界面
  rules/           本地 Java 资产与 SQLi taint 规则
  composition.py   实例装配与连接生命周期
```

依赖方向由架构测试约束：入口 → 应用 → 领域；适配器实现端口。导入模块不自动联网或建库。

## 启动

Python 3.11+；真实资产准备另需 Git、运行中的 Docker、`maven:3.9-eclipse-temurin-17` 镜像和独立安装的 Semgrep。
模型配置沿用本地 `.env`（参考 `.env.example`，权限 0600）；不提交密钥。

```sh
make check
make test
python3 -m pip install -e .
aixsecurity doctor
aixsecurity model-check --env-file .env
aixsecurity serve --semgrep /absolute/path/to/semgrep --port 8765 --max-cases 3
```

打开 <http://127.0.0.1:8765>。在资产中心输入公开 GitHub Java/Maven 仓库 URL；准备完成后进入扫描工作台选择项目和专项并运行。首轮样本为 [OWASP BenchmarkJava](https://github.com/OWASP-Benchmark/BenchmarkJava)。不部署靶场应用。

Semgrep 可安装在独立 Python 3.11 环境，避免与主程序运行时依赖冲突。`--database` 与 `--workdir` 可指定持久目录；运行结果默认在 Git 忽略的 `runs/`。显式重试保留失败记录，按工作区/仓库/commit/构建配置隔离的 Docker volume 只缓存 Maven 依赖；清理由操作者按保留策略执行。

## 如何理解结果

- READY 表示当前准备配置成功，不表示整个仓库所有框架、路径都已覆盖。
- 当前 Semgrep CE 输出缺少完整数据流路径证明；模型支持成立仍保留 `suspicious`，不升级为已证实漏洞。
- 默认调查前 3 个候选，最多 10 个。报告标明剩余未调查数；候选数量不等于漏洞数量。
- 独立上下文复核不等于不同模型，不能据此声称错误相互独立；没有精确率/召回率结论。
- 当前仅本机单用户；不面向公网部署。构建不挂宿主凭据，依赖下载网络开放；生产级隔离、任务取消、权限与多仓效果测试仍未完成。

## 设计与实施

- [架构设计](docs/architecture.md)：完整八模块、资产模型、生命周期和当前实现边界。
- [实施计划](docs/plan.md)：分阶段门禁、当前验收结果、下一步。
- [测试说明](docs/testing.md)：组件验证、真实 Java/模型与界面验收。
- [变更记录](CHANGELOG.md)：每轮可追溯增量。
