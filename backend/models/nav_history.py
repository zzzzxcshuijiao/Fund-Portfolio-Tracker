"""NAV history model - daily fund net asset values."""

from sqlalchemy import Column, BigInteger, String, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class FundNavHistory(Base):
    __tablename__ = "fund_nav_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fund_code = Column(String(10), nullable=False)
    nav_date = Column(Date, nullable=False)
    unit_nav = Column(Numeric(10, 4), nullable=False)
    acc_nav = Column(Numeric(10, 4), default=None)
    change_pct = Column(Numeric(8, 4), default=None)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("fund_code", "nav_date", name="uk_fund_nav_date"),
    )
