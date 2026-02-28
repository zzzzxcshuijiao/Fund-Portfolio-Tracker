"""Funds API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.fund import FundResponse, FundDetailResponse

router = APIRouter()


@router.get("/{fund_code}", response_model=FundDetailResponse)
def get_fund_detail(fund_code: str, db: Session = Depends(get_db)):
    """Get fund detail with aggregated holdings info."""
    from backend.services.fund_service import FundService
    return FundService(db).get_fund_detail(fund_code)


@router.get("/{fund_code}/nav-history")
def get_fund_nav_history(
    fund_code: str,
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get fund NAV history for the past N days."""
    from backend.services.nav_service import NavService
    return NavService(db).get_nav_history(fund_code, days)
