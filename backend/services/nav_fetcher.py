"""NAV fetcher - fetches fund NAV from East Money API."""

import asyncio
import json
import random
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

# East Money API endpoints
HISTORY_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
REALTIME_NAV_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
FUND_INFO_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
]


class NavData:
    """Parsed NAV data point."""

    def __init__(
        self,
        fund_code: str,
        nav_date: date,
        unit_nav: Decimal,
        acc_nav: Optional[Decimal] = None,
        change_pct: Optional[Decimal] = None,
    ):
        self.fund_code = fund_code
        self.nav_date = nav_date
        self.unit_nav = unit_nav
        self.acc_nav = acc_nav
        self.change_pct = change_pct


def _parse_jsonp(text: str) -> dict:
    """Extract JSON from JSONP response."""
    match = re.search(r"\((\{.*\})\)", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Try parsing as plain JSON
    return json.loads(text)


def _random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://fund.eastmoney.com/",
    }


async def fetch_fund_type(client: httpx.AsyncClient, fund_code: str) -> bool:
    """Check if a fund is a money market fund via East Money API.

    Requests pingzhongdata/{code}.js and extracts the `ishb` variable.
    Returns True if money market fund, False otherwise.
    """
    url = FUND_INFO_URL.format(code=fund_code)
    try:
        resp = await client.get(url, headers=_random_headers(), timeout=10.0)
        resp.raise_for_status()
        match = re.search(r"var\s+ishb\s*=\s*(true|false)", resp.text)
        if match:
            return match.group(1) == "true"
    except Exception:
        pass
    return False


async def fetch_fund_type_standalone(fund_code: str) -> bool:
    """Standalone version of fetch_fund_type (creates its own client)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await fetch_fund_type(client, fund_code)


async def fetch_latest_nav(
    client: httpx.AsyncClient, fund_code: str
) -> Optional[NavData]:
    """Fetch the latest NAV for a single fund."""
    params = {
        "fundCode": fund_code,
        "pageIndex": 1,
        "pageSize": 1,
    }
    try:
        resp = await client.get(
            HISTORY_NAV_URL, params=params, headers=_random_headers()
        )
        resp.raise_for_status()
        data = _parse_jsonp(resp.text)

        items = data.get("Data", {}).get("LSJZList", [])
        if not items:
            return None

        item = items[0]
        nav_date_str = item.get("FSRQ", "")
        unit_nav_str = item.get("DWJZ", "")
        acc_nav_str = item.get("LJJZ", "")
        change_pct_str = item.get("JZZZL", "")

        nav_date = datetime.strptime(nav_date_str, "%Y-%m-%d").date()
        unit_nav = Decimal(unit_nav_str) if unit_nav_str else None
        if unit_nav is None:
            return None

        acc_nav = None
        if acc_nav_str:
            try:
                acc_nav = Decimal(acc_nav_str)
            except InvalidOperation:
                pass

        change_pct = None
        if change_pct_str:
            try:
                change_pct = Decimal(change_pct_str)
            except InvalidOperation:
                pass

        return NavData(
            fund_code=fund_code,
            nav_date=nav_date,
            unit_nav=unit_nav,
            acc_nav=acc_nav,
            change_pct=change_pct,
        )
    except Exception:
        return None


async def fetch_history_nav(
    client: httpx.AsyncClient, fund_code: str, page_size: int = 30
) -> list[NavData]:
    """Fetch historical NAV data for a fund."""
    params = {
        "fundCode": fund_code,
        "pageIndex": 1,
        "pageSize": page_size,
    }
    try:
        resp = await client.get(
            HISTORY_NAV_URL, params=params, headers=_random_headers()
        )
        resp.raise_for_status()
        data = _parse_jsonp(resp.text)

        items = data.get("Data", {}).get("LSJZList", [])
        results = []
        for item in items:
            nav_date_str = item.get("FSRQ", "")
            unit_nav_str = item.get("DWJZ", "")
            acc_nav_str = item.get("LJJZ", "")
            change_pct_str = item.get("JZZZL", "")

            try:
                nav_date = datetime.strptime(nav_date_str, "%Y-%m-%d").date()
                unit_nav = Decimal(unit_nav_str)
            except (ValueError, InvalidOperation):
                continue

            acc_nav = None
            if acc_nav_str:
                try:
                    acc_nav = Decimal(acc_nav_str)
                except InvalidOperation:
                    pass

            change_pct = None
            if change_pct_str:
                try:
                    change_pct = Decimal(change_pct_str)
                except InvalidOperation:
                    pass

            results.append(NavData(
                fund_code=fund_code,
                nav_date=nav_date,
                unit_nav=unit_nav,
                acc_nav=acc_nav,
                change_pct=change_pct,
            ))
        return results
    except Exception:
        return []


async def batch_fetch_nav(
    fund_codes: list[str],
    concurrency: int = 5,
    interval: float = 0.5,
    history_days: int = 0,
) -> dict[str, list[NavData]]:
    """Batch fetch NAV for multiple funds with rate limiting.

    Args:
        fund_codes: List of fund codes to fetch
        concurrency: Max concurrent requests
        interval: Delay between requests in seconds
        history_days: If > 0, fetch history; otherwise just latest

    Returns:
        Dict mapping fund_code -> list of NavData
    """
    results: dict[str, list[NavData]] = {}
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=30.0) as client:

        async def _fetch_one(code: str):
            async with semaphore:
                if history_days > 0:
                    navs = await fetch_history_nav(client, code, history_days)
                    results[code] = navs
                else:
                    nav = await fetch_latest_nav(client, code)
                    results[code] = [nav] if nav else []
                # Rate limiting
                await asyncio.sleep(interval + random.uniform(0, 0.2))

        tasks = [_fetch_one(code) for code in fund_codes]
        await asyncio.gather(*tasks)

    return results
