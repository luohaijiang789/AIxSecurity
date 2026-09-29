# Composition

唯一依赖装配位置。以后按 `api`、`process`、`audit`、`beat` 四种角色装配同一后端包，确保 Beat 不加载数据库或模型配置，Core 不接收模型长期密钥。
