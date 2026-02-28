"""Import result schemas for API response."""

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

from backend.schemas.holding_change import HoldingChangeResponse


class ImportResult(BaseModel):
    import_id: int
    file_name: str
    total_rows: int = 0
    new_holdings: int = 0
    updated_holdings: int = 0
    removed_holdings: int = 0
    error_rows: int = 0
    data_date: Optional[date] = None
    status: str = "success"
    error_message: Optional[str] = None
    changes: list[HoldingChangeResponse] = []


class ImportHistoryItem(BaseModel):
    id: int
    file_name: str
    total_rows: int
    new_holdings: int
    updated_holdings: int
    removed_holdings: int
    error_rows: int
    data_date: Optional[date] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
