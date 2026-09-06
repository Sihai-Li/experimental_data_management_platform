# Lab Data Platform

当前阶段：P02 工程基础。使用真实神经元 MAT 文件；原始数据不进入 Git、镜像或 CI。

已实现：只读 MAT 解析验证、PostgreSQL 模型与迁移、API 健康检查、React 开发状态页面和基础 CI。登录授权属于 P03，正式导入/查询/下载属于 P04，当前没有这些业务接口，也不向数据库填充真实数据。

## 环境与依赖

- Python 3.12；本机已验证 3.12.10。`backend/requirements.lock` 锁定完整 Python 依赖。
- Node.js 24.19.0；`frontend/package-lock.json` 锁定前端依赖，使用 `npm ci` 安装。
- PostgreSQL 17.11。Docker Compose 可选；没有 Docker 时使用本机独立 PostgreSQL 集群。
- 从仓库根目录执行下文命令。复制 `.env.example` 为 `.env`；实际密码、原始 MAT、`.local` 和虚拟环境均被 Git 忽略。

## 使用 Docker Compose

```sh
cp .env.example .env
# 开发凭据仅限本机。已有 .env 时不要覆盖。
docker compose up --build -d
```

顺序为数据库健康 → migrate 一次性任务 → API → 前端。浏览器打开 http://localhost:5173，API 文档在 http://localhost:8000/docs。端口仅绑定本机回环地址。此 Compose 是开发配置，前端使用 Vite 开发服务；生产打包在 P08 完成。

停止使用 `docker compose down`；不要添加 `-v`，否则会删除数据库卷。配置可用 `docker compose config --quiet` 检查。

当前机器无 Docker Engine：Compose 配置已静态验证，容器构建/启动尚未实测；原生开发启动及真实 PostgreSQL 已实测。

## 原生开发（Windows / PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
# 已安装 PostgreSQL 17 时：创建/启动仓库 .local 下独立集群，端口 55432。
.\scripts\dev-postgres.ps1 start
$env:DATABASE_URL = 'postgresql+psycopg://lab@127.0.0.1:55432/lab_platform_p02'
.\.venv\Scripts\alembic.exe -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

本机附带的 Node 没有全局 npm 时，可用本次安装在忽略目录的工具：在项目根目录执行 `node .local/npm/package/bin/npm-cli.js --prefix frontend ci` 和 `node .local/npm/package/bin/npm-cli.js --prefix frontend run dev`。新环境建议安装标准 Node/npm；`.local` 不随 Git 分发。

原生独立集群仅供本机开发，使用 trust 认证且只监听 127.0.0.1，不更改已有 PostgreSQL 服务。停止命令为 `.\scripts\dev-postgres.ps1 stop`。不要对现有业务数据库执行初始化或测试回退。

Linux/macOS 可用 `python3 -m venv .venv` 和 `.venv/bin/` 中的命令，数据库使用 Compose 的 `db` 服务；DATABASE_URL 与 `.env.example` 一致。健康检查 `/api/health/live` 不依赖数据库，`/api/health/ready` 要求数据库可连接且迁移为 `0001`，失败返回 503 且不泄露连接信息。

## 只读验证真实样例

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.mat_validator spatial_data_pre_training/ADR001_1_3000_SPATIAL_PRE_dorsal_raster_data.mat spatial_data_pre_training/ADR004_1_3007_SPATIAL_PRE_ventral_raster_data.mat spatial_data_pre_training/ELV003_1_1004_SPATIAL_PRE_ventral_raster_data.mat
```

标准输出为 JSON 报告；`VALID` 表示文件验证通过，**不代表已入库或已做数据库去重**。退出码 1 表示至少一份拒绝；范围外 variant 返回 SKIPPED。三个样例应为 108/180/144 trials，共 432；2 个 animal（ADR、ELV）、3 个 session。原文件字节和字段值均不修改。

当前支持 MATLAB level-5（v5/v6/v7–7.2，包括压缩元素），不支持 v4、v7.3/HDF5。初版资源上限为文件 32 MiB、展开元素总量 256 MiB、raster 1200 万元素。超限拒绝，不截断数据。当前命令用于本地受信任文件；公开上传前还需 P04/P05 的进程隔离和运行超时，资源上限不等于对恶意 MAT 的完整隔离。

## 测试与检查

```powershell
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
$env:TEST_DATABASE_URL = 'postgresql+psycopg://lab@127.0.0.1:55432/lab_platform_p02_test'
.\.venv\Scripts\python.exe -m pytest -q
node .local/npm/package/bin/npm-cli.js --prefix frontend run build
```

集成测试必须使用**独立空数据库**，会执行迁移升级、回退及重建，结束后清理测试表；发现已有表时拒绝运行。未设置 TEST_DATABASE_URL 会跳过数据库测试，不能据此声称数据库验收完成。

真实样例测试默认读取 `spatial_data_pre_training`，可用 SAMPLE_DATA_DIR 改路径；缺少私有样例会跳过。CI 运行 `pytest -m 'not samples'`，只用内存/临时目录中的小型格式夹具，不包含 fake data generator 或数据库填充器。真实样例完整性验收必须在本地另跑。

GitHub Actions 配置见 `.github/workflows/ci.yml`，运行后端静态检查、实际 PostgreSQL 迁移/约束测试、前端构建与 Compose 配置校验；未推送前不声称远程 CI 已通过。

## 设计与当前证据

- [执行计划](Lab_Data_Platform_Execution_Plan.md)
- [数据契约](docs/data-contract-v1.md)
- [数据库设计](docs/database-design-v1.md)
- [P02 验收记录](docs/p02-verification.md)

下载、上传、权限和科学分析均不由当前健康检查页面提供。后续沿用 P03/P04 安排，原始样例继续被 `.gitignore` 与 `.dockerignore` 排除。

## 浏览器 smoke 检查

先启动 API 和前端，然后在 frontend 中执行 `npm run test:smoke`。需要 Playwright Chromium（`npx playwright install chromium`），或设置 BROWSER_EXECUTABLE 为已安装的 Chrome/Edge 可执行文件绝对路径。本机使用 Chrome 验证了真实 API/数据库就绪、503 故障提示、恢复刷新、手机宽度无横向溢出和无运行时错误。

容器镜像已从官方 registry 核实并固定 digest。依赖核查来源：[Vite 环境要求](https://vite.dev/guide/)、[PostgreSQL 版本支持策略](https://www.postgresql.org/support/versioning/)、[SciPy 官方包](https://pypi.org/project/scipy/)、[FastAPI 官方包](https://pypi.org/project/fastapi/)。实际解析安装版本见锁文件。
