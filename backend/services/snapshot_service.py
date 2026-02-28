"""Snapshot service - creates daily portfolio snapshots."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.holding_daily_pnl import HoldingDailyPnL
from backend.models.nav_history import FundNavHistory
from backend.models.portfolio_snapshot import PortfolioSnapshot

TEN_THOUSAND = Decimal("10000")


class SnapshotService:
    def __init__(self, db: Session):
        self.db = db

    def create_daily_snapshot(self, snapshot_date: date = None) -> PortfolioSnapshot:
        """Create a portfolio snapshot for the given date."""
        if snapshot_date is None:
            snapshot_date = date.today()

        # Check if snapshot already exists
        existing = self.db.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.snapshot_date == snapshot_date)
        ).scalar_one_or_none()

        if existing:
            # Update existing snapshot
            snapshot = existing
        else:
            snapshot = PortfolioSnapshot(snapshot_date=snapshot_date)

        # Calculate total market value
        total_mv = self.db.execute(
            select(func.sum(FundHolding.market_value))
            .where(FundHolding.status == 1)
        ).scalar() or Decimal("0")

        total_count = self.db.execute(
            select(func.count())
            .select_from(FundHolding)
            .where(FundHolding.status == 1)
        ).scalar() or 0

        # Platform breakdown
        platform_rows = self.db.execute(
            select(
                FundHolding.platform,
                func.sum(FundHolding.market_value).label("mv"),
                func.count().label("cnt"),
            )
            .where(FundHolding.status == 1)
            .group_by(FundHolding.platform)
        ).all()

        platform_breakdown = {
            r.platform: {"market_value": float(r.mv or 0), "count": r.cnt}
            for r in platform_rows
        }

        # Daily PnL - compare with previous snapshot
        prev_snapshot = self.db.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.snapshot_date < snapshot_date)
            .order_by(PortfolioSnapshot.snapshot_date.desc())
            .limit(1)
        ).scalar_one_or_none()

        daily_pnl = None
        daily_pnl_pct = None
        if prev_snapshot and prev_snapshot.total_market_value:
            daily_pnl = total_mv - prev_snapshot.total_market_value
            if prev_snapshot.total_market_value > 0:
                daily_pnl_pct = (
                    daily_pnl / prev_snapshot.total_market_value * 100
                )

        snapshot.total_market_value = total_mv
        snapshot.total_shares_count = total_count
        snapshot.daily_pnl = daily_pnl
        snapshot.daily_pnl_pct = daily_pnl_pct
        snapshot.platform_breakdown = platform_breakdown

        if not existing:
            self.db.add(snapshot)

        self.db.commit()
        self.db.refresh(snapshot)

        # Record per-holding daily PnL
        self._record_holding_daily_pnl(snapshot_date)

        return snapshot

    def _record_holding_daily_pnl(self, snapshot_date: date) -> None:
        """Record daily PnL for each active holding."""
        # Get money fund codes
        money_fund_codes = self._get_money_fund_codes()

        # Get all active holdings with fund info
        rows = self.db.execute(
            select(FundHolding, Fund)
            .outerjoin(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        ).all()

        for holding, fund in rows:
            if not fund or not fund.latest_nav or not holding.shares:
                continue

            shares = holding.shares
            is_money = holding.fund_code in money_fund_codes

            if is_money:
                nav = fund.latest_nav  # 1.0000 for money funds
                mv = shares  # each share = 1 yuan

                # Get today's DWJZ (万份收益) from nav_history
                today_dwjz = self.db.execute(
                    select(FundNavHistory.unit_nav)
                    .where(
                        FundNavHistory.fund_code == holding.fund_code,
                        FundNavHistory.nav_date == snapshot_date,
                    )
                ).scalar_one_or_none()

                if today_dwjz:
                    pnl = shares * today_dwjz / TEN_THOUSAND
                    pnl_pct = today_dwjz / TEN_THOUSAND * 100
                else:
                    pnl = None
                    pnl_pct = None
                prev_nav = None
            else:
                nav = fund.latest_nav
                mv = shares * nav

                # Get previous NAV from fund_nav_history
                prev_nav_row = self.db.execute(
                    select(FundNavHistory.unit_nav)
                    .where(
                        FundNavHistory.fund_code == holding.fund_code,
                        FundNavHistory.nav_date < snapshot_date,
                    )
                    .order_by(FundNavHistory.nav_date.desc())
                    .limit(1)
                ).scalar_one_or_none()

                prev_nav = prev_nav_row if prev_nav_row else None
                pnl = None
                pnl_pct = None
                if prev_nav and prev_nav > 0:
                    pnl = shares * (nav - prev_nav)
                    pnl_pct = (nav - prev_nav) / prev_nav * 100

            # Upsert: check if record exists
            existing = self.db.execute(
                select(HoldingDailyPnL).where(
                    HoldingDailyPnL.holding_id == holding.id,
                    HoldingDailyPnL.pnl_date == snapshot_date,
                )
            ).scalar_one_or_none()

            if existing:
                existing.fund_code = holding.fund_code
                existing.shares = shares
                existing.nav = nav
                existing.prev_nav = prev_nav
                existing.market_value = mv
                existing.daily_pnl = pnl
                existing.daily_pnl_pct = pnl_pct
            else:
                record = HoldingDailyPnL(
                    pnl_date=snapshot_date,
                    holding_id=holding.id,
                    fund_code=holding.fund_code,
                    shares=shares,
                    nav=nav,
                    prev_nav=prev_nav,
                    market_value=mv,
                    daily_pnl=pnl,
                    daily_pnl_pct=pnl_pct,
                )
                self.db.add(record)

        self.db.commit()

    def _get_money_fund_codes(self) -> set[str]:
        """Get set of fund codes that are money market funds."""
        rows = self.db.execute(
            select(Fund.fund_code).where(Fund.fund_type == "货币型")
        ).scalars().all()
        return set(rows)
