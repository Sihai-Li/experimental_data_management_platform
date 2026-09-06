# P02 本地验收记录

本阶段只实现工程基础和文件验证，不提供正式导入、授权查询或下载。未修改真实 MAT 文件，未填充业务数据库。

## 实现清单

| 内容 | 文件/入口 |
|---|---|
| FastAPI 健康检查 | backend/app/main.py；/api/health/live、/api/health/ready |
| SQLAlchemy 模型 | backend/app/models.py；含项目、身份和六个数据实体 |
| Alembic 首次迁移 | backend/migrations/versions/0001_initial_recording_and_project_schema.py |
| 只读 MAT 验证器 | python -m app.mat_validator（PYTHONPATH=backend） |
| React 状态页面 | frontend；http://127.0.0.1:5173 |
| 完整依赖锁 | backend/requirements.lock、frontend/package-lock.json |
| 开发启动 | compose.yaml、scripts/dev-postgres.ps1、README.md |
| 基础 CI | .github/workflows/ci.yml |

## 实测环境和结果

Windows；Python 3.12.10、PostgreSQL 17.11、Node 24.19.0。FastAPI 0.141.1、SQLAlchemy 2.0.52、Alembic 1.19.2、SciPy 1.18.1、React 19.2.8、Vite 8.2.2；完整传递依赖见锁文件。

- 33 项 pytest 测试通过，无跳过、无警告；包含三个真实样例和实际 PostgreSQL 集成测试。
- 独立空测试库执行 upgrade → 模型差异检查 → downgrade → upgrade；测试结束清理测试表。正式业务库未使用。
- 全局 neuron_number 和 SHA-256 重复分别触发预期唯一约束，不依赖其他唯一键冲突间接通过测试。
- animal/session 组合唯一、孤立外键、跨项目 source/recording 关联、match 一致性、非法 Membership 角色均拒绝。
- 两个时间字段以 double precision 写入测试记录后准确读回。
- Ruff 静态检查和格式检查通过；pip check 无损坏依赖。
- npm ci 干净安装与 TypeScript/Vite 构建通过。
- 真正启动 API 和前端；前端代理访问 PostgreSQL readiness 返回 schema_revision=0001。
- Playwright + 本机 Chrome：正常就绪、模拟 readiness 503、恢复刷新、390px 宽度无横向溢出、无 pageerror，全部通过。
- Compose v5.5.1 的 config --quiet 通过；官方 Python/Node/PostgreSQL 容器镜像已查验并锁定 digest。

## 真实样例基准

| 文件标识 | Trials | Columns | Spikes | Match |
|---|---:|---:|---:|---:|
| ADR001_1_3000 | 108 | 6001 | 44 | 54 |
| ADR004_1_3007 | 180 | 6001 | 370 | 90 |
| ELV003_1_1004 | 144 | 6001 | 4687 | 72 |

共 432 trials，2 个 animal（ADR、ELV）、3 个 session。旧文档曾误写 3 个 animal，已修正。

校验和（解析前后均相同）：

- ADR001_1_3000：efd94116b79b8211a72c878f528284dbce076017886734f052f73eeddec61cbe
- ADR004_1_3007：d1dd4ecb0c49ed8135739304f8ca72f9e9352040b3dbb0131c749f843453aec7
- ELV003_1_1004：2e9be6a284fc3255d0041a5a8979d9cd4ae9ab88b03bc7dce364fe831083d6c3

测试逐项比较源解析结果与返回对象的 metadata、raster、labels、timing，并只在临时副本中制造 match 错误。原样例不被覆盖。不存在 fake data generator；CI 使用最小格式夹具检查边界，不用于数据库填充。

## 明确未验证/未实现的部分

- 本机无 Docker Engine，完整容器构建和 Compose 启动尚未实测；已验证原生启动和 Compose 配置。
- GitHub Actions 已配置，本次尚未提交/推送，远程运行结果未知。真实数据不会上传 CI。
- OIDC 登录和 API 授权属于 P03；正式导入、数据库去重服务、查询下载属于 P04。当前数据库测试只验证约束和精度，不等同于完成导入事务。
- MATLAB v4/v7.3 未支持；展开量/文件大小/矩阵元素上限见 README。公开上传前需落实后台进程隔离和超时。
- DATA_ROOT、数据库、测试数据库和服务均为本地开发设置，不作为生产部署配置。

判定：P02 代码和本地原生环境验收已完成；容器运行与远程 CI 证据待对应环境执行，不能声称已通过。
