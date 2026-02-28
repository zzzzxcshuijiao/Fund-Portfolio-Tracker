"""HoldingDailyPnL schemas for API response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional


class HoldingDailyPnLResponse(BaseModel):
    id: int
    pnl_date: date
    holding_id: int
    fund_code: str
    shares: Optional[Decimal] = None
    nav: Optional[Decimal] = None
    prev_nav: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PeriodItem(BaseModel):
    """An import period (between two imports)."""
    start_date: date
    end_date: date
    start_import_id: int
    end_import_id: int
    start_label: str
    end_label: str
    total_pnl: Optional[Decimal] = None
    trading_days: int = 0


class FundPnLSummary(BaseModel):
    """Per-fund PnL summary for a period."""
    fund_code: str
    fund_name: Optional[str] = None
    platform: Optional[str] = None
    shares: Optional[Decimal] = None
    start_mv: Optional[Decimal] = None
    end_mv: Optional[Decimal] = None
    period_pnl: Optional[Decimal] = None
    period_pnl_pct: Optional[Decimal] = None


class DailyPnLPoint(BaseModel):
    """A single day's total PnL."""
    pnl_date: date
    total_pnl: Optional[Decimal] = None
    total_mv: Optional[Decimal] = None
