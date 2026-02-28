"""NAV fetcher - fetches fund NAV from East Money API."""

import asyncio
import json
import logging
import random
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 东方财富历史净值接口
# 参数：fundCode=基金代码, pageIndex=页码, pageSize=每页条数
# 可选：startDate/endDate 限定日期范围
HISTORY_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
]


class NavData:
    """解析后的单条净值数据。"""

    def __init__(
        self,
        fund_code: str,
        nav_date: date,
        unit_nav: Decimal,
        acc_nav: Optional[Decimal] = None,
        change_pct: Optional[Decimal] = None,
        is_money_fund: bool = False,
    ):
        self.fund_code = fund_code
        self.nav_date = nav_date
        # 普通基金：单位净值；货币基金：每万份收益（元），不是净值
        self.unit_nav = unit_nav
        # 累计净值（成立以来每份累计收益），货币基金通常与单位净值相同
        self.acc_nav = acc_nav
        # 日涨跌幅（%），货币基金此字段通常为空或 0
        self.change_pct = change_pct
        # 是否货币基金（由接口返回的 SYType == "每万份收益" 判断）
        self.is_money_fund = is_money_fund


def _parse_jsonp(text: str) -> dict:
    """从 JSONP 响应中提取 JSON。"""
    match = re.search(r"\((\{.*\})\)", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(text)


def _random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://fund.eastmoney.com/",
    }


def _is_money_fund_by_sy_type(data: dict) -> bool:
    """根据接口返回的 SYType 字段判断是否为货币基金。

    lsjz 接口在 Data 层返回 SYType 字段：
      - 货币基金："每万份收益"（DWJZ 此时是万份收益，非单位净值）
      - 普通基金：None 或其他值
    """
    return data.get("Data", {}).get("SYType") == "每万份收益"


async def fetch_latest_nav(
    client: httpx.AsyncClient, fund_code: str
) -> Optional[NavData]:
    """获取单只基金的最新净值。"""
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
        logger.debug("[东财API] fetch_latest_nav %s 原始响应: %s", fund_code, resp.text[:500])
        data = _parse_jsonp(resp.text)

        items = data.get("Data", {}).get("LSJZList", [])
        if not items:
            return None

        # 判断货币基金（利用同一接口返回的 SYType，无需额外请求）
        is_money_fund = _is_money_fund_by_sy_type(data)

        item = items[0]
        # FSRQ: 份额日期（净值日期）
        nav_date_str = item.get("FSRQ", "")
        # DWJZ: 单位净值；货币基金为每万份收益（元）
        unit_nav_str = item.get("DWJZ", "")
        # LJJZ: 累计净值
        acc_nav_str = item.get("LJJZ", "")
        # JZZZL: 净值增长率（日涨跌幅%）；货币基金通常为空
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
            is_money_fund=is_money_fund,
        )
    except Exception:
        return None


async def fetch_history_nav(
    client: httpx.AsyncClient, fund_code: str, page_size: int = 30
) -> list[NavData]:
    """获取单只基金的历史净值列表。"""
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
        logger.debug("[东财API] fetch_history_nav %s 原始响应: %s", fund_code, resp.text[:500])
        data = _parse_jsonp(resp.text)

        # SYType 是基金级别属性，列表内所有条目共用同一判断
        is_money_fund = _is_money_fund_by_sy_type(data)

        items = data.get("Data", {}).get("LSJZList", [])
        results = []
        for item in items:
            # FSRQ: 净值日期
            nav_date_str = item.get("FSRQ", "")
            # DWJZ: 单位净值（货币基金为万份收益）
            unit_nav_str = item.get("DWJZ", "")
            # LJJZ: 累计净值
            acc_nav_str = item.get("LJJZ", "")
            # JZZZL: 日涨跌幅%
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
                is_money_fund=is_money_fund,
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
    """批量抓取多只基金净值，带限速。

    Args:
        fund_codes: 基金代码列表
        concurrency: 最大并发请求数
        interval: 每次请求间隔秒数
        history_days: >0 时抓取历史净值，否则只取最新一条

    Returns:
        fund_code -> [NavData] 的字典
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
                await asyncio.sleep(interval + random.uniform(0, 0.2))

        tasks = [_fetch_one(code) for code in fund_codes]
        await asyncio.gather(*tasks)

    return results
