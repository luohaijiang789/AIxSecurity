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
- 待实现：模型接入、CodeQL/污点分析、独立复核、运行账本、沙箱动态证明、UI。
- 检出 `eval/exec` 不代表可利用；未检出不代表安全。语法别名与名称遮蔽暂不解析。
- 输入须为稳定快照；输出必须位于被审计目录之外。
- 配置文件为接口规划，不宣称已参与运行。

[Architecture](docs/architecture.md) · [Testing](docs/testing.md) · [Contribution](CONTRIBUTING.md) · [Security](SECURITY.md)

## Repository

[GitHub private repository](https://github.com/luohaijiang789/AIxSecurity)
