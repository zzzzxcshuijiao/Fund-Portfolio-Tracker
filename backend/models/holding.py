"""Holding model - fund holding positions."""

from sqlalchemy import Column, BigInteger, String, Numeric, Date, SmallInteger, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class FundHolding(Base):
    __tablename__ = "fund_holdings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fund_code = Column(String(10), nullable=False)
    fund_name = Column(String(200), nullable=False)
    share_type = Column(String(20), default="前收费")
    management_company = Column(String(100), default=None)
    platform = Column(String(100), nullable=False, comment="销售机构")
    fund_account = Column(String(50), nullable=False, comment="基金账户")
    trade_account = Column(String(50), nullable=False, comment="交易账户")
    shares = Column(Numeric(16, 4), nullable=False, comment="持有份额")
    share_date = Column(Date, nullable=False)
    nav_on_import = Column(Numeric(10, 4), default=None)
    nav_date = Column(Date, default=None)
    cost_nav = Column(Numeric(10, 4), default=None, comment="持仓成本净值(用户可编辑)")
    market_value = Column(Numeric(16, 4), default=None)
    currency = Column(String(10), default="人民币")
    dividend_mode = Column(String(20), default=None)
    last_import_id = Column(BigInteger, default=None)
    status = Column(SmallInteger, default=1, comment="1=持有 0=已清仓")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "fund_code", "platform", "fund_account", "trade_account",
            name="uk_holding"
        ),
    )
