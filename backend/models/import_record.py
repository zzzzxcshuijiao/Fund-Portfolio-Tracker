"""Import record model - tracks Excel import history."""

from sqlalchemy import Column, BigInteger, String, Integer, Date, Text, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class ImportRecord(Base):
    __tablename__ = "import_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), default=None, comment="防重复导入")
    total_rows = Column(Integer, default=0)
    new_holdings = Column(Integer, default=0)
    updated_holdings = Column(Integer, default=0)
    removed_holdings = Column(Integer, default=0)
    error_rows = Column(Integer, default=0)
    data_date = Column(Date, default=None)
    status = Column(String(20), default="success")
    error_message = Column(Text, default=None)
    created_at = Column(DateTime, server_default=func.now())
