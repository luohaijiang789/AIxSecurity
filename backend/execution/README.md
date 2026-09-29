# 执行能力边界

这里放置业务模块调用外部执行能力的端口及适配器：`queries/`、`tool-gateway/`、`agent-runtime/` 和 `runners/`。

执行层返回结构化结果，不直接写业务 ORM。三类 Runner 不共享默认权限，也不属于 Core 七容器中的新增业务服务。
