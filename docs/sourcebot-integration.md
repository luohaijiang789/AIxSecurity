# Sourcebot 代码智能与快速检索集成设计

状态：设计基线；用于 AIxSecurity 前置代码资产准备与 Agent 调查，不表示已经完成部署或联调。

## 1. 定位

Sourcebot 在 AIxSecurity 中定位为 **Code Intelligence / Fast Search Layer（代码智能与快速检索层）**。

它负责：
- 多仓代码索引与快速文本/正则检索；
- 文件树与源码读取；
- Definition / Reference 导航；
- 分支、提交与 Diff 上下文；
- 为 Claude Code、Codex 等 Agent 提供低延迟代码上下文入口。

它不负责：
- 判断漏洞是否成立；
- 替代 CodeQL / 程序数据流分析；
- 替代 AIxSecurity 的 Entry / Source / Sink / Guard 安全资产模型；
- 替代 Security Case、Evidence、Verifier 与最终 Finding；
- 作为业务事实数据库。

因此，Sourcebot 是 **代码上下文加速器与导航底座**，不是安全扫描器。

## 2. 在主链路中的位置

```text
Repository / RepoRevision
        |
        v
M2 代码处理
  |- 固定 commit
  |- 源码镜像
  |- No-Build 基础解析
  |- Sourcebot 索引/版本可用性检查
  |- 隔离构建 / CodeQL DB
        |
        v
M3 安全资产
  |- Entry / Source / Sink / Guard
  |- Assets / Relations
  |- capability + quality
  |- AssetSnapshot
        |
      READY
        |
        v
M4 Scan Plan / ScanSpec
        |
        v
M5 Analysis Runtime / Query Service
  |- Sourcebot: search / read / nav / diff
  |- CodeQL: program/data-flow evidence
  |- Asset Graph: security semantic relations
  |- Rules / AST / framework models
        |
        v
M6 Security Case Investigation
        |
        v
M7 Verification
        |
        v
M8 Finding / Report
```

Sourcebot 的索引准备应尽量在 M2 阶段完成，并作为 AssetSnapshot 的一项可声明能力发布。扫描执行阶段复用已有索引，不为每个 Case 重复克隆和全仓 grep。

## 3. 为什么需要它

AIxSecurity 面向一个或多个 Java 微服务代码仓。Agent 若直接依赖本地 `grep/ripgrep`：
- 每个调查任务都会重复扫描文件系统；
- 跨仓搜索成本高；
- Definition / Reference 需要重新建立符号上下文；
- Agent 容易重复读取大量无关代码；
- 多个专项扫描无法复用代码搜索准备成本。

Sourcebot 以 Zoekt 为搜索后端，适合承担长生命周期、多仓复用的代码检索索引。一次准备，多次 Plan/Profile/Case 复用。

## 4. Sourcebot 能力映射

当前集成优先使用 Sourcebot 公共 API 或由 AIxSecurity 自己包装的适配器。Sourcebot 自带 MCP 可作为可选接入方式，但不是系统必需依赖。

| AIxSecurity 能力 | Sourcebot 对应能力 | 用途 |
|---|---|---|
| search_code | /api/search / grep | 正则、文本、语言、repo 范围快速检索 |
| read_file | /api/source / read_file | 固定 ref 源码读取 |
| list_tree | file tree / list_tree | 目录和文件结构探索 |
| find_definitions | /api/find_definitions | 符号定义导航 |
| find_references | /api/find_references | 引用导航 |
| list_repos | repository API | 多仓可见性与索引状态 |
| list_branches | branches | 分支与 head commit 上下文 |
| list_commits | commits | 调查历史变化 |
| get_diff | diff | 变更扫描与提交差异 |

Sourcebot 自带 Ask Agent、Skills、MCP Server 可作为辅助能力；AIxSecurity 核心 Agent Runtime 仍由自己的 ScanSpec、Skill/Profile、Tool Gateway 和 Evidence Writer 控制。

## 5. Tool Gateway

Agent 不直接依赖 Sourcebot 私有实现。M5 通过统一工具接口访问：

```text
search_code(query, repos, ref, path, language, limit)
glob_files(pattern, repos, ref, path, limit)
read_file(repo, ref, path, offset, limit)
list_tree(repo, ref, path, depth)
find_definitions(repo, ref, symbol, context)
find_references(repo, ref, symbol, context)
list_commits(repo, ref, filters)
get_diff(repo, base_ref, head_ref)
```

适配器内部可以调用 Sourcebot REST API；若未来启用其 MCP，也只作为 Tool Adapter，不改变领域模型。

所有工具返回必须被 AIxSecurity 再包装为统一 Query Result：

```text
QueryResult {
  provider: "sourcebot"
  capability
  repo_id
  requested_ref
  resolved_commit
  path
  line_range
  content_digest / blob_id (若可得)
  provider_index_version / generation (若可得)
  precision
  retrieved_at
  raw_artifact_ref (必要时)
}
```

## 6. 固定版本与证据一致性

这是集成的硬约束。

AIxSecurity 的 ScanSpec 绑定固定 RepoRevision / AssetSnapshot。Sourcebot 默认分支搜索结果不能直接作为该固定版本的证据。

规则：

1. 所有扫描期 Sourcebot 查询必须显式携带目标 ref，优先使用固定 commit SHA。
2. Adapter 必须记录 `requested_ref` 与实际解析出的 `resolved_commit`。
3. 若 Sourcebot 当前索引无法搜索该 commit，禁止静默回退到默认分支。
4. 可采用以下策略之一：
   - 为被审计版本建立可索引 revision；
   - 使用固定 revision 的 Sourcebot 索引；
   - 对该查询回退到 AIxSecurity 固定源码镜像 + ripgrep；
   - 对需要精确程序事实的问题回退 CodeQL / Program Query。
5. `/api/source` 能读取任意可解析 revision 时，可用于固定版本源码取证；搜索与导航能力仍要单独声明其版本可用性。
6. 证据写回时绑定 repo + commit + path + line + digest；无法证明版本一致时只能作为线索，不作为强证据。

## 7. Snapshot Capability 模型

M3 不把“Sourcebot 已部署”当成能力成立，而记录实际可用能力。

建议 capability：

```text
code_search.text
code_search.regex
code_search.cross_repo
code_search.fixed_revision
code_nav.definition
code_nav.references
code_browse.file_tree
code_browse.source_at_revision
code_history.commits
code_history.diff
```

状态仍采用：
- supported
- partial
- unsupported
- failed

Plan/Profile 可声明 required capabilities。缺少必要能力时 M4 拒绝启动或要求重新准备，不让 Agent 运行中偷偷降级。

## 8. M2 准备流水建议

```text
1. resolve_repository
2. resolve_commit
3. mirror_source
4. inventory_files
5. sourcebot_sync_or_register
6. sourcebot_index
7. sourcebot_probe
8. no_build_extract
9. build / codeql_prepare
10. normalize_assets
11. publish_capabilities
12. publish_snapshot
```

可并行部分：
- Sourcebot 索引
- No-Build 语法/注解/配置提取
- 依赖清单提取

构建/CodeQL 可在隔离 Runner 中独立推进。

Sourcebot 失败不应自动伪装成功。是否阻止 READY 由当前准备 Profile 和后续 Scan Plan 所需能力决定。

## 9. 对 Agent 调查效率的影响

目标不是让 Agent “多一个搜索工具”，而是改变上下文获取方式：

```text
旧：
Agent -> shell grep -> read many files -> grep again -> manual navigation

新：
Agent -> search_code -> precise matches
      -> find_definitions / references
      -> read exact ranges
      -> trace_flow / graph query
      -> evidence
```

尤其在几百仓场景：
- 一份索引可被多个专项扫描复用；
- Agent 不需要每次从仓库根目录开始枚举；
- Cross-repo 搜索可用于补全服务调用线索；
- 代码导航减少纯文本猜测；
- 变更扫描可通过 commit / diff 快速缩小候选范围。

## 10. 与 CodeQL / Graph 的职责边界

```text
Sourcebot
  = 快速找“哪里有”

CodeQL / Program Analysis
  = 证明“程序上怎么到”

Security Asset Graph
  = 组织“它在业务/安全模型里是什么关系”

Agent
  = 分析“这些事实在当前漏洞语义下意味着什么”
```

例如 SQLi：

```text
Sourcebot: 找 executeQuery / createNativeQuery / 字符串拼接候选
   |
   v
Asset Model: 映射 Sink / Entry / Source / Guard
   |
   v
CodeQL: 请求 source -> sink 的精确数据流或调用路径
   |
   v
Agent: 检查 ORM 语义、参数化、过滤条件、反证
   |
   v
Case / Evidence / Verifier
```

## 11. 部署策略

Sourcebot 当前官方部署自身需要 Postgres、Redis 和持久化索引数据。AIxSecurity 业务库仍是 MySQL，两者不要混成一套数据库语义。

推荐分层：

```text
AIxSecurity Core
  frontend
  api
  celery-process
  celery-worker
  beat
  mysql
  redis

Analysis / Tool Services
  sourcebot
  sourcebot-postgres
  sourcebot-redis (可独立，也可在验证隔离后使用独立逻辑实例)
  runner / codeql tooling
```

因此“七容器”应理解为 **AIxSecurity Core 七容器**，不是启用全部分析工具后的总容器数。

本地/测试可通过 Compose profile 启用 Sourcebot；生产可部署成独立服务，由 AIxSecurity 使用内部 API 访问。

## 12. 容量与性能基线

Sourcebot 当前官方 sizing 建议把内存视为搜索性能最敏感资源，并建议磁盘至少按源码总量约 2-3 倍预留；多分支索引会显著增加空间。

这些值只作为初始容量参考。AIxSecurity 在正式接入前需要用真实 Java 仓做：
- 首次索引耗时；
- 增量刷新耗时；
- 10/50/100/500 仓搜索 P50/P95；
- 固定 revision 查询正确性；
- 内存、CPU、索引磁盘；
- Agent 每 Case 搜索调用次数与 Token/时间节省；
- 与本地 ripgrep 的基线对照。

## 13. 许可与可替换性

Sourcebot 的 Ask/MCP/部分企业能力存在许可边界，因此 AIxSecurity 不将这些能力作为核心架构前提。

核心依赖只绑定在自己的 `CodeSearchPort` / `CodeNavigationPort` 契约：
- Sourcebot 是首选实现；
- ripgrep/local git 可作为固定源码回退；
- 后续可替换其他代码搜索服务。

这样可以获得 Sourcebot 的高性能索引能力，同时保持 AIxSecurity 的 Agent、权限、证据和安全分析主链路独立。
