"""Analysis API endpoints - period PnL analysis."""

from datetime import date

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.holding_daily_pnl import (
    PeriodItem,
    FundPnLSummary,
    DailyPnLPoint,
)
from backend.schemas.calendar import (
    CalendarMonthResponse,
    CalendarDayDetail,
)

router = APIRouter()


@router.get("/periods", response_model=list[PeriodItem])
def get_periods(db: Session = Depends(get_db)):
    """Get all import periods with PnL summary."""
    from backend.services.analysis_service import AnalysisService
    return AnalysisService(db).get_periods()


@router.get("/period-detail", response_model=list[DailyPnLPoint])
def get_period_detail(
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    db: Session = Depends(get_db),
):
    """Get daily PnL points for a period."""
    from backend.services.analysis_service import AnalysisService
    return AnalysisService(db).get_period_detail(start_date, end_date)


@router.get("/fund-pnl", response_model=list[FundPnLSummary])
def get_fund_pnl(
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    db: Session = Depends(get_db),
):
    """Get per-fund PnL summary for a period."""
    from backend.services.analysis_service import AnalysisService
    return AnalysisService(db).get_fund_pnl(start_date, end_date)


@router.get("/calendar", response_model=CalendarMonthResponse)
def get_calendar_month(
    year: int = Query(..., description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db),
):
    """Get monthly calendar with daily PnL data."""
    from backend.services.calendar_service import CalendarService
    return CalendarService(db).get_monthly_pnl(year, month)


@router.get("/calendar/{target_date}/detail", response_model=list[CalendarDayDetail])
def get_calendar_day_detail(
    target_date: date = Path(..., description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
):
    """Get per-fund PnL detail for a specific day."""
    from backend.services.calendar_service import CalendarService
    return CalendarService(db).get_day_detail(target_date)
