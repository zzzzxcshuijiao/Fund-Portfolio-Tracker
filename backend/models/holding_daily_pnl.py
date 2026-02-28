"""HoldingDailyPnL model - daily per-holding profit and loss."""

from sqlalchemy import Column, BigInteger, String, Numeric, Date, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func

from backend.database import Base


class HoldingDailyPnL(Base):
    __tablename__ = "holding_daily_pnl"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pnl_date = Column(Date, nullable=False)
    holding_id = Column(BigInteger, nullable=False, comment="关联 fund_holdings.id")
    fund_code = Column(String(10), nullable=False)
    shares = Column(Numeric(16, 4))
    nav = Column(Numeric(10, 4))
    prev_nav = Column(Numeric(10, 4))
    market_value = Column(Numeric(16, 4))
    daily_pnl = Column(Numeric(16, 4), comment="日盈亏额")
    daily_pnl_pct = Column(Numeric(8, 4), comment="日盈亏率%")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("holding_id", "pnl_date", name="uk_holding_pnl_date"),
        Index("idx_pnl_date", "pnl_date"),
        Index("idx_pnl_fund_code", "fund_code"),
    )
