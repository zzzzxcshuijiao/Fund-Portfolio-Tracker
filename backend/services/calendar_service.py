"""Calendar service - compute daily portfolio PnL from NAV history."""

import calendar
from bisect import bisect_left, bisect_right
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
    DayTotalSummary,
    AccountAsset,
    DayTradeItem,
    CalendarDayResponse,
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

        # 4. NAV lookup – per-fund sorted timeline for "on-or-before" queries.
        #    Falls back to the most recent trading day when exact date has no data.
        nav_timeline = self._build_nav_lookup(all_fund_codes, month_start, month_end)

        # 4b. For funds completely absent from fund_nav_history (e.g. alternative
        #     investment products not covered by East Money), inject a synthetic
        #     entry using the holding's nav_on_import so market value is still shown.
        funds_no_nav = [fc for fc in all_fund_codes
                        if not nav_timeline.get(fc) and fc not in money_fund_codes]
        if funds_no_nav:
            fallback_nav = self._get_import_nav_fallback(funds_no_nav)
            synth_date = month_start - timedelta(days=1)
            for fc, fv in fallback_nav.items():
                nav_timeline[fc] = [(synth_date, fv)]

        # 5. Trading dates in the month (dates with at least one NAV record)
        trading_dates = sorted(
            {d for entries in nav_timeline.values()
             for d, _ in entries if month_start <= d <= month_end}
        )

        # 6. Previous trading date per (fund, date) – reuse timeline data
        all_dates_with_prev = self._find_prev_dates(
            all_fund_codes, trading_dates, month_start, nav_timeline
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

                # Use most recent available NAV on or before td
                nav_today = self._nav_on_or_before(nav_timeline, fc, td)
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
                        nav_prev = self._nav_on_or_before(nav_timeline, fc, prev_date)
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

        # 10. Trade dates (non-money-fund share changes in this month)
        trade_dates = self._load_trade_dates(month_start, month_end, money_fund_codes)

        return CalendarMonthResponse(
            year=year,
            month=month,
            summary=summary,
            daily_data=daily_data,
            trade_dates=sorted(d.isoformat() for d in trade_dates),
        )

    def get_day_detail(self, target_date: date) -> CalendarDayResponse:
        """Return full day detail: summary, per-account assets, trades, per-holding PnL."""
        imports = self._load_import_timeline()
        if not imports:
            return CalendarDayResponse(
                date=target_date,
                summary=DayTotalSummary(total_market_value=ZERO),
                accounts=[], trades=[], holdings=[],
            )

        baseline_date = imports[0].data_date
        if target_date < baseline_date:
            return CalendarDayResponse(
                date=target_date,
                summary=DayTotalSummary(total_market_value=ZERO),
                accounts=[], trades=[], holdings=[],
            )

        changes_map = self._load_all_holding_changes()

        # All holdings (including cleared – they may have been active on target_date)
        holdings = self.db.query(FundHolding).all()
        if not holdings:
            return CalendarDayResponse(
                date=target_date,
                summary=DayTotalSummary(total_market_value=ZERO),
                accounts=[], trades=[], holdings=[],
            )

        # Money fund codes
        money_fund_codes = self._get_money_fund_codes()

        shares_timeline = self._reconstruct_shares_timeline(
            holdings, imports, changes_map
        )

        fund_codes = list({h.fund_code for h in holdings})

        # NAV must come from fund_nav_history (API source); import NAV is for
        # validation only and must NOT be used as a data source.
        # Returns {fund_code: (unit_nav, actual_nav_date)}.
        nav_today_map = self._get_nav_on_date(fund_codes, target_date)

        # Import NAV for validation: compare against API nav when both exist
        # and the API returned the exact requested date (not a fallback date).
        import_nav_map = self._get_import_navs_for_date(fund_codes, target_date)

        prev_nav_map = self._get_prev_nav(fund_codes, target_date)
        prev_date_map = self._get_prev_date_map(fund_codes, target_date)

        results: list[CalendarDayDetail] = []
        for h in holdings:
            shares = self._get_effective_shares(
                target_date, h.id, shares_timeline, imports, changes_map
            )
            if shares <= ZERO:
                continue

            nav_entry = nav_today_map.get(h.fund_code)  # (nav, actual_nav_date) or None
            if nav_entry is not None:
                nav, nav_today_date = nav_entry
            elif h.fund_code not in money_fund_codes and h.nav_on_import is not None:
                # Fallback for funds not in fund_nav_history (e.g. alternative
                # investment products not covered by East Money API).
                nav = h.nav_on_import
                nav_today_date = None  # signals "import-based estimate, no API date"
            else:
                nav = None
                nav_today_date = None

            # Validate import nav vs API nav (only when API has the exact date)
            import_nav = import_nav_map.get(h.fund_code)
            nav_mismatch: bool | None = None
            if import_nav is not None and nav is not None and nav_today_date == target_date:
                api_r = nav.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                imp_r = import_nav.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                nav_mismatch = api_r != imp_r

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
                    fund_account=h.fund_account,
                    shares=shares,
                    nav=nav,
                    nav_date=nav_today_date,
                    prev_nav=prev,
                    import_nav=import_nav,
                    nav_mismatch=nav_mismatch,
                    daily_pnl=pnl,
                    daily_pnl_pct=pnl_pct,
                    market_value=mv,
                )
            )

        results.sort(
            key=lambda x: (x.daily_pnl is None, -(x.daily_pnl or ZERO)),
        )

        # --- Build total summary ---
        total_mv = sum(
            (r.market_value for r in results if r.market_value is not None), ZERO
        )
        pnl_vals = [r.daily_pnl for r in results if r.daily_pnl is not None]
        total_pnl: Decimal | None = sum(pnl_vals, ZERO) if pnl_vals else None

        day_pnl_pct: Decimal | None = None
        if total_pnl is not None and (total_mv - total_pnl) != ZERO:
            day_pnl_pct = (total_pnl / (total_mv - total_pnl) * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        summary = DayTotalSummary(
            total_market_value=total_mv.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            total_daily_pnl=total_pnl.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ) if total_pnl is not None else None,
            daily_pnl_pct=day_pnl_pct,
        )

        # --- Build per-platform breakdown ---
        from collections import defaultdict as _dd
        acct_mv: dict[str, Decimal] = _dd(lambda: ZERO)
        acct_pnl: dict[str, Decimal] = _dd(lambda: ZERO)
        acct_has_pnl: set[str] = set()

        for r in results:
            key = r.platform or ""
            if r.market_value is not None:
                acct_mv[key] += r.market_value
            if r.daily_pnl is not None:
                acct_pnl[key] += r.daily_pnl
                acct_has_pnl.add(key)

        accounts = [
            AccountAsset(
                platform=k,
                market_value=acct_mv[k].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                daily_pnl=acct_pnl[k].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ) if k in acct_has_pnl else None,
            )
            for k in sorted(acct_mv.keys())
        ]

        # --- Load trade changes for this day ---
        trades = self._load_day_trades(target_date)

        return CalendarDayResponse(
            date=target_date,
            summary=summary,
            accounts=accounts,
            trades=trades,
            holdings=results,
        )

    # ------------------------------------------------------------------
    # Shares reconstruction
    # ------------------------------------------------------------------

    def _load_day_trades(self, target_date: date) -> list[DayTradeItem]:
        """Load all holding changes whose import data_date == target_date."""
        rows = (
            self.db.query(
                HoldingChange.fund_code,
                HoldingChange.fund_name,
                HoldingChange.platform,
                HoldingChange.change_type,
                HoldingChange.shares_before,
                HoldingChange.shares_after,
                HoldingChange.shares_delta,
                HoldingChange.nav_at_change,
                HoldingChange.mv_before,
                HoldingChange.mv_after,
                FundHolding.fund_account,
            )
            .outerjoin(FundHolding, HoldingChange.holding_id == FundHolding.id)
            .join(ImportRecord, HoldingChange.import_id == ImportRecord.id)
            .filter(ImportRecord.data_date == target_date)
            .order_by(HoldingChange.platform, HoldingChange.fund_code)
            .all()
        )
        return [
            DayTradeItem(
                fund_code=r.fund_code,
                fund_name=r.fund_name,
                platform=r.platform,
                fund_account=r.fund_account,
                change_type=r.change_type,
                shares_before=r.shares_before,
                shares_after=r.shares_after,
                shares_delta=r.shares_delta,
                nav_at_change=r.nav_at_change,
                mv_before=r.mv_before,
                mv_after=r.mv_after,
            )
            for r in rows
        ]

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
            # Cleared holdings (status=0) have 0 shares at the current point.
            # fund_holdings.shares is NOT zeroed on clear (data bug), so we
            # override here to prevent ghost positions in historical timelines.
            if h.status == 0:
                current = ZERO
            else:
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
                    return after
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
    ) -> dict[str, list[tuple[date, Decimal]]]:
        """Load NAV records covering the month + a 15-day buffer before.

        Returns {fund_code: [(nav_date, unit_nav), ...]} sorted by date ascending.
        Use _nav_on_or_before() to query the most recent available NAV for any date,
        which handles non-trading days and delayed NAV publication transparently.
        """
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
            .order_by(FundNavHistory.fund_code, FundNavHistory.nav_date)
            .all()
        )

        result: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
        for r in rows:
            result[r.fund_code].append((r.nav_date, r.unit_nav))
        return dict(result)

    @staticmethod
    def _nav_on_or_before(
        nav_timeline: dict[str, list[tuple[date, Decimal]]],
        fund_code: str,
        target_date: date,
    ) -> Decimal | None:
        """Return the most recent unit_nav for fund_code on or before target_date.

        Falls back to the latest available trading day when the exact date has no
        data (non-trading day, delayed NAV publication, QDII different schedule, etc.).
        """
        entries = nav_timeline.get(fund_code, [])
        if not entries:
            return None
        dates = [e[0] for e in entries]
        pos = bisect_right(dates, target_date) - 1
        if pos < 0:
            return None
        return entries[pos][1]

    def _find_prev_dates(
        self,
        fund_codes: list[str],
        trading_dates: list[date],
        month_start: date,
        nav_timeline: dict[str, list[tuple[date, Decimal]]] | None = None,
    ) -> dict[tuple[str, date], date | None]:
        """For each (fund_code, trading_date), find the previous date with NAV."""
        if nav_timeline is not None:
            # Reuse already-loaded timeline to avoid a duplicate DB query
            fund_dates: dict[str, list[date]] = {
                fc: [d for d, _ in entries]
                for fc, entries in nav_timeline.items()
            }
        else:
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
            _fd: dict[str, list[date]] = defaultdict(list)
            for r in rows:
                _fd[r.fund_code].append(r.nav_date)
            fund_dates = dict(_fd)

        result: dict[tuple[str, date], date | None] = {}
        for fc in fund_codes:
            dates = fund_dates.get(fc, [])
            for td in trading_dates:
                # bisect_left gives the index of the leftmost position >= td,
                # so idx-1 is the last position strictly less than td.
                idx = bisect_left(dates, td) - 1
                result[(fc, td)] = dates[idx] if idx >= 0 else None

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
    ) -> dict[str, tuple[Decimal, date]]:
        """Get the most recent NAV for each fund on or before target_date.

        Falls back to the latest available trading day when the exact date has no
        data (non-trading day, delayed NAV publication, QDII different schedule, etc.).

        Returns {fund_code: (unit_nav, actual_nav_date)}.
        """
        subq = (
            self.db.query(
                FundNavHistory.fund_code,
                func.max(FundNavHistory.nav_date).label("latest_date"),
            )
            .filter(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date <= target_date,
            )
            .group_by(FundNavHistory.fund_code)
            .subquery()
        )
        rows = (
            self.db.query(
                FundNavHistory.fund_code,
                FundNavHistory.unit_nav,
                FundNavHistory.nav_date,
            )
            .join(
                subq,
                and_(
                    FundNavHistory.fund_code == subq.c.fund_code,
                    FundNavHistory.nav_date == subq.c.latest_date,
                ),
            )
            .all()
        )
        return {r.fund_code: (r.unit_nav, r.nav_date) for r in rows}

    def _get_import_navs_for_date(
        self, fund_codes: list[str], target_date: date
    ) -> dict[str, Decimal]:
        """Get nav_at_change from holding_changes for imports whose data_date == target_date.

        This uses the Excel-imported NAV as the source of truth for import dates.
        Only returns values when there's an explicit change record (new/increase/decrease).
        Excludes 'clear' type changes (where holdings were sold off).
        """
        rows = (
            self.db.query(HoldingChange.fund_code, HoldingChange.nav_at_change)
            .join(ImportRecord, HoldingChange.import_id == ImportRecord.id)
            .filter(
                ImportRecord.data_date == target_date,
                HoldingChange.fund_code.in_(fund_codes),
                HoldingChange.nav_at_change.isnot(None),
                HoldingChange.change_type != "clear",
            )
            .all()
        )
        # If multiple changes for same fund (unlikely), take the last one
        result: dict[str, Decimal] = {}
        for r in rows:
            result[r.fund_code] = r.nav_at_change
        return result

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

    def _get_import_nav_fallback(self, fund_codes: list[str]) -> dict[str, Decimal]:
        """For funds not covered by East Money API, return the most recent
        nav_on_import from active holdings as a market-value estimate.

        Used when fund_nav_history has no records for a fund (e.g. bank-issued
        alternative investment products that East Money does not index).
        """
        rows = (
            self.db.query(
                FundHolding.fund_code,
                func.max(FundHolding.nav_on_import).label("nav"),
            )
            .filter(
                FundHolding.fund_code.in_(fund_codes),
                FundHolding.status == 1,
                FundHolding.nav_on_import.isnot(None),
            )
            .group_by(FundHolding.fund_code)
            .all()
        )
        return {r.fund_code: r.nav for r in rows if r.nav is not None}

    def _load_trade_dates(
        self,
        month_start: date,
        month_end: date,
        money_fund_codes: set[str],
    ) -> set[date]:
        """Query dates in the month where non-money-fund holdings had share changes."""
        query = (
            self.db.query(ImportRecord.data_date)
            .join(HoldingChange, HoldingChange.import_id == ImportRecord.id)
            .filter(
                ImportRecord.data_date >= month_start,
                ImportRecord.data_date <= month_end,
                HoldingChange.change_type.in_(["new", "increase", "decrease", "clear"]),
            )
        )
        if money_fund_codes:
            query = query.filter(
                ~HoldingChange.fund_code.in_(money_fund_codes)
            )
        rows = query.distinct().all()
        return {r.data_date for r in rows}
