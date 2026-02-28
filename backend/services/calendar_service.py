"""Calendar service - compute daily portfolio PnL from NAV history."""

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.models.holding import FundHolding
from backend.models.fund import Fund
from backend.models.nav_history import FundNavHistory
from backend.models.import_record import ImportRecord
from backend.models.holding_change import HoldingChange
from backend.schemas.calendar import (
    CalendarDayData,
    CalendarDayDetail,
    CalendarMonthResponse,
    MonthSummary,
)

ZERO = Decimal("0")
TEN_THOUSAND = Decimal("10000")


class CalendarService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_monthly_pnl(self, year: int, month: int) -> CalendarMonthResponse:
        """Return daily PnL for every trading day in the given month."""
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])

        empty = CalendarMonthResponse(
            year=year, month=month, summary=MonthSummary(), daily_data=[]
        )

        # 1. Import timeline & baseline
        imports = self._load_import_timeline()
        if not imports:
            return empty

        baseline_date = imports[0].data_date

        # Entire month is before baseline → nothing to show
        if month_end < baseline_date:
            return empty

        # Money fund codes
        money_fund_codes = self._get_money_fund_codes()

        # 2. All holdings (including cleared – they may have been active historically)
        holdings = self.db.query(FundHolding).all()
        if not holdings:
            return empty

        changes_map = self._load_all_holding_changes()
        shares_timeline = self._reconstruct_shares_timeline(
            holdings, imports, changes_map
        )

        # 3. Collect all fund codes across every holding
        all_fund_codes = list({h.fund_code for h in holdings})

        # 4. NAV lookup (month + 15-day buffer before)
        nav_lookup = self._build_nav_lookup(all_fund_codes, month_start, month_end)

        # 5. Trading dates in the month (dates with at least one NAV record)
        trading_dates = sorted(
            {d for (_, d) in nav_lookup if month_start <= d <= month_end}
        )

        # 6. Previous trading date per (fund, date)
        all_dates_with_prev = self._find_prev_dates(
            all_fund_codes, trading_dates, month_start
        )

        # 7. Build per-day, per-fund aggregated shares
        daily_shares = self._build_daily_shares_map(
            holdings, trading_dates, shares_timeline, imports, changes_map
        )

        # 8. Compute daily PnL
        daily_data: list[CalendarDayData] = []
        for td in trading_dates:
            if td < baseline_date:
                continue

            shares_map = daily_shares.get(td, {})
            if not shares_map:
                continue

            day_pnl = ZERO
            day_mv = ZERO
            has_data = False

            for fc, shares in shares_map.items():
                if shares <= ZERO:
                    continue

                nav_today = nav_lookup.get((fc, td))
                if nav_today is None:
                    continue

                if fc in money_fund_codes:
                    # Money fund: mv = shares, pnl = shares * dwjz / 10000
                    day_mv += shares
                    day_pnl += shares * nav_today / TEN_THOUSAND
                else:
                    mv = shares * nav_today
                    day_mv += mv

                    # PnL only when previous date exists AND is on/after baseline
                    prev_date = all_dates_with_prev.get((fc, td))
                    if prev_date is not None and prev_date >= baseline_date:
                        nav_prev = nav_lookup.get((fc, prev_date))
                        if nav_prev is not None:
                            day_pnl += shares * (nav_today - nav_prev)

                has_data = True

            if has_data:
                pnl_pct = (
                    (day_pnl / (day_mv - day_pnl) * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if (day_mv - day_pnl) != ZERO
                    else None
                )
                daily_data.append(
                    CalendarDayData(
                        date=td,
                        daily_pnl=day_pnl.quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        ),
                        daily_pnl_pct=pnl_pct,
                        market_value=day_mv.quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        ),
                        is_trading_day=True,
                    )
                )

        # 9. Summary
        summary = self._build_summary(daily_data)

        return CalendarMonthResponse(
            year=year, month=month, summary=summary, daily_data=daily_data
        )

    def get_day_detail(self, target_date: date) -> list[CalendarDayDetail]:
        """Return per-holding PnL breakdown for a single day."""
        imports = self._load_import_timeline()
        if not imports:
            return []

        baseline_date = imports[0].data_date
        if target_date < baseline_date:
            return []

        changes_map = self._load_all_holding_changes()

        # All holdings (including cleared – they may have been active on target_date)
        holdings = self.db.query(FundHolding).all()
        if not holdings:
            return []

        # Money fund codes
        money_fund_codes = self._get_money_fund_codes()

        shares_timeline = self._reconstruct_shares_timeline(
            holdings, imports, changes_map
        )

        fund_codes = list({h.fund_code for h in holdings})

        # NAV data
        nav_today_map = self._get_nav_on_date(fund_codes, target_date)
        prev_nav_map = self._get_prev_nav(fund_codes, target_date)
        prev_date_map = self._get_prev_date_map(fund_codes, target_date)

        results: list[CalendarDayDetail] = []
        for h in holdings:
            shares = self._get_effective_shares(
                target_date, h.id, shares_timeline, imports, changes_map
            )
            if shares <= ZERO:
                continue

            nav = nav_today_map.get(h.fund_code)
            prev = prev_nav_map.get(h.fund_code)

            pnl = None
            pnl_pct = None
            mv = None

            if nav is not None:
                if h.fund_code in money_fund_codes:
                    # Money fund: mv = shares, pnl = shares * dwjz / 10000
                    mv = shares.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    pnl = (shares * nav / TEN_THOUSAND).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    pnl_pct = (nav / TEN_THOUSAND * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                else:
                    mv = (shares * nav).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    # PnL only when prev date is on/after baseline
                    prev_d = prev_date_map.get(h.fund_code)
                    if (
                        prev is not None
                        and prev_d is not None
                        and prev_d >= baseline_date
                    ):
                        pnl = (shares * (nav - prev)).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        if prev != ZERO:
                            pnl_pct = ((nav - prev) / prev * 100).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )

            results.append(
                CalendarDayDetail(
                    fund_code=h.fund_code,
                    fund_name=h.fund_name,
                    platform=h.platform,
                    shares=shares,
                    nav=nav,
                    prev_nav=prev,
                    daily_pnl=pnl,
                    daily_pnl_pct=pnl_pct,
                    market_value=mv,
                )
            )

        results.sort(
            key=lambda x: (x.daily_pnl is None, -(x.daily_pnl or ZERO)),
        )
        return results

    # ------------------------------------------------------------------
    # Shares reconstruction
    # ------------------------------------------------------------------

    def _load_import_timeline(self) -> list[ImportRecord]:
        """Load all successful import records ordered by data_date ASC."""
        return (
            self.db.query(ImportRecord)
            .filter(ImportRecord.status == "success")
            .order_by(ImportRecord.data_date.asc(), ImportRecord.id.asc())
            .all()
        )

    def _load_all_holding_changes(self) -> dict[tuple[int, int], HoldingChange]:
        """Load all holding_changes, keyed by (holding_id, import_id)."""
        rows = self.db.query(HoldingChange).all()
        return {(r.holding_id, r.import_id): r for r in rows}

    def _reconstruct_shares_timeline(
        self,
        holdings: list[FundHolding],
        imports: list[ImportRecord],
        changes_map: dict[tuple[int, int], HoldingChange],
    ) -> dict[int, dict[int, Decimal]]:
        """Rebuild shares at each import point for every holding.

        Returns {holding_id: {import_id: shares_at_that_point}}.
        Walks backwards from current shares, using holding_changes to
        reverse-apply each modification.
        """
        result: dict[int, dict[int, Decimal]] = {}

        for h in holdings:
            current = h.shares if h.shares is not None else ZERO
            timeline: dict[int, Decimal] = {}

            # Walk from most-recent import → earliest
            for imp in reversed(imports):
                change = changes_map.get((h.id, imp.id))
                if change is not None:
                    timeline[imp.id] = (
                        change.shares_after
                        if change.shares_after is not None
                        else ZERO
                    )
                    current = (
                        change.shares_before
                        if change.shares_before is not None
                        else ZERO
                    )
                else:
                    timeline[imp.id] = current

            result[h.id] = timeline

        return result

    def _get_effective_shares(
        self,
        target_date: date,
        holding_id: int,
        shares_timeline: dict[int, dict[int, Decimal]],
        imports: list[ImportRecord],
        changes_map: dict[tuple[int, int], HoldingChange],
    ) -> Decimal:
        """Get effective shares for a holding on a given date.

        Handles:
        - Before baseline → 0
        - Transition day (non-first import date with changes) → adjusted shares
        - Normal day → timeline shares from the applicable import
        """
        if not imports:
            return ZERO

        baseline_date = imports[0].data_date
        if target_date < baseline_date:
            return ZERO

        # Find applicable import: latest with data_date <= target_date
        applicable_import = None
        for imp in imports:
            if imp.data_date <= target_date:
                applicable_import = imp
            else:
                break

        if applicable_import is None:
            return ZERO

        timeline = shares_timeline.get(holding_id, {})
        base_shares = timeline.get(applicable_import.id, ZERO)

        # Transition day: target equals a non-first import's data_date
        if (
            target_date == applicable_import.data_date
            and applicable_import.id != imports[0].id
        ):
            change = changes_map.get((holding_id, applicable_import.id))
            if change is not None:
                before = (
                    change.shares_before
                    if change.shares_before is not None
                    else ZERO
                )
                after = (
                    change.shares_after
                    if change.shares_after is not None
                    else ZERO
                )
                ct = change.change_type
                if ct == "new":
                    return after
                elif ct == "clear":
                    return ZERO
                elif ct == "increase":
                    return before  # min(before, after)
                elif ct == "decrease":
                    return after  # min(before, after)

        return base_shares

    def _build_daily_shares_map(
        self,
        holdings: list[FundHolding],
        trading_dates: list[date],
        shares_timeline: dict[int, dict[int, Decimal]],
        imports: list[ImportRecord],
        changes_map: dict[tuple[int, int], HoldingChange],
    ) -> dict[date, dict[str, Decimal]]:
        """Build {date: {fund_code: aggregated_shares}} for each trading date."""
        result: dict[date, dict[str, Decimal]] = {}

        for td in trading_dates:
            fund_shares: dict[str, Decimal] = defaultdict(lambda: ZERO)
            for h in holdings:
                shares = self._get_effective_shares(
                    td, h.id, shares_timeline, imports, changes_map
                )
                if shares > ZERO:
                    fund_shares[h.fund_code] += shares
            if fund_shares:
                result[td] = dict(fund_shares)

        return result

    # ------------------------------------------------------------------
    # NAV helpers
    # ------------------------------------------------------------------

    def _build_nav_lookup(
        self,
        fund_codes: list[str],
        month_start: date,
        month_end: date,
    ) -> dict[tuple[str, date], Decimal]:
        """Load NAV records covering the month + a buffer before it."""
        buffer_start = month_start - timedelta(days=15)

        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                FundNavHistory.nav_date,
                FundNavHistory.unit_nav,
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date >= buffer_start,
                FundNavHistory.nav_date <= month_end,
            )
            .all()
        )
        return {(r.fund_code, r.nav_date): r.unit_nav for r in rows}

    def _find_prev_dates(
        self,
        fund_codes: list[str],
        trading_dates: list[date],
        month_start: date,
    ) -> dict[tuple[str, date], date | None]:
        """For each (fund_code, trading_date), find the previous date with NAV."""
        buffer_start = month_start - timedelta(days=15)

        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                FundNavHistory.nav_date,
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date >= buffer_start,
            )
            .order_by(FundNavHistory.fund_code, FundNavHistory.nav_date)
            .all()
        )

        fund_dates: dict[str, list[date]] = defaultdict(list)
        for r in rows:
            fund_dates[r.fund_code].append(r.nav_date)

        result: dict[tuple[str, date], date | None] = {}
        for fc in fund_codes:
            dates = fund_dates.get(fc, [])
            for td in trading_dates:
                prev = None
                for d in dates:
                    if d < td:
                        prev = d
                    else:
                        break
                result[(fc, td)] = prev

        return result

    def _build_summary(self, daily_data: list[CalendarDayData]) -> MonthSummary:
        if not daily_data:
            return MonthSummary()

        pnl_days = [d for d in daily_data if d.daily_pnl is not None]
        if not pnl_days:
            return MonthSummary(trading_days=len(daily_data))

        total = sum(d.daily_pnl for d in pnl_days)
        avg = (total / len(pnl_days)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        best = max(pnl_days, key=lambda d: d.daily_pnl)
        worst = min(pnl_days, key=lambda d: d.daily_pnl)

        return MonthSummary(
            total_pnl=total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            trading_days=len(pnl_days),
            avg_daily_pnl=avg,
            best_day=best,
            worst_day=worst,
        )

    def _get_nav_on_date(
        self, fund_codes: list[str], target_date: date
    ) -> dict[str, Decimal]:
        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                FundNavHistory.unit_nav,
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date == target_date,
            )
            .all()
        )
        return {r.fund_code: r.unit_nav for r in rows}

    def _get_prev_nav(
        self, fund_codes: list[str], target_date: date
    ) -> dict[str, Decimal]:
        """For each fund, get the unit_nav on the most recent date before target_date."""
        subq = (
            self.db.query(
                FundNavHistory.fund_code,
                func.max(FundNavHistory.nav_date).label("prev_date"),
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date < target_date,
            )
            .group_by(FundNavHistory.fund_code)
            .subquery()
        )

        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                FundNavHistory.unit_nav,
            )
            .join(
                subq,
                and_(
                    FundNavHistory.fund_code == subq.c.fund_code,
                    FundNavHistory.nav_date == subq.c.prev_date,
                ),
            )
            .all()
        )
        return {r.fund_code: r.unit_nav for r in rows}

    def _get_prev_date_map(
        self, fund_codes: list[str], target_date: date
    ) -> dict[str, date]:
        """For each fund, get the most recent NAV date before target_date."""
        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                func.max(FundNavHistory.nav_date).label("prev_date"),
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date < target_date,
            )
            .group_by(FundNavHistory.fund_code)
            .all()
        )
        return {r.fund_code: r.prev_date for r in rows if r.prev_date is not None}

    def _get_money_fund_codes(self) -> set[str]:
        """Get set of fund codes that are money market funds."""
        rows = self.db.execute(
            select(Fund.fund_code).where(Fund.fund_type == "货币型")
        ).scalars().all()
        return set(rows)
