# orchestration（M5）

负责把 ScanSpec 编译为持久步骤并协调阶段推进、重试、恢复和取消。只调用其他模块的公开用例，不拥有 Case 或 Verdict。
