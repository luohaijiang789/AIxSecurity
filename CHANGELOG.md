# Changelog

## 0.2.0 — 2026-09-22

### Added
- 严格配置校验及文件数、单文件/总读取预算。
- SQLite 运行账本，`runs list/show`，运行配置及错误追踪。
- 候选指纹、显式覆盖信息和项目路线图。
- Issue/PR 模板、版本一致性检查、项目交付验收流程。

### Changed
- 报告 schema 从 `1` 升为 `2`；新增 `config`、`coverage`、`fingerprint`。
- 空输入/仅不支持文件返回 `no_supported_files`，CLI 退出码为 3。
- CLI 版本与 Python 包版本使用同一来源。

### Fixed
- Ctrl-C 后账本写入失败不再掩盖中断退出码。
- JSON 报告显式使用 UTF-8，避免平台默认编码差异。

### Migration / known gaps
- 消费端应接受 schema v2 和新状态；CLI 默认会写 `runs/ledger.sqlite3`。
- 直接调用 `audit()` 仍只生成确定性报告，不创建运行记录。
- 暂无快照固化、断点恢复、进程隔离、AI、CodeQL 或动态验证。
- 本版本为工程基础迭代，不代表完整漏洞检测能力或正式生产版。

## 0.1.0 — Initial foundation
- 安装入口、模块化单体、Python AST 演示分析器、10 项测试和 CI。
- 初始工程提交：`b556149`；文档记录提交：`cd48e2b`。
