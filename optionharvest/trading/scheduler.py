"""
Daily trading scheduler.

Runs the trading bot automatically every trading day:
  9:25 AM ET  -- start up, connect, pre-checks
  9:31 AM ET  -- execute strategy
  3:15 PM ET  -- exit positions
  4:02 PM ET  -- end-of-day cleanup, shutdown

Can run as a long-lived process (stays alive across days)
or as a one-shot (run once for today, then exit).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from optionharvest.utils.calendar import now_et
from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.trading.executor import TradingBot

log = get_logger("scheduler")


class TradingScheduler:
    """Schedule and run the trading bot on trading days."""

    def __init__(
        self,
        bot: "TradingBot",
        start_time: str = "09:25",
        shutdown_time: str = "16:05",
    ) -> None:
        self.bot = bot
        self.start_time = start_time
        self.shutdown_time = shutdown_time
        self._running = False

    @classmethod
    def from_bot(
        cls,
        bot: "TradingBot",
    ) -> "TradingScheduler":
        cfg = bot.cfg.get("scheduler", {})
        return cls(
            bot=bot,
            start_time=cfg.get("start_time", "09:25"),
            shutdown_time=cfg.get("shutdown_time", "16:05"),
        )

    # ------------------------------------------------------------------
    # One-shot mode
    # ------------------------------------------------------------------

    def run_today(self) -> None:
        """Run the bot for today only, then exit."""
        log.info("Running one-shot for today")
        self._wait_until(self.start_time)
        self._run_with_retry()
        log.info("One-shot complete")

    # ------------------------------------------------------------------
    # Continuous mode
    # ------------------------------------------------------------------

    def run_forever(self) -> None:
        """
        Run as a long-lived process. Wakes up each trading day,
        runs the bot, then sleeps until the next day.
        """
        log.info("Scheduler started in continuous mode")
        self._running = True

        while self._running:
            now = now_et()

            # If we're past shutdown time, sleep until tomorrow's start
            if self._is_past_time(self.shutdown_time):
                self._sleep_until_next_day()
                continue

            # If we're before start time, wait for it
            if not self._is_past_time(self.start_time):
                self._wait_until(self.start_time)

            # Check if it's a trading day
            try:
                if not self.bot.calendar.is_trading_day():
                    log.info("Not a trading day -- sleeping until tomorrow")
                    self._sleep_until_next_day()
                    continue
            except Exception as exc:
                log.error("Failed to check trading day: %s", exc)
                self._sleep_minutes(5)
                continue

            # Run the bot
            self._run_with_retry()

            # Reset tracker for next day
            self.bot.tracker.reset_daily()

            # Sleep until next day
            self._sleep_until_next_day()

        log.info("Scheduler stopped")

    def stop(self) -> None:
        """Signal the scheduler to stop after current cycle."""
        log.info("Scheduler stop requested")
        self._running = False

    # ------------------------------------------------------------------
    # Retry logic (Task 6.3 edge cases)
    # ------------------------------------------------------------------

    def _run_with_retry(self, max_retries: int = 3) -> None:
        """Run the bot with retry on connection/API errors."""
        for attempt in range(1, max_retries + 1):
            try:
                self.bot.run()
                return  # success
            except KeyboardInterrupt:
                log.info("Interrupted by user")
                self._running = False
                return
            except ConnectionError as exc:
                log.error(
                    "Connection error (attempt %d/%d): %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    wait = 30 * attempt  # 30s, 60s, 90s
                    log.info("Retrying in %ds...", wait)
                    time.sleep(wait)
            except Exception as exc:
                log.error(
                    "Unexpected error (attempt %d/%d): %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    wait = 60 * attempt
                    log.info("Retrying in %ds...", wait)
                    time.sleep(wait)

        log.error("All %d retries exhausted -- skipping today", max_retries)

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _wait_until(self, time_str: str) -> None:
        """Sleep until a specific time today (ET)."""
        while not self._is_past_time(time_str):
            secs = self.bot.calendar.seconds_until(time_str)
            if secs <= 0:
                break
            wait = min(secs, 60)
            log.info("Waiting for %s ET (%.0fs away)", time_str, secs)
            time.sleep(wait)

    def _is_past_time(self, time_str: str) -> bool:
        """Is the current ET time past the given time string?"""
        now = now_et()
        h, m = map(int, time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return now >= target

    def _sleep_until_next_day(self) -> None:
        """Sleep until start_time tomorrow."""
        now = now_et()
        h, m = map(int, self.start_time.split(":"))
        # Calculate seconds until start_time tomorrow
        tomorrow_start = now.replace(
            hour=h, minute=m, second=0, microsecond=0,
        )
        # Move to tomorrow
        from datetime import timedelta
        tomorrow_start += timedelta(days=1)
        secs = (tomorrow_start - now).total_seconds()

        log.info(
            "Sleeping until tomorrow %s ET (%.0f hours)",
            self.start_time, secs / 3600,
        )
        # Sleep in chunks so we can respond to stop()
        while secs > 0 and self._running:
            chunk = min(secs, 300)  # wake every 5 min to check _running
            time.sleep(chunk)
            secs -= chunk

    def _sleep_minutes(self, minutes: int) -> None:
        """Sleep for N minutes."""
        time.sleep(minutes * 60)
