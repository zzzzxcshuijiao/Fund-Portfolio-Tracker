"""Dashboard API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.dashboard import (
    DashboardSummary,
    PlatformDistribution,
    DailyPnLPoint,
    TopHolding,
)
from backend.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
def get_summary(db: Session = Depends(get_db)):
    """Get portfolio summary: total value, daily PnL, counts."""
    return DashboardService(db).get_summary()


@router.get("/platform-distribution", response_model=list[PlatformDistribution])
def get_platform_distribution(db: Session = Depends(get_db)):
    """Get market value distribution by platform."""
    return DashboardService(db).get_platform_distribution()


@router.get("/daily-pnl", response_model=list[DailyPnLPoint])
def get_daily_pnl(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Get daily PnL trend for the past N days."""
    return DashboardService(db).get_daily_pnl(days)


@router.get("/top-holdings", response_model=list[TopHolding])
def get_top_holdings(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Get top N holdings by market value."""
    return DashboardService(db).get_top_holdings(limit)
