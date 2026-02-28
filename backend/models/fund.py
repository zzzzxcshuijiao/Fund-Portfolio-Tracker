"""Fund model - basic fund information."""

from sqlalchemy import Column, BigInteger, String, Numeric, Date, SmallInteger, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class Fund(Base):
    __tablename__ = "funds"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fund_code = Column(String(10), nullable=False, unique=True, comment="基金代码")
    fund_name = Column(String(200), nullable=False)
    fund_type = Column(String(50), default=None, comment="基金类型")
    management_company = Column(String(100), default=None)
    latest_nav = Column(Numeric(10, 4), default=None, comment="最新净值（缓存）")
    latest_nav_date = Column(Date, default=None)
    nav_change_pct = Column(Numeric(8, 4), default=None, comment="最新涨跌幅%")
    status = Column(SmallInteger, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
