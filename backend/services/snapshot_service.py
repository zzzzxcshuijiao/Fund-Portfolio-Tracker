"""Snapshot service - creates daily portfolio snapshots."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.holding_change import HoldingChange
from backend.models.holding_daily_pnl import HoldingDailyPnL
from backend.models.import_record import ImportRecord
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

        # Calculate total market value using real-time shares × latest_nav
        mv_rows = self.db.execute(
            select(FundHolding.shares, Fund.latest_nav, Fund.fund_type)
            .join(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        ).all()

        total_mv = Decimal("0")
        for shares, latest_nav, fund_type in mv_rows:
            if shares and latest_nav:
                if fund_type == "货币型":
                    total_mv += shares  # money fund: 1 share = 1 yuan
                else:
                    total_mv += shares * latest_nav

        total_count = self.db.execute(
            select(func.count())
            .select_from(FundHolding)
            .where(FundHolding.status == 1)
        ).scalar() or 0

        # Platform breakdown using real-time market value
        pb_rows = self.db.execute(
            select(FundHolding.platform, FundHolding.shares, Fund.latest_nav, Fund.fund_type)
            .join(Fund, FundHolding.fund_code == Fund.fund_code)
            .where(FundHolding.status == 1)
        ).all()

        platform_map: dict = {}
        for platform, shares, latest_nav, fund_type in pb_rows:
            mv = Decimal("0")
            if shares and latest_nav:
                mv = shares if fund_type == "货币型" else shares * latest_nav
            entry = platform_map.setdefault(platform, {"market_value": Decimal("0"), "count": 0})
            entry["market_value"] += mv
            entry["count"] += 1

        platform_breakdown = {
            p: {"market_value": float(e["market_value"]), "count": e["count"]}
            for p, e in platform_map.items()
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

        # Portfolio NAV calculation (time-weighted return)
        net_inflow = self._calculate_net_inflow(snapshot_date)

        if (
            prev_snapshot
            and prev_snapshot.portfolio_nav is not None
            and prev_snapshot.total_market_value
            and prev_snapshot.total_market_value > 0
        ):
            # Time-weighted: strip out new cash inflows to measure pure market return
            pure_mv = total_mv - net_inflow
            pure_return = (pure_mv - prev_snapshot.total_market_value) / prev_snapshot.total_market_value
            portfolio_nav = prev_snapshot.portfolio_nav * (1 + pure_return)
            # Issue new units at current NAV for the inflow
            new_units = net_inflow / portfolio_nav if portfolio_nav > 0 else Decimal("0")
            total_units = (prev_snapshot.total_units or Decimal("0")) + new_units
        else:
            # First snapshot: NAV = 1, units = total market value
            portfolio_nav = Decimal("1.000000")
            total_units = total_mv

        snapshot.portfolio_nav = portfolio_nav
        snapshot.total_units = total_units
        snapshot.net_inflow = net_inflow

        if not existing:
            self.db.add(snapshot)

        self.db.commit()
        self.db.refresh(snapshot)

        # Record per-holding daily PnL
        self._record_holding_daily_pnl(snapshot_date)

        return snapshot

    def _calculate_net_inflow(self, snapshot_date: date) -> Decimal:
        """Calculate net cash inflow for the given date from holding changes."""
        # Find import records whose data_date matches snapshot_date
        rows = self.db.execute(
            select(HoldingChange)
            .join(ImportRecord, HoldingChange.import_id == ImportRecord.id)
            .where(ImportRecord.data_date == snapshot_date)
        ).scalars().all()

        net_inflow = Decimal("0")
        for change in rows:
            if change.shares_delta is None or change.nav_at_change is None:
                continue
            # positive delta = buy (inflow), negative = sell (outflow)
            net_inflow += change.shares_delta * change.nav_at_change

        return net_inflow

    def backfill_portfolio_nav(self) -> None:
        """Backfill portfolio_nav, total_units, net_inflow for all existing snapshots in order."""
        snapshots = self.db.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.snapshot_date.asc())
        ).scalars().all()

        prev_snapshot = None
        for snapshot in snapshots:
            net_inflow = self._calculate_net_inflow(snapshot.snapshot_date)
            total_mv = snapshot.total_market_value or Decimal("0")

            if (
                prev_snapshot
                and prev_snapshot.portfolio_nav is not None
                and prev_snapshot.total_market_value
                and prev_snapshot.total_market_value > 0
            ):
                pure_mv = total_mv - net_inflow
                pure_return = (pure_mv - prev_snapshot.total_market_value) / prev_snapshot.total_market_value
                portfolio_nav = prev_snapshot.portfolio_nav * (1 + pure_return)
                new_units = net_inflow / portfolio_nav if portfolio_nav > 0 else Decimal("0")
                total_units = (prev_snapshot.total_units or Decimal("0")) + new_units
            else:
                portfolio_nav = Decimal("1.000000")
                total_units = total_mv

            snapshot.portfolio_nav = portfolio_nav
            snapshot.total_units = total_units
            snapshot.net_inflow = net_inflow

            prev_snapshot = snapshot

        self.db.commit()

    def backfill_historical_snapshots(self) -> int:
        """Create snapshots for each historical import date using mv_after from holding_changes.

        For each import date, reconstruct total market value by taking the latest known
        mv_after for every holding (using the most recent import up to that date).
        Returns the number of snapshots created.
        """
        # Get all distinct import dates in order
        import_dates = self.db.execute(
            select(ImportRecord.data_date)
            .where(ImportRecord.data_date.isnot(None))
            .distinct()
            .order_by(ImportRecord.data_date.asc())
        ).scalars().all()

        created = 0
        for data_date in import_dates:
            # Skip if snapshot already exists for this date
            existing = self.db.execute(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.snapshot_date == data_date)
            ).scalar_one_or_none()
            if existing:
                continue

            # Get max import_id for imports up to this date
            max_import_id = self.db.execute(
                select(func.max(ImportRecord.id))
                .where(ImportRecord.data_date <= data_date)
            ).scalar()
            if not max_import_id:
                continue

            # For each holding, get the mv_after from its most recent change
            # at or before this import date
            subq = (
                select(
                    HoldingChange.holding_id,
                    func.max(HoldingChange.import_id).label("last_import_id"),
                )
                .where(HoldingChange.import_id <= max_import_id)
                .where(HoldingChange.holding_id.isnot(None))
                .group_by(HoldingChange.holding_id)
                .subquery()
            )

            rows = self.db.execute(
                select(HoldingChange.mv_after, HoldingChange.change_type)
                .join(
                    subq,
                    (HoldingChange.holding_id == subq.c.holding_id)
                    & (HoldingChange.import_id == subq.c.last_import_id),
                )
            ).all()

            total_mv = Decimal("0")
            active_count = 0
            for mv_after, change_type in rows:
                if change_type != "clear" and mv_after:
                    total_mv += Decimal(str(mv_after))
                    active_count += 1

            snapshot = PortfolioSnapshot(
                snapshot_date=data_date,
                total_market_value=total_mv,
                total_shares_count=active_count,
            )
            self.db.add(snapshot)
            created += 1

        self.db.commit()

        # Recompute daily_pnl and portfolio_nav for all snapshots in order
        self._recompute_daily_pnl_and_nav()

        return created

    def backfill_all_daily_snapshots(self) -> int:
        """为 fund_nav_history 中所有 nav_date 创建或更新 portfolio_snapshots。

        使用 shares × unit_nav 计算历史市值（而非 mv_after），保证计算方式与实时快照一致。
        货币型基金市值 = shares × 1.0（不使用 fund_nav_history.unit_nav，因其为万份收益）。
        对已有快照则更新其 total_market_value 和 total_shares_count，
        最后调用 _recompute_daily_pnl_and_nav() 重算 daily_pnl 和 portfolio_nav。
        返回创建或更新的快照数量。
        """
        db = self.db

        # 取 fund_nav_history 中所有交易日
        nav_dates = db.execute(
            select(FundNavHistory.nav_date)
            .distinct()
            .order_by(FundNavHistory.nav_date.asc())
        ).scalars().all()

        if not nav_dates:
            return 0

        money_fund_codes = self._get_money_fund_codes()
        created_or_updated = 0

        for nav_date in nav_dates:
            # 获取该日各基金历史份额 {fund_code: total_shares}
            shares_map = self._get_shares_map_on_date(nav_date)
            if not shares_map:
                continue

            # 非货币型基金查历史净值（最近 nav_date <= nav_date）
            non_money_codes = [fc for fc in shares_map if fc not in money_fund_codes]
            nav_map: dict[str, Decimal] = {}
            if non_money_codes:
                nav_subq = (
                    select(
                        FundNavHistory.fund_code,
                        func.max(FundNavHistory.nav_date).label("latest_date"),
                    )
                    .where(
                        FundNavHistory.fund_code.in_(non_money_codes),
                        FundNavHistory.nav_date <= nav_date,
                    )
                    .group_by(FundNavHistory.fund_code)
                    .subquery()
                )
                nav_rows = db.execute(
                    select(FundNavHistory.fund_code, FundNavHistory.unit_nav)
                    .join(
                        nav_subq,
                        (FundNavHistory.fund_code == nav_subq.c.fund_code)
                        & (FundNavHistory.nav_date == nav_subq.c.latest_date),
                    )
                ).all()
                nav_map = {r.fund_code: r.unit_nav for r in nav_rows}

            # 计算总市值
            total_mv = Decimal("0")
            active_count = 0
            for fund_code, shares in shares_map.items():
                if fund_code in money_fund_codes:
                    total_mv += shares  # 货币型：1份 = 1元
                    active_count += 1
                elif fund_code in nav_map:
                    total_mv += shares * nav_map[fund_code]
                    active_count += 1
                # 无净值数据的基金跳过

            if total_mv == Decimal("0"):
                continue

            existing = db.execute(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.snapshot_date == nav_date)
            ).scalar_one_or_none()

            if existing:
                existing.total_market_value = total_mv
                existing.total_shares_count = active_count
            else:
                db.add(PortfolioSnapshot(
                    snapshot_date=nav_date,
                    total_market_value=total_mv,
                    total_shares_count=active_count,
                ))

            created_or_updated += 1

        db.commit()

        # 重算所有快照的 daily_pnl、daily_pnl_pct 和 portfolio_nav
        self._recompute_daily_pnl_and_nav()

        return created_or_updated

    def _recompute_daily_pnl_and_nav(self) -> None:
        """Recompute daily_pnl, daily_pnl_pct and portfolio_nav for all snapshots."""
        snapshots = self.db.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.snapshot_date.asc())
        ).scalars().all()

        prev = None
        for s in snapshots:
            total_mv = s.total_market_value or Decimal("0")

            # daily pnl
            if prev and prev.total_market_value and prev.total_market_value > 0:
                s.daily_pnl = total_mv - prev.total_market_value
                s.daily_pnl_pct = s.daily_pnl / prev.total_market_value * 100
            else:
                s.daily_pnl = None
                s.daily_pnl_pct = None

            # portfolio nav
            net_inflow = self._calculate_net_inflow(s.snapshot_date)
            s.net_inflow = net_inflow

            if prev and prev.portfolio_nav is not None and prev.total_market_value and prev.total_market_value > 0:
                pure_mv = total_mv - net_inflow
                pure_return = (pure_mv - prev.total_market_value) / prev.total_market_value
                s.portfolio_nav = prev.portfolio_nav * (1 + pure_return)
                new_units = net_inflow / s.portfolio_nav if s.portfolio_nav > 0 else Decimal("0")
                s.total_units = (prev.total_units or Decimal("0")) + new_units
            else:
                s.portfolio_nav = Decimal("1.000000")
                s.total_units = total_mv

            prev = s

        self.db.commit()

    def _record_holding_daily_pnl(self, snapshot_date: date) -> None:
        """Record daily PnL for each holding, using historical shares on snapshot_date.

        Uses holding_changes to reconstruct shares held on the given date,
        which fixes incorrect P&L when shares have changed since the historical date.
        Includes cleared holdings (status=0) that may have been active historically.
        """
        money_fund_codes = self._get_money_fund_codes()

        # 对每个 holding 找 data_date <= snapshot_date 范围内最近一次变更（按 import_id 最大）
        subq = (
            select(
                HoldingChange.holding_id,
                func.max(HoldingChange.import_id).label("last_import_id"),
            )
            .join(ImportRecord, HoldingChange.import_id == ImportRecord.id)
            .where(
                ImportRecord.data_date <= snapshot_date,
                HoldingChange.holding_id.isnot(None),
            )
            .group_by(HoldingChange.holding_id)
            .subquery()
        )

        hist_rows = self.db.execute(
            select(
                FundHolding.id,
                FundHolding.fund_code,
                HoldingChange.shares_after,
                HoldingChange.change_type,
            )
            .join(subq, FundHolding.id == subq.c.holding_id)
            .join(
                HoldingChange,
                (HoldingChange.holding_id == subq.c.holding_id)
                & (HoldingChange.import_id == subq.c.last_import_id),
            )
        ).all()

        # {holding_id: (fund_code, shares)} for holdings active on snapshot_date
        active_holdings: dict[int, tuple[str, Decimal]] = {}
        for holding_id, fund_code, shares_after, change_type in hist_rows:
            if change_type == "clear" or shares_after is None:
                continue
            s = Decimal(str(shares_after))
            if s > Decimal("0"):
                active_holdings[holding_id] = (fund_code, s)

        if not active_holdings:
            return

        # Prefetch fund.latest_nav for fallback when nav_history has no data
        all_fund_codes = {fc for _, (fc, _) in active_holdings.items()}
        fund_nav_fallback: dict[str, Decimal] = {}
        fund_rows = self.db.execute(
            select(Fund.fund_code, Fund.latest_nav)
            .where(Fund.fund_code.in_(all_fund_codes))
        ).all()
        for r in fund_rows:
            if r.latest_nav:
                fund_nav_fallback[r.fund_code] = r.latest_nav

        for holding_id, (fund_code, shares) in active_holdings.items():
            is_money = fund_code in money_fund_codes

            if is_money:
                nav = Decimal("1.0000")
                mv = shares  # each share = 1 yuan

                # Get the most recent DWJZ (万份收益) on or before snapshot_date.
                today_dwjz = self.db.execute(
                    select(FundNavHistory.unit_nav)
                    .where(
                        FundNavHistory.fund_code == fund_code,
                        FundNavHistory.nav_date <= snapshot_date,
                    )
                    .order_by(FundNavHistory.nav_date.desc())
                    .limit(1)
                ).scalar_one_or_none()

                if today_dwjz:
                    pnl = shares * today_dwjz / TEN_THOUSAND
                    pnl_pct = today_dwjz / TEN_THOUSAND * 100
                else:
                    pnl = None
                    pnl_pct = None
                prev_nav = None
            else:
                today_nav_row = self.db.execute(
                    select(FundNavHistory.unit_nav, FundNavHistory.nav_date)
                    .where(
                        FundNavHistory.fund_code == fund_code,
                        FundNavHistory.nav_date <= snapshot_date,
                    )
                    .order_by(FundNavHistory.nav_date.desc())
                    .limit(1)
                ).first()

                if today_nav_row:
                    nav = today_nav_row.unit_nav
                    current_nav_date = today_nav_row.nav_date
                elif fund_code in fund_nav_fallback:
                    nav = fund_nav_fallback[fund_code]
                    current_nav_date = snapshot_date
                else:
                    continue  # No NAV data available for this fund, skip

                mv = shares * nav

                # Get previous NAV strictly before current_nav_date
                prev_nav_row = self.db.execute(
                    select(FundNavHistory.unit_nav)
                    .where(
                        FundNavHistory.fund_code == fund_code,
                        FundNavHistory.nav_date < current_nav_date,
                    )
                    .order_by(FundNavHistory.nav_date.desc())
                    .limit(1)
                ).scalar_one_or_none()

                prev_nav = prev_nav_row
                pnl = None
                pnl_pct = None
                if prev_nav and prev_nav > 0:
                    pnl = shares * (nav - prev_nav)
                    pnl_pct = (nav - prev_nav) / prev_nav * 100

            # Upsert: check if record exists
            existing = self.db.execute(
                select(HoldingDailyPnL).where(
                    HoldingDailyPnL.holding_id == holding_id,
                    HoldingDailyPnL.pnl_date == snapshot_date,
                )
            ).scalar_one_or_none()

            if existing:
                existing.fund_code = fund_code
                existing.shares = shares
                existing.nav = nav
                existing.prev_nav = prev_nav
                existing.market_value = mv
                existing.daily_pnl = pnl
                existing.daily_pnl_pct = pnl_pct
            else:
                record = HoldingDailyPnL(
                    pnl_date=snapshot_date,
                    holding_id=holding_id,
                    fund_code=fund_code,
                    shares=shares,
                    nav=nav,
                    prev_nav=prev_nav,
                    market_value=mv,
                    daily_pnl=pnl,
                    daily_pnl_pct=pnl_pct,
                )
                self.db.add(record)

        self.db.commit()

    def backfill_holding_daily_pnl(self) -> int:
        """Backfill holding_daily_pnl for all dates that have NAV data in fund_nav_history.

        Iterates over every distinct nav_date in fund_nav_history and calls
        _record_holding_daily_pnl for each one. Existing records are updated in place.
        Returns the number of dates processed.
        """
        nav_dates = self.db.execute(
            select(FundNavHistory.nav_date)
            .distinct()
            .order_by(FundNavHistory.nav_date.asc())
        ).scalars().all()

        for pnl_date in nav_dates:
            self._record_holding_daily_pnl(pnl_date)

        return len(nav_dates)

    def _get_money_fund_codes(self) -> set[str]:
        """Get set of fund codes that are money market funds."""
        rows = self.db.execute(
            select(Fund.fund_code).where(Fund.fund_type == "货币型")
        ).scalars().all()
        return set(rows)

    def _get_shares_map_on_date(self, target_date: date) -> dict[str, Decimal]:
        """返回 {fund_code: total_shares}，表示 target_date 当日每个基金的持仓份额。

        通过查询 holding_changes + import_records，找到每个持仓在 target_date
        之前最近一次导入后的 shares_after。同一 fund_code 的多个持仓（不同平台/账户）
        份额累加合并。change_type == "clear" 或无记录的持仓份额视为 0。
        """
        db = self.db

        # 对每个 holding，找 data_date <= target_date 范围内 import_id 最大的那次变更
        subq = (
            select(
                HoldingChange.holding_id,
                func.max(HoldingChange.import_id).label("last_import_id"),
            )
            .join(ImportRecord, HoldingChange.import_id == ImportRecord.id)
            .where(
                ImportRecord.data_date <= target_date,
                HoldingChange.holding_id.isnot(None),
            )
            .group_by(HoldingChange.holding_id)
            .subquery()
        )

        rows = db.execute(
            select(
                FundHolding.fund_code,
                HoldingChange.shares_after,
                HoldingChange.change_type,
            )
            .join(subq, FundHolding.id == subq.c.holding_id)
            .join(
                HoldingChange,
                (HoldingChange.holding_id == subq.c.holding_id)
                & (HoldingChange.import_id == subq.c.last_import_id),
            )
        ).all()

        shares_map: dict[str, Decimal] = {}
        for fund_code, shares_after, change_type in rows:
            if change_type == "clear" or shares_after is None:
                continue
            s = Decimal(str(shares_after))
            if s > Decimal("0"):
                shares_map[fund_code] = shares_map.get(fund_code, Decimal("0")) + s

        return shares_map
