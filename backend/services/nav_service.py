"""NAV service - business logic for NAV updates."""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, func, distinct
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
