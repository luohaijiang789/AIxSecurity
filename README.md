# AIxSecurity

面向 Java 代码仓的 AI 辅助安全审计系统：**发现问题、独立复核、交付证据报告，不自动修改目标代码。**

当前版本 **0.6.0：模块化基础框架与资产登记模块**。不是已经完成的 Java 漏洞扫描产品。

## 产品主线

```text
资产管理中心（Web 待实现）
  纳入单个/多个仓库 → 自动拉取与固定版本 → 解析/构建/建库
  → 接口、Source、Sink、Guard、数据流与关系 → 发布 READY 资产版本

扫描工作台（Web 待实现）
  人选 READY 版本和计划 → 多方法发现候选 → 统一 SecurityCase
  → Agent 查询补证/寻找反证 → 独立复核 → 可追溯报告
```

资产准备与扫描是两套任务。准备完成不自动启动扫描；同一资产版本可复用。
Sourcebot 是检索候选、CodeQL 是程序分析候选，统一资产库管理安全对象，三者不互相替代。
前置阶段不穷举所有路径，专项查询和补证在扫描时进行。八个业务模块不等于八个微服务。

## 代码如何组织

```text
src/aixsecurity/
  domain/          资产输入规则、不可变扫描选择、证据裁决规则；无数据库/网络
  application/     资产与计划用例、CatalogPort；通过接口调用基础设施
  adapters/        SQLite 目录/任务/历史账本、工件存储、本地模型代理
  entrypoints/     薄 CLI；未来 Web/API 放此边界
  composition.py   实例装配与连接生命周期；导入时不创建数据库或发请求
  cli.py           兼容既有命令入口
  doctor.py        本地环境检查
```

依赖方向：入口 → 应用 → 领域；适配器实现应用端口，装配层连接二者。
`tests/test_architecture.py` 检查反向依赖，业务规则测试使用假端口而不是强依赖 SQLite。

## 已实现与尚未实现

| 模块 | 当前能力 | 下一交付 |
|---|---|---|
| M1 资产管理 | 登记、规范校验、幂等、持久目录、准备任务原子排队、CLI 查询 | Web/API、实际 Git 接入 |
| M2 代码处理/建库 | 任务与工件基础组件 | 隔离执行、固定 commit、Java/CodeQL 适配 |
| M3 安全资产 | 不可变版本契约 | 提取器、质量校验、READY 发布 |
| M4 扫描计划 | 纯计划校验：版本、就绪、能力 | 可信快照查询、扫描工作台与持久 ScanRun |
| M5 多方法分析 | 架构定义 | Source-first、Sink-first、规则和路径查询 |
| M6 Case/调查 | 证据对象与模型传输组件 | Case 存储、受控查询、Agent 调查循环 |
| M7 独立复核 | SQLi 记录一致性与静态裁决契约 | 真实复核执行器 |
| M8 报告 | 架构定义 | 报告生成与导出 |

不创建空实现来填满表格。SQLi 契约通过只表示记录一致，不能证明真实漏洞成立。

## 本地运行

Python 3.11+。无需模型或第三方 Java 项目即可验证当前模块。

```sh
make check
make test
python3 -m pip install -e .

aixsecurity assets register --name "Java services" \
  --repo https://example.com/org/service-a.git \
  --repo https://example.com/org/service-b.git \
  --request-id registration-001
aixsecurity assets list
aixsecurity assets show PROJECT_ID
```

以上示例只保存 URL 并排入准备任务，不访问 example.com。当前尚无准备执行器，任务保持 queued，
`current_snapshot_id` 为 null；不会伪造 READY。重复请求使用同一 request-id；同键不同参数会冲突。
默认数据库在 `runs/platform.sqlite3`，可用 `assets --database PATH ...` 指定。查询以只读模式打开；缺失或非目录数据库报错，不创建空库或修改 schema。

现阶段仓库登记只接受不含凭据的公网格式 HTTPS URL；这不是拉取授权，也不提供 DNS/重定向防护。
内部 Git、凭据引用与 fetch 网络策略留待接入适配器，未来不得直接把已登记 URL 当成可执行命令。

## 模型与环境

```sh
aixsecurity doctor
aixsecurity model-check --env-file .env
```

将 `.env.example` 复制成 `.env`，设置 `chmod 600 .env`，填写本地代理配置。密钥不提交 Git。
环境变量覆盖文件配置；只支持非流式 Chat Completions，禁止自动重定向/重试。
最小测试不发送项目源码。当前观测：模型列表可用，auto 响应未通过校验，显式模型返回过 HTTP 429；
CodeQL 不在 PATH，Docker 服务未连接。`localhost` 是代理地址，不保证上游推理也在本地。

## 文档与交付

- [架构设计](docs/architecture.md)：八模块、资产模型、两套生命周期、数据契约与代码映射。
- [实施计划](docs/plan.md)：逐模块顺序、验收条件、当前状态与下一步。
- [测试说明](docs/testing.md)：当前组件验证与未来真实 Java/模型效果实验。
- [变更记录](CHANGELOG.md)：版本与历史清理记录。

CLI 是当前用例的验证入口，不替代计划中的资产管理界面和扫描工作台。
