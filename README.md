# AIxSecurity

**AI 辅助白盒代码审计工程。** 当前交付完整、可安装和可测试的项目基础架构，以及可运行的 Python 静态审计演示闭环。AI 模型、CodeQL 和动态验证尚未接入；演示命中只是候选，不是已确认漏洞。

## Quick start

Python 3.11+，运行内核无第三方依赖：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
aixsecurity audit examples/demo --output runs/demo.json
python -m unittest discover -s tests -v
```

无需安装也可使用 `make test` 和 `make demo`。报告包含分析器版本、源文件哈希、候选位置、跳过文件与覆盖状态；不执行目标代码。

## Structure

```text
src/aixsecurity/
  cli.py                CLI 输入与退出码
  domain/               Finding/证据对象
  application/          审计流程与原子报告输出
  adapters/             Python AST 示例分析器
  ports.py              Analyzer / HypothesisProvider 接口
tests/                  单元和集成测试
examples/demo/          合成代码样本
configs/                默认配置说明
docs/                  架构、ADR、测试与路线图
.github/workflows/      CI
pyproject.toml          安装与命令入口
Dockerfile              非 root 容器运行配方
```

## 当前状态

- 已实现：CLI、语法规则演示、文件哈希、大小限制、符号链接过滤、部分失败报告、原子写入、离线测试。
- 待实现：模型接入、CodeQL/污点分析、独立复核、沙箱动态证明、UI。
- 检出 `eval/exec` 不代表可利用；未检出不代表安全。语法别名与名称遮蔽暂不解析。
- 输入须为稳定快照；输出必须位于被审计目录之外。
- 配置通过 `--config configs/default.json` 加载，未知字段、重复字段和无效类型会报错。
- CLI 默认将运行记录保存在 `runs/ledger.sqlite3`；可用 `--ledger` 指定路径，必须位于目标目录外。

[Architecture](docs/architecture.md) · [Testing](docs/testing.md) · [Contribution](CONTRIBUTING.md) · [Security](SECURITY.md)

## Repository

[GitHub private repository](https://github.com/luohaijiang789/AIxSecurity)

## 第一轮工程迭代

已加入严格配置、SQLite 运行账本、确定性候选指纹及显式覆盖信息。报告升级为 schema v2；空扫描返回 `no_supported_files`（退出码 3），不再视为成功。

```sh
PYTHONPATH=src python3 -m aixsecurity audit examples/demo --output runs/demo.json --config configs/default.json
PYTHONPATH=src python3 -m aixsecurity runs list
PYTHONPATH=src python3 -m aixsecurity runs show RUN_ID
```

`runs show` 包含生效配置、时间、结果及错误。报告不包含时间和运行 ID，同一输入/配置产生相同报告。`completed` 只表示所选 Python 分析范围完成，不表示整个仓库安全。

[迭代设计与下一步](docs/iteration-1.md)

## 项目迭代与追溯

当前工程版本 **0.4.0**。[路线图与验收台账](docs/roadmap.md)记录优化项、依赖和完成标准；[变更日志](CHANGELOG.md)记录版本差异与迁移说明。提交关联 AXS 编号，CI 验证安装、测试和 CLI。

发布前执行 `python3 scripts/check_project.py`、`make test` 与 `make demo`。

## 内容寻址快照（AXS-004）

分析器只使用采集完成后的不可变字节，不重新读取目标文件。报告 schema v3 的
`snapshot.id` 是规范化采集清单的 SHA256；`manifest` 包含成功采集的文件，包括解析失败项。
原始源码副本保存在报告父目录的 `.aixsecurity-snapshots/<id>/`，默认被 Git 忽略。
这是本地敏感数据，保留期限由项目管理；本轮没有自动清理或恢复命令。

采集会检测已读取文件的常见修改/替换，不等价于操作系统原子快照。输入仍须为稳定目录。
详见 [ADR 002](docs/adr-002-source-snapshot.md)。

## 独立分析进程（AXS-005）

CLI 默认每个文件启动一个受信任的 Python AST worker，以 `-I` 隔离 Python 导入环境。
`worker_timeout_seconds` 默认 10 秒；单文件超时、崩溃或协议错误会进入 skipped，整体
返回 partial/退出码 3，并继续后续文件。报告 `execution_mode` 区分 subprocess/in_process。
这不是权限沙箱或内存限额；直接使用库时，传入 `PythonAstAnalyzer` 仍在当前进程分析。
[执行边界与取舍](docs/adr-003-isolated-worker.md)。
