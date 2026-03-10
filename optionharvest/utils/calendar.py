"""
Trading calendar using Alpaca's market clock API.

No hardcoded holidays — Alpaca tells us if the market is open.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.api.client import AlpacaClient

log = get_logger("calendar")

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    """Current time in Eastern Time."""
    return datetime.now(ET)


class TradingCalendar:
    """Check market status via Alpaca's clock API."""

    def __init__(self, client: "AlpacaClient") -> None:
        self.client = client

    def get_clock(self) -> dict:
        """Get current market clock."""
        clock = self.client.trading.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": clock.next_open,
            "next_close": clock.next_close,
        }

    def is_market_open(self) -> bool:
        """Is the market open right now?"""
        return self.get_clock()["is_open"]

    def is_trading_day(self) -> bool:
        """Is today a trading day? (market is or was open today)."""
        now = now_et()
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        # If market is open, it's a trading day
        # If closed, check if next_open is tomorrow (meaning today was a trading day)
        clock = self.get_clock()
        if clock["is_open"]:
            return True
        # Market is closed — check if it closed today (after hours)
        next_open = clock["next_open"]
        if next_open and next_open.date() > now.date():
            return True  # next open is tomorrow+, so today was/is a trading day
        return False

    def is_after_entry_time(self, entry_time_str: str = "09:31") -> bool:
        """Is it past the entry time (e.g., 9:31 AM ET)?"""
        now = now_et()
        h, m = map(int, entry_time_str.split(":"))
        entry = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return now >= entry

    def is_before_exit_time(self, exit_time_str: str = "15:15") -> bool:
        """Is it before the exit time (e.g., 3:15 PM ET)?"""
        now = now_et()
        h, m = map(int, exit_time_str.split(":"))
        exit_t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return now < exit_t

    def seconds_until(self, time_str: str) -> float:
        """Seconds until a given time today (ET). Negative if past."""
        now = now_et()
        h, m = map(int, time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return (target - now).total_seconds()
