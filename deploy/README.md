# Compose 部署清单（配置已编写，应用入口待实现）

本目录实现七服务部署描述，不实现 FastAPI/Vue/Celery 业务。默认启用 MySQL/Redis；`app` profile 增加另外五个服务。
当前应用镜像、Vue dist 和新 Python 入口尚不存在；`config` 通过只证明配置可解析，不代表服务已启动或审计可运行。本轮不拉镜像、不启动容器、不迁移旧数据。

## 1. 挂载表

| 宿主配置/命名卷 | 容器路径 | 使用者与权限 |
|---|---|---|
| `nginx/nginx.conf` | `/etc/nginx/nginx.conf` | frontend，只读 |
| `../frontend/dist` 或 FRONTEND_DIST | `/usr/share/nginx/html` | frontend，只读；缺目录直接报错，不自动创建空目录 |
| mysql_data | `/var/lib/mysql` | mysql，读写 |
| redis_data | `/data` | redis，读写，AOF |
| artifacts | `/var/lib/aixsecurity/artifacts` | 两个 Worker 读写；backend 只读；其余不挂载 |
| workspaces | `/var/lib/aixsecurity/work` | 仅 celery-process 读写，准备临时区 |
| beat_state | `/var/lib/aixsecurity/beat` | 仅 beat 读写，只能单活 |
| `redis/redis.conf` | `/usr/local/etc/redis/redis.conf` | redis，只读 |
| `secrets/*.txt` | `/run/secrets/<名称>` | 按服务分发，见 compose.yaml |
| tmpfs | `/tmp` | 应用临时文件，重启不保留 |

命名卷实际名称带 Compose 项目前缀，不指定宿主硬编码路径。源码、CodeQL 库、原始证据与报告放 artifacts 的版本目录；不能只留在容器可写层。
不挂载整个项目、根 `.env`、用户主目录或 Docker socket。隔离 Runner 尚未集成，`AIX_RUNNER_MODE=disabled` 必须使构建请求明确 blocked，不在 Worker 内降级执行不可信脚本。
共享 artifacts 的两个 Worker 属同一可信应用边界，不是租户级隔离；业务按快照/attempt 管理写入和不可变发布。

## 2. 网络与资源

只有 frontend 发布 `127.0.0.1:8080`，不影响已有 8765 服务。MySQL/Redis 无宿主端口，位于 internal data 网络。
Worker 通过 egress 访问允许的仓库/模型；该网络不是域名级外联白名单，Runner 网络策略另行实现。backend 与 frontend 使用 web 网络。
容器内访问数据库使用 `mysql:3306`，队列使用 `redis:6379`。模型默认 `host.docker.internal:3001/v1`；Linux 主机代理若只监听 127.0.0.1 可能不可达，须单独实测配置，不能将代理凭据开放到公网。
CPU/内存限制是初始预算，不含额外 Runner；日志轮转 10MB × 3。Worker 预取为 1，两个池各并发 2，可按模型配额和主机资源调整。

## 3. 本地配置与密钥（操作者执行，勿覆盖已有文件）

从项目根进入 `deploy`，首次复制 `.env.example` 为 `.env`，建立 `secrets` 目录。
生成三个独立随机密码文件：`mysql_root_password.txt`、`mysql_password.txt`、`redis_password.txt`；不要使用示例密码。模型密钥另存 `model_api_key.txt`，仅审计 Worker 获得。
文件不得提交 Git。Compose 文件型 secrets 是挂载，不是加密保险库；Linux 须保证容器 UID 10001 可读取对应文件且其他主机用户无权限，配置 ACL/所有权后实测，不能只假设 Compose uid/mode 会替你改宿主文件权限。
Redis 启动参数从文件读取密码；宿主 Docker 管理员仍可查看容器进程，因此宿主管理员属于可信边界。

```sh
# deploy 目录下；显式 --env-file 避免混用项目根模型 .env
docker compose --env-file .env.example -f compose.yaml config --quiet
docker compose --env-file .env.example -f compose.yaml --profile app config --quiet
# 配置 .env 和三份数据库/队列密码文件后，才启动基础设施：
docker compose --env-file .env -f compose.yaml up -d mysql redis
# 新代码、镜像、Vue产物、schema迁移和全部密钥就绪后：
docker compose --env-file .env -f compose.yaml --profile app up -d
```

MySQL 官方镜像的初始化密码/用户仅对空数据目录生效；修改文件不等于修改现有数据库密码。schema 迁移为后续独立发布步骤，不在每个 Worker 启动时并发执行。
停止用 `docker compose --env-file .env -f compose.yaml --profile app down`，不带 `-v`，保留数据卷。修改项目名会切换卷前缀，不应误认数据消失。

## 4. 新代码必须满足的入口契约

- backend 镜像包含 FastAPI、Uvicorn、Celery、Redis/MySQL 驱动与业务包；`pull_policy: never` 避免误拉不存在的同名镜像。
- API 入口 `aixsecurity.entrypoints.api.app:app`，提供 `/api/v1/health/ready`；检查数据库 schema、队列连接、relay 状态，失败返回非 2xx。
- Celery 入口 `aixsecurity.entrypoints.tasks.app:app`，显式注册 prepare/analysis/audit/maintenance 路由；不将未知任务落到无人消费的 default 队列。
- 自定义 `AIX_*_FILE` 并非框架自动支持：后续配置模块负责读取、校验和隐藏文件内容，构造连接 URL 时转义密码；Beat 导入时不强制加载 MySQL/模型配置。
- backend 生命周期启动 relay；Beat 只发送 tick，不连接 MySQL；maintenance Worker 查 MySQL 策略并生成运行。
- 新镜像预建 `/var/lib/aixsecurity/artifacts`、`work`、`beat` 并归 UID/GID 10001，确保空命名卷初始化复制正确权限。已有卷须另行验证所有权，不能用 chmod 777 凑通。
- 两个 Worker 与 Beat 尚未添加“假健康检查”；后续实现任务心跳/调度更新时间探针。Compose restart 不会因 unhealthy 自动重启，仍需运维策略。
- 前端 dist 必须来自真正 Vue 构建；Nginx healthz 只检查代理进程，另测首页资源、API及完整交互。
- 标签目前为可配置系列版本；发布前锁定经实测镜像 digest，记录平台架构和版本，不宣称目前可复现部署已验收。

参考：[Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)、[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)。
