"""Analysis service - period PnL analysis between imports."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.holding_daily_pnl import HoldingDailyPnL
from backend.models.import_record import ImportRecord
from backend.schemas.holding_daily_pnl import (
    PeriodItem,
    FundPnLSummary,
    DailyPnLPoint,
)


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db

    def get_periods(self) -> list[PeriodItem]:
        """Get all import periods (consecutive import pairs)."""
        records = self.db.execute(
            select(ImportRecord)
            .where(ImportRecord.status == "success")
            .order_by(ImportRecord.created_at.asc())
        ).scalars().all()

        if len(records) < 2:
            return []

        periods = []
        for i in range(len(records) - 1):
            r_start = records[i]
            r_end = records[i + 1]
            start_date = r_start.data_date or r_start.created_at.date()
            end_date = r_end.data_date or r_end.created_at.date()

            # Calculate total PnL for this period
            total_pnl = self.db.execute(
                select(func.sum(HoldingDailyPnL.daily_pnl))
                .where(
                    HoldingDailyPnL.pnl_date > start_date,
                    HoldingDailyPnL.pnl_date <= end_date,
                )
            ).scalar()

            trading_days = self.db.execute(
                select(func.count(func.distinct(HoldingDailyPnL.pnl_date)))
                .where(
                    HoldingDailyPnL.pnl_date > start_date,
                    HoldingDailyPnL.pnl_date <= end_date,
                )
            ).scalar() or 0

            periods.append(PeriodItem(
                start_date=start_date,
                end_date=end_date,
                start_import_id=r_start.id,
                end_import_id=r_end.id,
                start_label=f"#{r_start.id} ({start_date})",
                end_label=f"#{r_end.id} ({end_date})",
                total_pnl=total_pnl,
                trading_days=trading_days,
            ))

        return periods

    def get_period_detail(
        self, start_date: date, end_date: date
    ) -> list[DailyPnLPoint]:
        """Get daily PnL points for a period."""
        rows = self.db.execute(
            select(
                HoldingDailyPnL.pnl_date,
                func.sum(HoldingDailyPnL.daily_pnl).label("total_pnl"),
                func.sum(HoldingDailyPnL.market_value).label("total_mv"),
            )
            .where(
                HoldingDailyPnL.pnl_date > start_date,
                HoldingDailyPnL.pnl_date <= end_date,
            )
            .group_by(HoldingDailyPnL.pnl_date)
            .order_by(HoldingDailyPnL.pnl_date)
        ).all()

        return [
            DailyPnLPoint(
                pnl_date=r.pnl_date,
                total_pnl=r.total_pnl,
                total_mv=r.total_mv,
            )
            for r in rows
        ]

    def get_fund_pnl(
        self, start_date: date, end_date: date
    ) -> list[FundPnLSummary]:
        """Get per-fund PnL summary for a period."""
        # Aggregate daily PnL by fund_code
        rows = self.db.execute(
            select(
                HoldingDailyPnL.fund_code,
                func.sum(HoldingDailyPnL.daily_pnl).label("period_pnl"),
            )
            .where(
                HoldingDailyPnL.pnl_date > start_date,
                HoldingDailyPnL.pnl_date <= end_date,
            )
            .group_by(HoldingDailyPnL.fund_code)
        ).all()

        pnl_map = {r.fund_code: r.period_pnl for r in rows}

        # Get start MV (first day in period) and end MV (last day in period)
        first_date = self.db.execute(
            select(func.min(HoldingDailyPnL.pnl_date))
            .where(
                HoldingDailyPnL.pnl_date > start_date,
                HoldingDailyPnL.pnl_date <= end_date,
            )
        ).scalar()

        last_date = self.db.execute(
            select(func.max(HoldingDailyPnL.pnl_date))
            .where(
                HoldingDailyPnL.pnl_date > start_date,
                HoldingDailyPnL.pnl_date <= end_date,
            )
        ).scalar()

        if not first_date or not last_date:
            return []

        # Start MV per fund
        start_mv_rows = self.db.execute(
            select(
                HoldingDailyPnL.fund_code,
                func.sum(HoldingDailyPnL.market_value).label("mv"),
                func.sum(HoldingDailyPnL.shares).label("shares"),
            )
            .where(HoldingDailyPnL.pnl_date == first_date)
            .group_by(HoldingDailyPnL.fund_code)
        ).all()
        start_mv_map = {r.fund_code: (r.mv, r.shares) for r in start_mv_rows}

        # End MV per fund
        end_mv_rows = self.db.execute(
            select(
                HoldingDailyPnL.fund_code,
                func.sum(HoldingDailyPnL.market_value).label("mv"),
            )
            .where(HoldingDailyPnL.pnl_date == last_date)
            .group_by(HoldingDailyPnL.fund_code)
        ).all()
        end_mv_map = {r.fund_code: r.mv for r in end_mv_rows}

        # Fund info
        all_codes = set(pnl_map.keys())
        funds = self.db.execute(
            select(Fund).where(Fund.fund_code.in_(all_codes))
        ).scalars().all()
        fund_map = {f.fund_code: f for f in funds}

        # Holding info for platform
        holdings = self.db.execute(
            select(FundHolding.fund_code, FundHolding.platform)
            .where(FundHolding.fund_code.in_(all_codes))
            .distinct()
        ).all()
        platform_map = {r.fund_code: r.platform for r in holdings}

        results = []
        for code, period_pnl in pnl_map.items():
            fund = fund_map.get(code)
            s_mv, s_shares = start_mv_map.get(code, (None, None))
            e_mv = end_mv_map.get(code)

            pnl_pct = None
            if s_mv and s_mv > 0 and period_pnl is not None:
                pnl_pct = period_pnl / s_mv * 100

            results.append(FundPnLSummary(
                fund_code=code,
                fund_name=fund.fund_name if fund else None,
                platform=platform_map.get(code),
                shares=s_shares,
                start_mv=s_mv,
                end_mv=e_mv,
                period_pnl=period_pnl,
                period_pnl_pct=pnl_pct,
            ))

        # Sort by period_pnl desc
        results.sort(key=lambda x: x.period_pnl or Decimal("0"), reverse=True)
        return results
