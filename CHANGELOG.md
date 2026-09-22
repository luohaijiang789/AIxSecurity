# Changelog

## 0.4.0 — 2026-09-22

- AXS-005：CLI 每个文件使用独立 AST worker，默认墙钟超时 10 秒。
- 超时后终止并等待子进程回收；崩溃、启动失败、协议错误记录为 skipped，后续文件继续。
- 校验子进程返回的证据路径、哈希、字段与指纹；不执行目标代码。
- 配置新增正整数 worker_timeout_seconds；报告增加 execution_mode，schema 保持 3。
- 库调用仍支持显式注入进程内分析器；CLI 默认 subprocess。新增 8 项 worker 测试。
- 不是 OS 权限沙箱，暂无内存限制、整批超时和断点恢复。

## 0.3.0 — 2026-09-22

- AXS-004：先采集不可变字节快照，再分析；快照清单及 blob 内容寻址落盘。
- 增加采集前后文件身份/大小/时间变化检查，检测到变化则中止本次采集。
- 已完整采集但解析/编码失败的文件仍保留 SHA256。
- 报告 schema 升为 3：新增 snapshot，manifest 表示已采集文件而非成功分析文件；files_analyzed 语义不变。
- 本地新增 `.aixsecurity-snapshots/` 原始源码存储（位于报告父目录），不上传；按数据保留要求清理。
- 新增 8 项回归测试；强对抗文件系统一致性、worker 隔离及恢复仍未实现。

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
