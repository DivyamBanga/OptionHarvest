"""Tests for trading scheduler."""

from unittest.mock import MagicMock, patch

import pytest

from optionharvest.trading.scheduler import TradingScheduler


def _mock_bot(is_trading_day=True):
    bot = MagicMock()
    bot.calendar.is_trading_day.return_value = is_trading_day
    bot.calendar.seconds_until.return_value = -1  # already past
    bot.cfg = {"scheduler": {"start_time": "09:25", "shutdown_time": "16:05"}}
    bot.tracker.reset_daily = MagicMock()
    return bot


class TestScheduler:
    def test_from_bot(self):
        bot = _mock_bot()
        scheduler = TradingScheduler.from_bot(bot)
        assert scheduler.start_time == "09:25"
        assert scheduler.shutdown_time == "16:05"

    def test_from_bot_default_config(self):
        bot = MagicMock()
        bot.cfg = {}
        scheduler = TradingScheduler.from_bot(bot)
        assert scheduler.start_time == "09:25"
        assert scheduler.shutdown_time == "16:05"

    def test_run_with_retry_success(self):
        bot = _mock_bot()
        scheduler = TradingScheduler(bot)
        scheduler._run_with_retry()
        bot.run.assert_called_once()

    def test_run_with_retry_recovers(self):
        bot = _mock_bot()
        # Fail first, succeed second
        bot.run.side_effect = [ConnectionError("timeout"), None]
        scheduler = TradingScheduler(bot)

        with patch("time.sleep"):
            scheduler._run_with_retry(max_retries=3)

        assert bot.run.call_count == 2

    def test_run_with_retry_exhausted(self):
        bot = _mock_bot()
        bot.run.side_effect = ConnectionError("down")
        scheduler = TradingScheduler(bot)

        with patch("time.sleep"):
            scheduler._run_with_retry(max_retries=2)

        assert bot.run.call_count == 2

    def test_run_with_retry_keyboard_interrupt(self):
        bot = _mock_bot()
        bot.run.side_effect = KeyboardInterrupt()
        scheduler = TradingScheduler(bot)

        scheduler._run_with_retry()
        assert scheduler._running is False

    def test_stop(self):
        bot = _mock_bot()
        scheduler = TradingScheduler(bot)
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False

    def test_is_past_time(self):
        bot = _mock_bot()
        scheduler = TradingScheduler(bot)

        with patch("optionharvest.trading.scheduler.now_et") as mock_now:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            et = ZoneInfo("America/New_York")
            mock_now.return_value = datetime(2026, 3, 10, 10, 0, 0, tzinfo=et)
            assert scheduler._is_past_time("09:30") is True
            assert scheduler._is_past_time("10:30") is False
