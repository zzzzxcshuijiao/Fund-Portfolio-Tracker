"""Holding schemas for API request/response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional


class HoldingResponse(BaseModel):
    id: int
    fund_code: str
    fund_name: str
    share_type: Optional[str] = None
    management_company: Optional[str] = None
    platform: str
    fund_account: str
    trade_account: str
    shares: Decimal
    share_date: date
    nav_on_import: Optional[Decimal] = None
    nav_date: Optional[date] = None
    cost_nav: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    currency: str = "人民币"
    dividend_mode: Optional[str] = None
    status: int = 1
    # Joined from funds table
    latest_nav: Optional[Decimal] = None
    latest_nav_date: Optional[date] = None
    nav_change_pct: Optional[Decimal] = None
    current_market_value: Optional[Decimal] = None
    daily_pnl: Optional[Decimal] = None
    total_pnl: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HoldingCostUpdate(BaseModel):
    cost_nav: Decimal


class HoldingsByPlatformResponse(BaseModel):
    platform: str
    count: int
    total_market_value: Optional[Decimal] = None
    holdings: list[HoldingResponse] = []
