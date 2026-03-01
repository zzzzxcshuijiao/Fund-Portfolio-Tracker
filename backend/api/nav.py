"""NAV (Net Asset Value) API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.post("/refresh")
async def refresh_nav(db: Session = Depends(get_db)):
    """Manually trigger NAV update for all held funds."""
    from backend.services.nav_service import NavService
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
