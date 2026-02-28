# Fund Portfolio Tracker

个人公募基金组合追踪系统。从「基金E账户App」导出的 Excel 导入持仓数据，自动从东方财富 API 抓取每日净值，计算组合市值与盈亏，通过 Web 界面可视化展示。

## 功能特性

- **Excel 导入** — 解析「基金E账户App」导出的持仓 Excel，自动合并/更新持仓
- **净值抓取** — 自动从东方财富 API 批量抓取基金净值（支持定时任务）
- **组合总览** — 总资产、总收益、日涨跌等关键指标一览
- **持仓管理** — 按基金、平台、账户维度查看持仓详情
- **基金详情** — 单只基金的净值走势、持仓分布、收益历史
- **分析报表** — 平台分布、基金类型分布等多维度分析
- **收益日历** — 日历视图展示每日盈亏
- **定时快照** — 每日自动记录组合市值和持仓盈亏

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12、FastAPI、SQLAlchemy 2.0、Alembic、APScheduler |
| 前端 | Vue 3 (Composition API)、Element Plus、ECharts、Vite |
| 数据库 | MySQL 8.0 |
| 数据源 | 东方财富 HTTP API |

## 项目结构

```
├── backend/
│   ├── api/            # FastAPI 路由 (thin HTTP layer)
│   ├── models/         # SQLAlchemy ORM 模型 (7 张表)
│   ├── schemas/        # Pydantic 请求/响应模型
│   ├── services/       # 业务逻辑层
│   ├── scheduler/      # APScheduler 定时任务
│   ├── config.py       # Pydantic Settings (读取 .env)
│   ├── database.py     # SQLAlchemy 引擎与会话
│   └── main.py         # FastAPI 应用入口
├── frontend/
│   └── src/
│       ├── api/        # Axios API 封装
│       ├── views/      # 7 个页面视图
│       └── router/     # Vue Router 路由
├── alembic/            # 数据库迁移
├── data/uploads/       # 上传文件存储
├── .env.example        # 环境变量示例
├── alembic.ini.example # Alembic 配置示例
├── docker-compose.yml.example  # Docker Compose 示例
├── Dockerfile          # 后端 Docker 镜像
├── frontend/Dockerfile # 前端 Docker 镜像
└── requirements.txt    # Python 依赖
```

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 18+
- MySQL 8.0

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd fund-portfolio-tracker
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 MySQL 连接信息：

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=fund_tracker
```

### 3. 配置 Alembic

```bash
cp alembic.ini.example alembic.ini
```

> `alembic/env.py` 会自动从 `.env` 读取数据库连接，`alembic.ini` 中的 `sqlalchemy.url` 会被覆盖，无需手动修改。

### 4. 启动后端

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:3000`，自动代理 `/api` 请求到后端 `:8000`。

### Docker 部署（可选）

```bash
cp docker-compose.yml.example docker-compose.yml
# 编辑 docker-compose.yml 中的环境变量，或确保 .env 文件已配置
docker compose up -d
```

- 后端：`http://localhost:8000`
- 前端：`http://localhost:3000`

## 定时任务

应用启动后，APScheduler 会在工作日自动执行以下任务：

| 时间 | 任务 |
|------|------|
| 20:00 | 抓取所有基金最新净值 |
| 22:00 | 重试缺失的净值数据 |
| 22:30 | 生成每日快照 + 持仓盈亏记录 |
| 启动时 | 回填缺失的历史净值 |

## 数据库表

| 表名 | 说明 | 唯一键 |
|------|------|--------|
| `funds` | 基金基本信息 | `fund_code` |
| `fund_holdings` | 持仓记录 | `(fund_code, platform, fund_account, trade_account)` |
| `fund_nav_history` | 基金净值历史 | `(fund_code, nav_date)` |
| `portfolio_snapshots` | 组合每日快照 | `snapshot_date` |
| `import_records` | Excel 导入记录 | `id` |
| `holding_changes` | 持仓变动记录 | `id` |
| `holding_daily_pnl` | 持仓每日盈亏 | `(holding_id, pnl_date)` |

## API

后端提供 RESTful API，启动后访问 `http://localhost:8000/docs` 查看 Swagger 文档。

## License

MIT
