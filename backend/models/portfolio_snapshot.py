"""Portfolio snapshot model - daily portfolio snapshots."""

from sqlalchemy import Column, BigInteger, Date, Numeric, Integer, JSON, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, unique=True)
    total_market_value = Column(Numeric(16, 4), nullable=False)
    total_shares_count = Column(Integer, nullable=False)
    daily_pnl = Column(Numeric(16, 4), default=None)
    daily_pnl_pct = Column(Numeric(8, 4), default=None)
    platform_breakdown = Column(JSON, default=None, comment="按平台市值分布")
    holdings_detail = Column(JSON, default=None, comment="全量持仓明细快照")
    portfolio_nav = Column(Numeric(12, 6), default=None, comment="组合净值（起始1.000000）")
    total_units = Column(Numeric(20, 4), default=None, comment="组合份额（用于发行/赎回）")
    net_inflow = Column(Numeric(16, 4), default=None, comment="当日净资金流入（正=买入,负=卖出）")
    created_at = Column(DateTime, server_default=func.now())
