"""HoldingChange schemas for API response."""

from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
from typing import Optional


class HoldingChangeResponse(BaseModel):
    id: int
    import_id: int
    holding_id: Optional[int] = None
    fund_code: str
    fund_name: Optional[str] = None
    platform: Optional[str] = None
    change_type: str
    shares_before: Optional[Decimal] = None
    shares_after: Optional[Decimal] = None
    shares_delta: Optional[Decimal] = None
    nav_at_change: Optional[Decimal] = None
    mv_before: Optional[Decimal] = None
    mv_after: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
