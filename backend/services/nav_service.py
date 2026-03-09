"""NAV service - business logic for NAV updates."""

import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, func, distinct, case
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.nav_history import FundNavHistory
from backend.services.nav_fetcher import batch_fetch_nav, NavData
from backend.config import get_settings

logger = logging.getLogger(__name__)


class NavService:
    def __init__(self, db: Session):
        self.db = db

    def get_held_fund_codes(self) -> list[str]:
        """Get distinct fund codes from active holdings."""
        result = self.db.execute(
            select(distinct(FundHolding.fund_code)).where(FundHolding.status == 1)
        ).scalars().all()
        return list(result)

    async def refresh_all_nav(self) -> dict:
        """获取所有持仓基金的最新净值并更新数据库。"""
        settings = get_settings()
        fund_codes = self.get_held_fund_codes()
        if not fund_codes:
            return {"status": "no_holdings", "message": "没有持仓基金"}

        results = await batch_fetch_nav(
            fund_codes,
            concurrency=settings.NAV_FETCH_CONCURRENCY,
            interval=settings.NAV_FETCH_INTERVAL,
        )

        updated = 0
        failed = 0
        for code, navs in results.items():
            if navs and navs[0]:
                nav = navs[0]
                self._save_nav(nav)
                self._update_fund_nav(nav)
                updated += 1
            else:
                failed += 1

        self._recalculate_market_values()
        self.db.commit()

        return {
            "status": "success",
            "total": len(fund_codes),
            "updated": updated,
            "failed": failed,
            "timestamp": datetime.now().isoformat(),
        }

    async def backfill_history(self, days: int = 30) -> dict:
        """回填所有持仓基金的历史净值，从第一次导入日期开始。"""
        settings = get_settings()
        fund_codes = self.get_held_fund_codes()
        if not fund_codes:
            return {"status": "no_holdings"}

        # Use first import date as start, so we get exactly the data needed
        from backend.models.import_record import ImportRecord
        first_import_date = self.db.execute(
            select(func.min(ImportRecord.data_date))
            .where(ImportRecord.data_date.isnot(None))
        ).scalar()

        start_date = str(first_import_date) if first_import_date else None
        # page_size large enough to cover all trading days since start_date
        page_size = max(days, 300)

        results = await batch_fetch_nav(
            fund_codes,
            concurrency=settings.NAV_FETCH_CONCURRENCY,
            interval=settings.NAV_FETCH_INTERVAL,
            history_days=page_size,
            start_date=start_date,
        )

        total_saved = 0
        for code, navs in results.items():
            for nav in navs:
                self._save_nav(nav)
                total_saved += 1
            if navs:
                self._update_fund_nav(navs[0])

        self._recalculate_market_values()
        self.db.commit()

        return {
            "status": "success",
            "funds": len(fund_codes),
            "nav_records": total_saved,
            "start_date": start_date,
        }

    def _save_nav(self, nav: NavData) -> None:
        """Save NAV data to fund_nav_history (upsert)."""
        stmt = mysql_insert(FundNavHistory).values(
            fund_code=nav.fund_code,
            nav_date=nav.nav_date,
            unit_nav=nav.unit_nav,
            acc_nav=nav.acc_nav,
            change_pct=nav.change_pct,
        )
        stmt = stmt.on_duplicate_key_update(
            unit_nav=stmt.inserted.unit_nav,
            acc_nav=stmt.inserted.acc_nav,
            change_pct=stmt.inserted.change_pct,
        )
        self.db.execute(stmt)

    def _update_fund_nav(self, nav: NavData) -> None:
        """更新 funds 表中的最新净值缓存。

        货币基金特殊处理：
          - latest_nav 固定为 1.0000（每份面值 1 元）
          - nav_change_pct = 万份收益 / 10000 * 100，转换为日收益率%
          - fund_type 同步标记为 "货币型"
        """
        fund = self.db.execute(
            select(Fund).where(Fund.fund_code == nav.fund_code)
        ).scalar_one_or_none()
        if fund:
            if fund.latest_nav_date is None or nav.nav_date >= fund.latest_nav_date:
                if nav.is_money_fund:
                    fund.latest_nav = Decimal("1.0000")
                    # 万份收益（元）转日收益率：万份收益 / 10000 * 100
                    fund.nav_change_pct = nav.unit_nav / Decimal("10000") * 100
                    fund.fund_type = "货币型"
                else:
                    fund.latest_nav = nav.unit_nav
                    fund.nav_change_pct = nav.change_pct
                fund.latest_nav_date = nav.nav_date

    def _recalculate_market_values(self) -> None:
        """Recalculate market values for all active holdings using latest NAV."""
        money_fund_codes = self._get_money_fund_codes()

        holdings = self.db.execute(
            select(FundHolding).where(FundHolding.status == 1)
        ).scalars().all()

        for h in holdings:
            if h.fund_code in money_fund_codes:
                # Money market fund: each share = 1 yuan
                h.market_value = h.shares
            else:
                fund = self.db.execute(
                    select(Fund).where(Fund.fund_code == h.fund_code)
                ).scalar_one_or_none()
                if fund and fund.latest_nav:
                    h.market_value = h.shares * fund.latest_nav

    def _get_money_fund_codes(self) -> set[str]:
        """Get set of fund codes that are money market funds."""
        rows = self.db.execute(
            select(Fund.fund_code).where(Fund.fund_type == "货币型")
        ).scalars().all()
        return set(rows)

    def get_nav_history(self, fund_code: str, days: int = 90) -> list[dict]:
        """Get NAV history for a specific fund."""
        cutoff = date.today() - timedelta(days=days)
        records = self.db.execute(
            select(FundNavHistory)
            .where(
                FundNavHistory.fund_code == fund_code,
                FundNavHistory.nav_date >= cutoff,
            )
            .order_by(FundNavHistory.nav_date.asc())
        ).scalars().all()

        return [
            {
                "date": str(r.nav_date),
                "unit_nav": float(r.unit_nav),
                "acc_nav": float(r.acc_nav) if r.acc_nav else None,
                "change_pct": float(r.change_pct) if r.change_pct else None,
            }
            for r in records
        ]

    def has_today_nav(self, today: date) -> bool:
        """Return True if all active funds already have NAV data for today."""
        fund_codes = self.get_held_fund_codes()
        if not fund_codes:
            return True

        count_today = self.db.execute(
            select(func.count(distinct(FundNavHistory.fund_code)))
            .where(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date == today,
            )
        ).scalar() or 0

        return count_today >= len(fund_codes)

    def get_nav_status(self) -> dict:
        """Get latest NAV update status."""
        # Get the latest NAV date across all funds
        latest = self.db.execute(
            select(func.max(FundNavHistory.nav_date))
        ).scalar()

        # Count funds with NAV
        total_funds = self.db.execute(
            select(func.count(distinct(FundHolding.fund_code)))
            .where(FundHolding.status == 1)
        ).scalar()

        funds_with_nav = self.db.execute(
            select(func.count(distinct(Fund.fund_code)))
            .where(Fund.latest_nav.isnot(None))
        ).scalar()

        return {
            "latest_nav_date": str(latest) if latest else None,
            "total_funds": total_funds or 0,
            "funds_with_nav": funds_with_nav or 0,
            "funds_missing_nav": (total_funds or 0) - (funds_with_nav or 0),
        }

    def get_latest_trading_date(self) -> date | None:
        """获取数据库中最新的交易日（有NAV数据的日期）。

        返回所有基金中最新的 nav_date。
        """
        return self.db.execute(
            select(func.max(FundNavHistory.nav_date))
        ).scalar()

    def get_missing_date_range(
        self, from_date: date | None, to_date: date | None
    ) -> list[date]:
        """获取指定日期范围内缺失的交易日列表。

        一个日期被认为是"缺失的"，如果：
        - 任何持仓基金在该日期没有 NAV 数据

        Args:
            from_date: 起始日期（包含），如果为 None 则使用最早的 NAV 日期
            to_date: 结束日期（包含），如果为 None 则返回所有缺失日期

        Returns:
            缺失的交易日列表，按时间顺序排列
        """
        if to_date is None:
            to_date = date.today()

        # 确定起始日期
        if from_date is None:
            # 使用最早的 NAV 日期
            earliest = self.db.execute(
                select(func.min(FundNavHistory.nav_date))
            ).scalar()
            if earliest is None:
                return []
            from_date = earliest

        fund_codes = self.get_held_fund_codes()
        if not fund_codes:
            return []

        # 查询在指定日期范围内有 NAV 数据的日期
        existing_dates = self.db.execute(
            select(distinct(FundNavHistory.nav_date))
            .where(
                FundNavHistory.fund_code.in_(fund_codes),
                FundNavHistory.nav_date >= from_date,
                FundNavHistory.nav_date <= to_date,
            )
        ).scalars().all()

        existing_set = set(existing_dates)

        # 找出缺失的日期：在 from_date 到 to_date 之间的工作日
        missing = []
        current = from_date
        while current <= to_date:
            # 只考虑工作日（周一到周五）
            if current.weekday() < 5:  # 0-4 是周一到周五
                if current not in existing_set:
                    missing.append(current)
            current += timedelta(days=1)

        return missing

    async def refresh_all_nav_smart(self) -> dict:
        """智能刷新所有持仓基金的净值数据。

        策略：
        1. 首先获取最新交易日的净值（优先级最高）
        2. 然后后台异步获取从上次更新到最新交易日之间缺失的日期

        Returns:
            包含更新状态的字典
        """
        settings = get_settings()
        fund_codes = self.get_held_fund_codes()
        if not fund_codes:
            return {"status": "no_holdings", "message": "没有持仓基金"}

        # Step 1: 获取最新交易日的净值（优先）
        logger.info("Step 1: Fetching latest trading day NAV...")
        results = await batch_fetch_nav(
            fund_codes,
            concurrency=settings.NAV_FETCH_CONCURRENCY,
            interval=settings.NAV_FETCH_INTERVAL,
        )

        updated = 0
        failed = 0
        for code, navs in results.items():
            if navs and navs[0]:
                nav = navs[0]
                self._save_nav(nav)
                self._update_fund_nav(nav)
                updated += 1
            else:
                failed += 1

        self._recalculate_market_values()
        self.db.commit()

        # Step 2: 找出缺失的日期范围并后台异步获取
        latest_trading_date = self.get_latest_trading_date()
        if latest_trading_date:
            # 获取最新 NAV 日期（用于确定从哪天开始补）
            latest_nav_in_db = self.db.execute(
                select(func.max(Fund.latest_nav_date))
            ).scalar()

            if latest_nav_in_db and latest_nav_in_db < latest_trading_date:
                # 有缺失日期，启动后台任务补全
                missing_dates = self.get_missing_date_range(
                    from_date=latest_nav_in_db + timedelta(days=1),
                    to_date=latest_trading_date,
                )
                if missing_dates:
                    logger.info(
                        f"Step 2: Found {len(missing_dates)} missing dates, "
                        f"starting backfill from {missing_dates[0]} to {missing_dates[-1]}"
                    )
                    # 启动后台任务（不等待完成）
                    asyncio.create_task(
                        self._backfill_missing_dates(missing_dates)
                    )
                    return {
                        "status": "success",
                        "total": len(fund_codes),
                        "updated": updated,
                        "failed": failed,
                        "missing_dates_count": len(missing_dates),
                        "backfill_started": True,
                        "timestamp": datetime.now().isoformat(),
                    }

        return {
            "status": "success",
            "total": len(fund_codes),
            "updated": updated,
            "failed": failed,
            "timestamp": datetime.now().isoformat(),
        }

    async def _backfill_missing_dates(self, missing_dates: list[date]) -> None:
        """后台任务：补全指定日期范围的净值数据。

        Args:
            missing_dates: 需要补全的日期列表
        """
        settings = get_settings()
        fund_codes = self.get_held_fund_codes()

        if not fund_codes or not missing_dates:
            return

        logger.info(f"Backfill task: processing {len(missing_dates)} dates...")

        for target_date in missing_dates:
            try:
                # 按日期获取历史数据
                date_str = str(target_date)
                results = await batch_fetch_nav(
                    fund_codes,
                    concurrency=settings.NAV_FETCH_CONCURRENCY,
                    interval=settings.NAV_FETCH_INTERVAL,
                    start_date=date_str,
                    end_date=date_str,
                )

                saved = 0
                for code, navs in results.items():
                    for nav in navs:
                        self._save_nav(nav)
                        saved += 1
                    # 更新基金最新净值缓存（如果这个日期更新）
                    if navs:
                        self._update_fund_nav(navs[0])

                if saved > 0:
                    self.db.commit()
                    logger.info(
                        f"Backfill: {target_date} - saved {saved} NAV records"
                    )
                else:
                    logger.info(f"Backfill: {target_date} - no data available")

                # 短暂延迟，避免请求过快
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Backfill error for {target_date}: {e}")
                self.db.rollback()

        logger.info("Backfill task completed")
