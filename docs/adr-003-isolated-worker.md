# ADR 003 — 单文件受信任分析 worker

状态：Accepted / 0.4.0 / AXS-005

## 决策
CLI 注入 IsolatedPythonAnalyzer；application 只依赖 Analyzer 和 WorkerFailure 端口。
每个文件启动一个 Python `-I` 进程，受信任脚本只导入本项目分析器。请求由 stdin JSON
传递源码和证据定位，响应由 stdout JSON 返回候选。目标文件只作为 AST 数据，绝不 import。
父进程校验响应字段、源哈希/路径、行号、候选状态和指纹，未知协议视为文件分析失败。

subprocess.run 的 timeout 到期后杀死并等待子进程，释放管道。失败记录为 WorkerTimeout、
WorkerCrash、WorkerStartError 或 WorkerProtocolError，保留源哈希；审计继续后续文件。
SyntaxError/UnicodeError/RecursionError 同样记录为该文件分析缺口。

## 配置与兼容
配置 schema 仍为 1，新增可选 worker_timeout_seconds=10（正整数）。CLI 使用该预算；
显式库调用可选择进程内分析器，因此报告增加 execution_mode。报告 schema 3 的新增字段
兼容允许额外字段的消费端。耗时边界影响超时结果，因此可复现性以分析成功且预算足够为前提。

## 非目标及代价
不是权限沙箱：没有网络/文件系统权限隔离，没有 RSS/内存硬上限。目标输入虽不执行，
AST 解析仍可能消耗内存；父进程收集响应也未设置独立输出大小限额。
预算只覆盖单文件进程通信/等待，不覆盖快照采集和整批运行；系统进程创建本身可能延迟。
子进程不设计为启动后代；当前终止不提供通用进程树清理。
一文件一进程的启动成本高于进程池，但状态隔离和故障归因更简单。池化留待性能基准后。
不新增 resume；下一步 AXS-006 需先明确检查点持久化和幂等键。

## 验收证据
tests/test_worker.py 覆盖真实 worker 与原分析器结果一致、语法失败、真实超时并检查 PID
已回收、真实异常退出、无效响应、失败继续后续、配置校验及不执行目标代码。

## 下一轮可复用任务
```text
实现 AXS-006：先阅读当前 ledger、snapshot 和 isolated adapter；定义版本化检查点与
幂等键（snapshot ID、配置摘要、分析器版本），持久化每个文件完成状态。验证强杀重启、
失败重试、输入变化拒绝旧结果以及重复恢复不重复执行；保留当前单文件 worker 隔离。
```
