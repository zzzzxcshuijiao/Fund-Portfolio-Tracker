# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

个人公募基金组合追踪系统。从"基金E账户App"导出的 Excel 导入持仓，自动从东方财富 API 抓取每日净值，计算组合市值与盈亏，通过 Web 界面可视化展示。

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (sync session), Alembic, APScheduler
- **Frontend**: Vue 3 (Composition API, `<script setup>`), Element Plus, ECharts, Vite
- **Database**: MySQL 8.0 (remote 192.168.224.171:3326, db: fund_tracker)
- **Data Source**: 东方财富 HTTP API (JSONP format, regex-extracted)

## Commands

```bash
# Backend
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install
cd frontend && npm run dev      # port 3000, proxies /api -> :8000
cd frontend && npm run build

# Docker
docker compose up -d            # backend :8000, frontend :3000
```

No test framework is configured. No tests exist yet.

## Architecture

### Three-Layer Backend

```
API Routers (backend/api/)     -- thin HTTP layer, request validation
    ↓
Services (backend/services/)   -- all business logic lives here
    ↓
Models (backend/models/)       -- SQLAlchemy ORM, 7 tables
```

- Services are instantiated per-request: `Service(db)` receiving a SQLAlchemy `Session`
- API routers use **lazy imports** for services (function-level `from ... import`) to avoid circular deps
- SQLAlchemy uses **sync sessions**, but FastAPI endpoints and NAV fetching are `async`
- Pydantic v2 schemas in `backend/schemas/` with `from_attributes = True`
- CORS is hardcoded to `http://localhost:3000` in `main.py` -- must edit for non-local deployments

### Key Data Flows

**Excel Import** (`POST /api/imports/upload`):
1. File saved to `data/uploads/`, SHA256 hash computed for dedup
2. `excel_parser` parses fixed-format Excel (row 5 = headers, row 6+ = data)
3. `import_service._merge_holdings()` upserts by unique key `(fund_code, platform, fund_account, trade_account)`
4. Missing holdings marked `status=0` (cleared), changes recorded in `holding_changes`
5. `_ensure_fund()` calls East Money API via `asyncio.get_event_loop().run_until_complete()` (sync context bridge -- anti-pattern, potential issue in some async environments)
6. Money market funds (`ishb=true` from API) get `fund_type="货币型"` and `latest_nav` fixed at `1.0000` permanently

**NAV Refresh** (`POST /api/nav/refresh` or scheduled):
1. Fetches all active fund codes, batch-calls 东方财富 API (concurrency=5, interval=0.5s)
2. JSONP response parsed via regex -> MySQL `ON DUPLICATE KEY UPDATE` into `fund_nav_history`
3. Updates `funds.latest_nav`, recalculates all holding `market_value = shares * latest_nav`

**Daily Snapshot** (scheduled 22:30 weekdays):
1. Aggregates total market value into `portfolio_snapshots`
2. Records per-holding daily P&L in `holding_daily_pnl` (vs previous trading day NAV)

### Scheduled Jobs (APScheduler, weekdays only)

| Time  | Job                    |
|-------|------------------------|
| 20:00 | Refresh all fund NAVs  |
| 22:00 | Retry missing NAVs     |
| 22:30 | Daily snapshot + P&L   |
| Start | Backfill missing NAVs  |

### Frontend Structure

- No state management library (no Vuex/Pinia) -- each view manages its own data
- `frontend/src/api/index.js` centralizes all API calls via axios
- Axios interceptor auto-unwraps `response.data` and shows `ElMessage.error` on failure
- 7 views: Dashboard, Holdings, FundDetail, Import, Analysis, Calendar, Settings
- **Color convention**: red for profit (`#f56c6c`), green for loss (`#67c23a`) -- Chinese market style
- Calendar endpoints are under `/api/analysis/calendar`, not a separate router

## Database

### Tables (7)

| Table | Unique Key |
|-------|------------|
| `funds` | `fund_code` |
| `fund_holdings` | `(fund_code, platform, fund_account, trade_account)` |
| `fund_nav_history` | `(fund_code, nav_date)` |
| `portfolio_snapshots` | `snapshot_date` |
| `import_records` | `id` (PK) |
| `holding_changes` | `id` (PK) |
| `holding_daily_pnl` | `(holding_id, pnl_date)` |

### Key Field Values

- `fund_holdings.status`: `1` = active (持有), `0` = cleared (已清仓)
- `holding_changes.change_type`: `"new"` / `"increase"` / `"decrease"` / `"clear"`
- `funds.fund_type`: `"货币型"` for money market funds (their `latest_nav` is permanently `1.0000`; East Money returns 万份收益, not unit NAV)

### Market Value Calculation

Dashboard computes real-time market value as `shares * fund.latest_nav` (not stored `holding.market_value`). The stored `market_value` column reflects values at import time.

### Migration Notes

- Alembic manages schema in `alembic/versions/`
- `main.py` also calls `Base.metadata.create_all()` at startup (parallel with Alembic)
- MySQL dialect: use `mysql_insert().on_duplicate_key_update()` for upserts
- MySQL doesn't support `NULLS LAST` -- use `case((col.is_(None), 1), else_=0)` instead

## Conventions

- **API responses**: all `snake_case` field names
- **Backend files**: `snake_case.py`; **Frontend files**: `PascalCase.vue`
- **DB tables**: `snake_case`, plural names
- **No foreign keys** between tables -- relations via `fund_code` column matching
- **No ORM relationships** defined -- all joins are manual in service queries
- **Mixed query styles**: most services use SQLAlchemy 2.0 `select()`, but `calendar_service.py` uses legacy `db.query()`
- Frontend JS uses `camelCase` vars but keeps API data in original `snake_case`

## Known Issues

- `formatNum()` / `pnlClass()` duplicated across 5+ Vue views (should be extracted to shared utils)
- `.text-profit` / `.text-loss` CSS classes duplicated in every view
- `HoldingsTable.vue` component exists but is unused
- `pandas` in requirements.txt but never imported
- Several N+1 query patterns in `nav_service._recalculate_market_values()`, `dashboard_service.get_top_holdings()`, and `snapshot_service._record_holding_daily_pnl()`
- **[P0 Bug]** Money market fund NAV in `fund_nav_history` is actually 万份收益 (per-10000-shares yield), not unit NAV -- causes wrong daily P&L in calendar view
- **[P0 Bug]** Daily P&L in calendar vs dashboard are inconsistent (snapshot-based vs real-time NAV-based calculations)
- **[P0 Bug]** Total market value in dashboard uses `shares * latest_nav` which can diverge from platform's value; Excel-imported `market_value` may be parsed as string type
