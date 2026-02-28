"""Fund service - query fund details."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.schemas.fund import FundDetailResponse


class FundService:
    def __init__(self, db: Session):
        self.db = db

    def get_fund_detail(self, fund_code: str) -> FundDetailResponse:
        """Get fund detail with aggregated holding info."""
        fund = self.db.execute(
            select(Fund).where(Fund.fund_code == fund_code)
        ).scalar_one_or_none()

        if not fund:
            raise HTTPException(status_code=404, detail=f"基金 {fund_code} 不存在")

        # Aggregate holding info
        agg = self.db.execute(
            select(
                func.sum(FundHolding.shares).label("total_shares"),
                func.sum(FundHolding.market_value).label("total_market_value"),
                func.count(func.distinct(FundHolding.platform)).label("platform_count"),
            ).where(
                FundHolding.fund_code == fund_code,
                FundHolding.status == 1,
            )
        ).one()

        # Recalculate market value if we have latest NAV
        total_mv = agg.total_market_value
        if fund.latest_nav and agg.total_shares:
            total_mv = agg.total_shares * fund.latest_nav

        return FundDetailResponse(
            id=fund.id,
            fund_code=fund.fund_code,
            fund_name=fund.fund_name,
            fund_type=fund.fund_type,
            management_company=fund.management_company,
            latest_nav=fund.latest_nav,
            latest_nav_date=fund.latest_nav_date,
            nav_change_pct=fund.nav_change_pct,
            status=fund.status,
            created_at=fund.created_at,
            updated_at=fund.updated_at,
            total_shares=agg.total_shares,
            total_market_value=total_mv,
            platform_count=agg.platform_count or 0,
        )
