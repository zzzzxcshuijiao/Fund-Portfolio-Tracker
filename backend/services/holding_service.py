"""Holding service - query and manage fund holdings."""

from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, distinct, case
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.schemas.holding import HoldingResponse, HoldingsByPlatformResponse


class HoldingService:
    def __init__(self, db: Session):
        self.db = db

    def get_holdings(
        self,
        platform: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "market_value",
        sort_order: str = "desc",
    ) -> list[HoldingResponse]:
        """Get all active holdings with optional filters."""
        query = (
            select(FundHolding, Fund)
            .outerjoin(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        )

        if platform:
            query = query.where(FundHolding.platform == platform)
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (FundHolding.fund_code.like(search_term))
                | (FundHolding.fund_name.like(search_term))
            )

        # Sorting (MySQL doesn't support NULLS LAST, use COALESCE)
        sort_col = self._get_sort_column(sort_by)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(
                case((sort_col.is_(None), 1), else_=0),
                sort_col.desc(),
            )

        rows = self.db.execute(query).all()

        results = []
        for holding, fund in rows:
            current_mv = None
            if fund and fund.latest_nav and holding.shares:
                current_mv = holding.shares * fund.latest_nav

            daily_pnl = None
            if current_mv and fund and fund.nav_change_pct:
                daily_pnl = current_mv * fund.nav_change_pct / Decimal("100")

            # Total PnL = current MV - cost MV
            total_pnl = None
            if current_mv and holding.cost_nav and holding.shares:
                cost_mv = holding.shares * holding.cost_nav
                total_pnl = current_mv - cost_mv

            results.append(HoldingResponse(
                id=holding.id,
                fund_code=holding.fund_code,
                fund_name=holding.fund_name,
                share_type=holding.share_type,
                management_company=holding.management_company,
                platform=holding.platform,
                fund_account=holding.fund_account,
                trade_account=holding.trade_account,
                shares=holding.shares,
                share_date=holding.share_date,
                nav_on_import=holding.nav_on_import,
                nav_date=holding.nav_date,
                cost_nav=holding.cost_nav,
                market_value=holding.market_value,
                currency=holding.currency,
                dividend_mode=holding.dividend_mode,
                status=holding.status,
                latest_nav=fund.latest_nav if fund else None,
                latest_nav_date=fund.latest_nav_date if fund else None,
                nav_change_pct=fund.nav_change_pct if fund else None,
                current_market_value=current_mv,
                daily_pnl=daily_pnl,
                total_pnl=total_pnl,
                created_at=holding.created_at,
                updated_at=holding.updated_at,
            ))

        return results

    def get_holdings_by_platform(self) -> list[HoldingsByPlatformResponse]:
        """Get holdings grouped by platform."""
        platforms = self.get_platforms()
        results = []

        for platform in platforms:
            holdings = self.get_holdings(platform=platform)
            total_mv = sum(
                h.current_market_value or h.market_value or Decimal("0")
                for h in holdings
            )
            results.append(HoldingsByPlatformResponse(
                platform=platform,
                count=len(holdings),
                total_market_value=total_mv,
                holdings=holdings,
            ))

        results.sort(key=lambda x: x.total_market_value or 0, reverse=True)
        return results

    def get_platforms(self) -> list[str]:
        """Get all distinct platform names from active holdings."""
        result = self.db.execute(
            select(distinct(FundHolding.platform))
            .where(FundHolding.status == 1)
            .order_by(FundHolding.platform)
        ).scalars().all()
        return list(result)

    def update_cost(self, holding_id: int, cost_nav: Decimal) -> HoldingResponse:
        """Update cost_nav for a holding."""
        holding = self.db.execute(
            select(FundHolding).where(FundHolding.id == holding_id)
        ).scalar_one_or_none()

        if not holding:
            raise ValueError(f"Holding {holding_id} not found")

        holding.cost_nav = cost_nav
        self.db.commit()
        self.db.refresh(holding)

        # Return updated holding with fund info
        results = self.get_holdings(search=holding.fund_code)
        for r in results:
            if r.id == holding_id:
                return r

        # Fallback: return basic info
        return HoldingResponse(
            id=holding.id,
            fund_code=holding.fund_code,
            fund_name=holding.fund_name,
            platform=holding.platform,
            fund_account=holding.fund_account,
            trade_account=holding.trade_account,
            shares=holding.shares,
            share_date=holding.share_date,
            cost_nav=holding.cost_nav,
            market_value=holding.market_value,
        )

    def _get_sort_column(self, sort_by: str):
        """Map sort field name to SQLAlchemy column."""
        mapping = {
            "market_value": FundHolding.market_value,
            "shares": FundHolding.shares,
            "fund_code": FundHolding.fund_code,
            "fund_name": FundHolding.fund_name,
            "platform": FundHolding.platform,
        }
        return mapping.get(sort_by, FundHolding.market_value)
