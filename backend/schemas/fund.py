"""Fund schemas for API request/response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional


class FundBase(BaseModel):
    fund_code: str
    fund_name: str
    fund_type: Optional[str] = None
    management_company: Optional[str] = None


class FundResponse(FundBase):
    id: int
    latest_nav: Optional[Decimal] = None
    latest_nav_date: Optional[date] = None
    nav_change_pct: Optional[Decimal] = None
    status: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FundDetailResponse(FundResponse):
    """Fund detail with aggregated holding info."""
    total_shares: Optional[Decimal] = None
    total_market_value: Optional[Decimal] = None
    platform_count: Optional[int] = None
