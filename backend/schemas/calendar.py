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
    trade_dates: list[str] = []  # YYYY-MM-DD，当日有非货币基金份额变动


class CalendarDayDetail(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None
    platform: Optional[str] = None
    fund_account: Optional[str] = None
    shares: Decimal
    nav: Optional[Decimal] = None
    nav_date: Optional[date] = None  # 实际净值日期，可能早于查询日期（回退）
    prev_nav: Optional[Decimal] = None
    import_nav: Optional[Decimal] = None    # Excel 导入时的净值（仅导入日有值）
    nav_mismatch: Optional[bool] = None     # True = 导入净值与接口净值不一致
    daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None
    market_value: Optional[Decimal] = None


class DayTotalSummary(BaseModel):
    total_market_value: Decimal
    total_daily_pnl: Optional[Decimal] = None
    daily_pnl_pct: Optional[Decimal] = None


class AccountAsset(BaseModel):
    platform: str
    market_value: Decimal
    daily_pnl: Optional[Decimal] = None


class DayTradeItem(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None
    platform: Optional[str] = None
    fund_account: Optional[str] = None
    change_type: str  # new / increase / decrease / clear
    shares_before: Optional[Decimal] = None
    shares_after: Optional[Decimal] = None
    shares_delta: Optional[Decimal] = None
    nav_at_change: Optional[Decimal] = None
    mv_before: Optional[Decimal] = None
    mv_after: Optional[Decimal] = None


class CalendarDayResponse(BaseModel):
    date: date
    summary: DayTotalSummary
    accounts: list[AccountAsset]
    trades: list[DayTradeItem]
    holdings: list[CalendarDayDetail]
