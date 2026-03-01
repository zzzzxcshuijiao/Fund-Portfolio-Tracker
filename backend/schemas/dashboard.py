"""Dashboard schemas for API response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from typing import Optional


class DashboardSummary(BaseModel):
    total_market_value: Decimal = Decimal("0")
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    total_holdings: int = 0
    total_funds: int = 0
    total_platforms: int = 0
    nav_update_time: Optional[str] = None


class PlatformDistribution(BaseModel):
    platform: str
    market_value: Decimal
    count: int
    percentage: Optional[Decimal] = None
    daily_pnl: Optional[Decimal] = None


class DailyPnLPoint(BaseModel):
    date: date
    total_market_value: Decimal
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    portfolio_nav: Optional[Decimal] = None
    cumulative_return_pct: Optional[Decimal] = None


class TopHolding(BaseModel):
    fund_code: str
    fund_name: str
    total_market_value: Decimal
    total_shares: Decimal
    latest_nav: Optional[Decimal] = None
    nav_change_pct: Optional[Decimal] = None
    platform_count: int = 1
