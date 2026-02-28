"""Holdings API endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db
from backend.schemas.holding import HoldingResponse, HoldingsByPlatformResponse, HoldingCostUpdate

router = APIRouter()


@router.get("", response_model=list[HoldingResponse])
def get_holdings(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    search: Optional[str] = Query(None, description="Search by fund code or name"),
    sort_by: str = Query("market_value", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    db: Session = Depends(get_db),
):
    """Get all active holdings with optional filters."""
    from backend.services.holding_service import HoldingService
    return HoldingService(db).get_holdings(
        platform=platform, search=search, sort_by=sort_by, sort_order=sort_order
    )


@router.get("/by-platform", response_model=list[HoldingsByPlatformResponse])
def get_holdings_by_platform(db: Session = Depends(get_db)):
    """Get holdings grouped by platform."""
    from backend.services.holding_service import HoldingService
    return HoldingService(db).get_holdings_by_platform()


@router.get("/platforms", response_model=list[str])
def get_platforms(db: Session = Depends(get_db)):
    """Get all distinct platform names."""
    from backend.services.holding_service import HoldingService
    return HoldingService(db).get_platforms()


@router.patch("/{holding_id}", response_model=HoldingResponse)
def update_holding_cost(
    holding_id: int,
    body: HoldingCostUpdate,
    db: Session = Depends(get_db),
):
    """Update cost_nav for a holding."""
    from backend.services.holding_service import HoldingService
    try:
        return HoldingService(db).update_cost(holding_id, body.cost_nav)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
