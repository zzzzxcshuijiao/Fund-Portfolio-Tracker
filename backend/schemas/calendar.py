"""Calendar schemas for API response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from typing import Optional


class CalendarDayData(BaseModel):
    date: date
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    is_trading_day: bool = True


class MonthSummary(BaseModel):
    total_pnl: Optional[Decimal] = None
    trading_days: int = 0
    avg_daily_pnl: Optional[Decimal] = None
    best_day: Optional[CalendarDayData] = None
    worst_day: Optional[CalendarDayData] = None


class CalendarMonthResponse(BaseModel):
    year: int
    month: int
    summary: MonthSummary
    daily_data: list[CalendarDayData]


class CalendarDayDetail(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None
    platform: Optional[str] = None
    shares: Decimal
    nav: Optional[Decimal] = None
    prev_nav: Optional[Decimal] = None
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
