"""Import service - handles Excel upload, parse, and merge into database."""

import asyncio
import os
import shutil
from decimal import Decimal
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.models.fund import Fund
from backend.models.holding import FundHolding
from backend.models.holding_change import HoldingChange
from backend.models.import_record import ImportRecord
from backend.schemas.import_result import ImportResult, ImportHistoryItem
from backend.schemas.holding_change import HoldingChangeResponse
from backend.services.excel_parser import (
    parse_excel,
    compute_file_hash,
    ExcelParseError,
)

UPLOAD_DIR = Path("data/uploads")


class ImportService:
    def __init__(self, db: Session):
        self.db = db

    async def import_excel(self, file: UploadFile) -> ImportResult:
        """Upload Excel file, parse, and merge holdings into database."""
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # Save uploaded file
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Compute hash for duplicate detection
        file_hash = compute_file_hash(file_path)

        # Check for duplicate import
        existing = self.db.execute(
            select(ImportRecord).where(ImportRecord.file_hash == file_hash)
        ).scalar_one_or_none()
        if existing:
            os.remove(file_path)
            return ImportResult(
                import_id=existing.id,
                file_name=file.filename,
                total_rows=existing.total_rows,
                new_holdings=existing.new_holdings,
                updated_holdings=existing.updated_holdings,
                removed_holdings=existing.removed_holdings,
                error_rows=existing.error_rows,
                data_date=existing.data_date,
                status="duplicate",
                error_message="该文件已导入过",
            )

        # Parse Excel
        try:
            holdings, errors, data_date = parse_excel(file_path)
        except ExcelParseError as e:
            record = ImportRecord(
                file_name=file.filename,
                file_hash=file_hash,
                status="error",
                error_message=str(e),
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return ImportResult(
                import_id=record.id,
                file_name=file.filename,
                status="error",
                error_message=str(e),
            )

        # Create import record
        record = ImportRecord(
            file_name=file.filename,
            file_hash=file_hash,
            total_rows=len(holdings),
            error_rows=len(errors),
            data_date=data_date,
        )
        self.db.add(record)
        self.db.flush()  # get record.id

        # Merge holdings
        new_count, updated_count, removed_count, changes = self._merge_holdings(
            holdings, record.id
        )

        record.new_holdings = new_count
        record.updated_holdings = updated_count
        record.removed_holdings = removed_count
        record.status = "success"
        if errors:
            record.error_message = "; ".join(
                f"行{e['row']}: {e['message']}" for e in errors[:10]
            )

        self.db.commit()
        self.db.refresh(record)

        # Build change responses
        change_responses = [
            HoldingChangeResponse.model_validate(c) for c in changes
        ]

        return ImportResult(
            import_id=record.id,
            file_name=file.filename,
            total_rows=record.total_rows,
            new_holdings=new_count,
            updated_holdings=updated_count,
            removed_holdings=removed_count,
            error_rows=len(errors),
            data_date=data_date,
            status=record.status,
            error_message=record.error_message,
            changes=change_responses,
        )

    def _merge_holdings(
        self, holdings, import_id: int
    ) -> tuple[int, int, int, list[HoldingChange]]:
        """Merge parsed holdings into database.

        Strategy:
        - Existing key match -> update shares/nav/market_value
        - New key -> insert new holding + ensure fund exists
        - DB holdings not in Excel -> mark status=0 (cleared)

        Returns (new_count, updated_count, removed_count, changes).
        """
        new_count = 0
        updated_count = 0
        changes: list[HoldingChange] = []

        # Build set of keys from Excel
        excel_keys = set()
        for h in holdings:
            excel_keys.add(h.unique_key)

        # Process each holding
        for h in holdings:
            existing = self.db.execute(
                select(FundHolding).where(
                    FundHolding.fund_code == h.fund_code,
                    FundHolding.platform == h.platform,
                    FundHolding.fund_account == h.fund_account,
                    FundHolding.trade_account == h.trade_account,
                )
            ).scalar_one_or_none()

            if existing:
                old_shares = existing.shares or Decimal("0")
                old_mv = existing.market_value or Decimal("0")
                new_shares = h.shares
                new_mv = h.market_value or Decimal("0")
                was_cleared = existing.status == 0

                # Update existing holding
                existing.shares = h.shares
                existing.share_date = h.share_date
                existing.nav_on_import = h.nav
                existing.nav_date = h.nav_date
                existing.market_value = h.market_value
                existing.fund_name = h.fund_name
                existing.management_company = h.management_company
                existing.dividend_mode = h.dividend_mode
                existing.last_import_id = import_id
                existing.status = 1  # Re-activate if was cleared
                # Do NOT overwrite cost_nav on update
                updated_count += 1

                # Determine change type
                if was_cleared:
                    change_type = "new"
                    old_shares = Decimal("0")
                    old_mv = Decimal("0")
                elif new_shares > old_shares:
                    change_type = "increase"
                elif new_shares < old_shares:
                    change_type = "decrease"
                else:
                    change_type = None  # No change in shares

                if change_type:
                    change = HoldingChange(
                        import_id=import_id,
                        holding_id=existing.id,
                        fund_code=h.fund_code,
                        fund_name=h.fund_name,
                        platform=h.platform,
                        change_type=change_type,
                        shares_before=old_shares,
                        shares_after=new_shares,
                        shares_delta=new_shares - old_shares,
                        nav_at_change=h.nav,
                        mv_before=old_mv,
                        mv_after=new_mv,
                    )
                    self.db.add(change)
                    changes.append(change)
            else:
                # Insert new holding
                new_holding = FundHolding(
                    fund_code=h.fund_code,
                    fund_name=h.fund_name,
                    share_type=h.share_type,
                    management_company=h.management_company,
                    platform=h.platform,
                    fund_account=h.fund_account,
                    trade_account=h.trade_account,
                    shares=h.shares,
                    share_date=h.share_date,
                    nav_on_import=h.nav,
                    nav_date=h.nav_date,
                    market_value=h.market_value,
                    currency=h.currency,
                    dividend_mode=h.dividend_mode,
                    last_import_id=import_id,
                    status=1,
                    cost_nav=h.nav,  # Set cost_nav on first import
                )
                self.db.add(new_holding)
                self.db.flush()  # get new_holding.id
                new_count += 1

                change = HoldingChange(
                    import_id=import_id,
                    holding_id=new_holding.id,
                    fund_code=h.fund_code,
                    fund_name=h.fund_name,
                    platform=h.platform,
                    change_type="new",
                    shares_before=Decimal("0"),
                    shares_after=h.shares,
                    shares_delta=h.shares,
                    nav_at_change=h.nav,
                    mv_before=Decimal("0"),
                    mv_after=h.market_value or Decimal("0"),
                )
                self.db.add(change)
                changes.append(change)

            # Ensure fund exists in funds table
            self._ensure_fund(h)

        # Mark holdings not in Excel as cleared (status=0)
        all_active = self.db.execute(
            select(FundHolding).where(FundHolding.status == 1)
        ).scalars().all()

        removed_count = 0
        for holding in all_active:
            key = (
                holding.fund_code,
                holding.platform,
                holding.fund_account,
                holding.trade_account,
            )
            if key not in excel_keys:
                old_shares = holding.shares or Decimal("0")
                old_mv = holding.market_value or Decimal("0")
                holding.status = 0
                removed_count += 1

                change = HoldingChange(
                    import_id=import_id,
                    holding_id=holding.id,
                    fund_code=holding.fund_code,
                    fund_name=holding.fund_name,
                    platform=holding.platform,
                    change_type="clear",
                    shares_before=old_shares,
                    shares_after=Decimal("0"),
                    shares_delta=-old_shares,
                    nav_at_change=holding.nav_on_import,
                    mv_before=old_mv,
                    mv_after=Decimal("0"),
                )
                self.db.add(change)
                changes.append(change)

        self.db.flush()
        return new_count, updated_count, removed_count, changes

    def _ensure_fund(self, h) -> None:
        """Ensure fund exists in funds table, create if not."""
        from backend.services.nav_fetcher import fetch_fund_type_standalone

        existing = self.db.execute(
            select(Fund).where(Fund.fund_code == h.fund_code)
        ).scalar_one_or_none()

        if not existing:
            # Check if money market fund via API
            is_money = asyncio.get_event_loop().run_until_complete(
                fetch_fund_type_standalone(h.fund_code)
            )
            fund_type = "货币型" if is_money else None
            latest_nav = Decimal("1.0000") if is_money else h.nav

            fund = Fund(
                fund_code=h.fund_code,
                fund_name=h.fund_name,
                management_company=h.management_company,
                fund_type=fund_type,
                latest_nav=latest_nav,
                latest_nav_date=h.nav_date,
            )
            self.db.add(fund)
            self.db.flush()

    def get_import_history(self) -> list[ImportHistoryItem]:
        """Get all import records, newest first."""
        records = self.db.execute(
            select(ImportRecord).order_by(ImportRecord.created_at.desc())
        ).scalars().all()
        return [ImportHistoryItem.model_validate(r) for r in records]

    def get_import_changes(self, import_id: int) -> list[HoldingChangeResponse]:
        """Get holding changes for a specific import."""
        changes = self.db.execute(
            select(HoldingChange)
            .where(HoldingChange.import_id == import_id)
            .order_by(HoldingChange.change_type, HoldingChange.fund_code)
        ).scalars().all()
        return [HoldingChangeResponse.model_validate(c) for c in changes]
