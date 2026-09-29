# 前端目录骨架

前端计划采用 Vue，构建产物由 Core 的 `frontend` 容器通过 Nginx 托管，不增加 Node 常驻容器。

```text
frontend/
├── app/              应用装配、路由和全局布局
├── features/         资产、扫描、Case、报告和周期策略页面
├── shared/           共用 UI、API 传输和基础类型
├── public/           静态资源
└── tests/            单元、组件和端到端测试
```

当前只建立目录说明，没有 Vue 工程、依赖锁、页面或模拟业务数据。前端开发在后端契约和首个审计闭环稳定后开始。
