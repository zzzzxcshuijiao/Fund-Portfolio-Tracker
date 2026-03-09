"""NAV (Net Asset Value) API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.post("/refresh")
async def refresh_nav(smart: bool = True, db: Session = Depends(get_db)):
    """手动触发所有持仓基金的净值更新。

    Args:
        smart: 是否使用智能模式（默认 True）。
            - True: 先获取最新交易日，然后后台补全缺失日期
            - False: 只获取最新一条净值
    """
    from backend.services.nav_service import NavService
    if smart:
        result = await NavService(db).refresh_all_nav_smart()
    else:
        result = await NavService(db).refresh_all_nav()
    return result


@router.get("/status")
def get_nav_status(db: Session = Depends(get_db)):
    """Get latest NAV update status."""
    from backend.services.nav_service import NavService
    return NavService(db).get_nav_status()


@router.post("/snapshot")
def create_snapshot(db: Session = Depends(get_db)):
    """Manually trigger today's portfolio snapshot."""
    from backend.services.snapshot_service import SnapshotService
    snapshot = SnapshotService(db).create_daily_snapshot()
    return {
        "snapshot_date": str(snapshot.snapshot_date),
        "total_market_value": float(snapshot.total_market_value),
        "portfolio_nav": float(snapshot.portfolio_nav) if snapshot.portfolio_nav else None,
    }


@router.post("/backfill-history")
async def backfill_nav_history(db: Session = Depends(get_db)):
    """Backfill historical NAV data for all held funds since first import date."""
    from backend.services.nav_service import NavService
    return await NavService(db).backfill_history()


@router.post("/backfill-snapshots")
def backfill_snapshots(db: Session = Depends(get_db)):
    """Create historical snapshots from import records."""
    from backend.services.snapshot_service import SnapshotService
    created = SnapshotService(db).backfill_historical_snapshots()
    return {"created": created}


@router.post("/backfill-holding-pnl")
def backfill_holding_pnl(db: Session = Depends(get_db)):
    """Backfill holding_daily_pnl for all dates with NAV data in fund_nav_history.

    Use this to fix dates where only money market fund P&L was recorded
    but other fund types were missing.
    """
    from backend.services.snapshot_service import SnapshotService
    dates_processed = SnapshotService(db).backfill_holding_daily_pnl()
    return {"dates_processed": dates_processed}


@router.post("/backfill-all-daily-snapshots")
def backfill_all_daily_snapshots(db: Session = Depends(get_db)):
    """为 fund_nav_history 中所有交易日创建或更新 portfolio_snapshots。

    使用 shares × unit_nav 计算历史市值，保证与实时快照计算方式一致。
    执行前请先调用 POST /api/nav/backfill-history 确保 NAV 数据完整。
    """
    from backend.services.snapshot_service import SnapshotService
    count = SnapshotService(db).backfill_all_daily_snapshots()
    return {"created_or_updated": count}
