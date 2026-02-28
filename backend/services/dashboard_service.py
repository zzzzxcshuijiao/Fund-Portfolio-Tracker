"""Dashboard service - aggregated portfolio data for dashboard."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.portfolio_snapshot import PortfolioSnapshot
from backend.schemas.dashboard import (
    DashboardSummary,
    PlatformDistribution,
    DailyPnLPoint,
    TopHolding,
)


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self) -> DashboardSummary:
        """Get portfolio summary."""
        # Get active holdings joined with fund info
        rows = self.db.execute(
            select(FundHolding, Fund)
            .outerjoin(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        ).all()

        total_mv = Decimal("0")
        daily_pnl = Decimal("0")
        fund_codes = set()
        platforms = set()

        for holding, fund in rows:
            # Calculate current market value using latest NAV
            if fund and fund.latest_nav and holding.shares:
                mv = holding.shares * fund.latest_nav
            else:
                mv = holding.market_value or Decimal("0")
            total_mv += mv

            # Calculate daily PnL: market_value * change_pct / 100
            if fund and fund.nav_change_pct and mv:
                pnl = mv * fund.nav_change_pct / Decimal("100")
                daily_pnl += pnl

            fund_codes.add(holding.fund_code)
            platforms.add(holding.platform)

        daily_pnl_pct = None
        if total_mv > 0 and daily_pnl != 0:
            daily_pnl_pct = daily_pnl / total_mv * Decimal("100")

        # NAV update time
        latest_nav_date = self.db.execute(
            select(func.max(Fund.latest_nav_date))
        ).scalar()
        nav_update_time = str(latest_nav_date) if latest_nav_date else None

        return DashboardSummary(
            total_market_value=total_mv,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            total_holdings=len(rows),
            total_funds=len(fund_codes),
            total_platforms=len(platforms),
            nav_update_time=nav_update_time,
        )

    def get_platform_distribution(self) -> list[PlatformDistribution]:
        """Get market value distribution by platform (real-time via latest NAV)."""
        rows = self.db.execute(
            select(FundHolding, Fund)
            .outerjoin(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        ).all()

        platform_map: dict[str, dict] = {}
        for holding, fund in rows:
            if fund and fund.latest_nav and holding.shares:
                mv = holding.shares * fund.latest_nav
            else:
                mv = holding.market_value or Decimal("0")

            pnl = Decimal("0")
            if fund and fund.nav_change_pct and mv:
                pnl = mv * fund.nav_change_pct / Decimal("100")

            entry = platform_map.setdefault(holding.platform, {
                "market_value": Decimal("0"),
                "count": 0,
                "daily_pnl": Decimal("0"),
            })
            entry["market_value"] += mv
            entry["count"] += 1
            entry["daily_pnl"] += pnl

        total = sum(e["market_value"] for e in platform_map.values())
        results = []
        for platform, entry in platform_map.items():
            mv = entry["market_value"]
            pct = (mv / total * 100) if total > 0 else Decimal("0")
            results.append(PlatformDistribution(
                platform=platform,
                market_value=mv,
                count=entry["count"],
                percentage=round(pct, 2),
                daily_pnl=entry["daily_pnl"],
            ))
        results.sort(key=lambda x: x.market_value, reverse=True)
        return results

    def get_daily_pnl(self, days: int = 30) -> list[DailyPnLPoint]:
        """Get daily PnL trend from snapshots."""
        cutoff = date.today() - timedelta(days=days)
        snapshots = self.db.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.snapshot_date >= cutoff)
            .order_by(PortfolioSnapshot.snapshot_date.asc())
        ).scalars().all()

        return [
            DailyPnLPoint(
                date=s.snapshot_date,
                total_market_value=s.total_market_value,
                daily_pnl=s.daily_pnl,
                daily_pnl_pct=s.daily_pnl_pct,
            )
            for s in snapshots
        ]

    def get_top_holdings(self, limit: int = 10) -> list[TopHolding]:
        """Get top N holdings by aggregated market value."""
        rows = self.db.execute(
            select(
                FundHolding.fund_code,
                FundHolding.fund_name,
                func.sum(FundHolding.market_value).label("total_market_value"),
                func.sum(FundHolding.shares).label("total_shares"),
                func.count(distinct(FundHolding.platform)).label("platform_count"),
            )
            .where(FundHolding.status == 1)
            .group_by(FundHolding.fund_code, FundHolding.fund_name)
            .order_by(func.sum(FundHolding.market_value).desc())
            .limit(limit)
        ).all()

        results = []
        for r in rows:
            fund = self.db.execute(
                select(Fund).where(Fund.fund_code == r.fund_code)
            ).scalar_one_or_none()

            results.append(TopHolding(
                fund_code=r.fund_code,
                fund_name=r.fund_name,
                total_market_value=r.total_market_value or Decimal("0"),
                total_shares=r.total_shares or Decimal("0"),
                latest_nav=fund.latest_nav if fund else None,
                nav_change_pct=fund.nav_change_pct if fund else None,
                platform_count=r.platform_count or 1,
            ))

        return results
