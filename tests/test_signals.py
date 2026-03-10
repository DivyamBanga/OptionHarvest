"""Tests for entry/exit signal logic."""

from unittest.mock import MagicMock

import pytest

from optionharvest.strategy.signals import SignalEngine, ExitSignal


def _mock_calendar(is_open=True, after_entry=True, before_exit=True):
    cal = MagicMock()
    cal.is_market_open.return_value = is_open
    cal.is_after_entry_time.return_value = after_entry
    cal.is_before_exit_time.return_value = before_exit
    return cal


class TestEntrySignals:
    def test_entry_allowed(self):
        engine = SignalEngine()
        cal = _mock_calendar()
        ok, reason = engine.check_entry(cal, has_open_position=False, daily_loss_limit_hit=False)
        assert ok is True
        assert reason == ""

    def test_blocked_by_open_position(self):
        engine = SignalEngine()
        cal = _mock_calendar()
        ok, reason = engine.check_entry(cal, has_open_position=True, daily_loss_limit_hit=False)
        assert ok is False
        assert "open position" in reason

    def test_blocked_by_daily_loss(self):
        engine = SignalEngine()
        cal = _mock_calendar()
        ok, reason = engine.check_entry(cal, has_open_position=False, daily_loss_limit_hit=True)
        assert ok is False
        assert "loss limit" in reason

    def test_blocked_market_closed(self):
        engine = SignalEngine()
        cal = _mock_calendar(is_open=False)
        ok, reason = engine.check_entry(cal, has_open_position=False, daily_loss_limit_hit=False)
        assert ok is False
        assert "closed" in reason

    def test_blocked_before_entry_time(self):
        engine = SignalEngine()
        cal = _mock_calendar(after_entry=False)
        ok, reason = engine.check_entry(cal, has_open_position=False, daily_loss_limit_hit=False)
        assert ok is False
        assert "entry time" in reason

    def test_blocked_after_exit_time(self):
        engine = SignalEngine()
        cal = _mock_calendar(before_exit=False)
        ok, reason = engine.check_entry(cal, has_open_position=False, daily_loss_limit_hit=False)
        assert ok is False
        assert "exit time" in reason


class TestExitSignals:
    def test_no_exit_when_price_normal(self):
        engine = SignalEngine(stop_loss_multiplier=2.0, profit_target_pct=0.50)
        cal = _mock_calendar(before_exit=True)
        result = engine.check_exit(entry_premium=1.50, current_option_price=1.20, calendar=cal)
        assert result.should_exit is False

    def test_stop_loss_triggered(self):
        engine = SignalEngine(stop_loss_multiplier=2.0)
        cal = _mock_calendar(before_exit=True)
        # Price doubled (bad for seller)
        result = engine.check_exit(entry_premium=1.50, current_option_price=3.00, calendar=cal)
        assert result.should_exit is True
        assert result.reason == "stop_loss"

    def test_profit_target_triggered(self):
        engine = SignalEngine(profit_target_pct=0.50)
        cal = _mock_calendar(before_exit=True)
        # Price dropped to 50% of entry (good for seller)
        result = engine.check_exit(entry_premium=1.50, current_option_price=0.75, calendar=cal)
        assert result.should_exit is True
        assert result.reason == "profit_target"

    def test_time_exit_triggered(self):
        engine = SignalEngine()
        cal = _mock_calendar(before_exit=False)
        result = engine.check_exit(entry_premium=1.50, current_option_price=1.20, calendar=cal)
        assert result.should_exit is True
        assert result.reason == "time_exit"

    def test_time_exit_takes_priority(self):
        """Time exit should fire even if stop loss is also triggered."""
        engine = SignalEngine(stop_loss_multiplier=2.0)
        cal = _mock_calendar(before_exit=False)
        result = engine.check_exit(entry_premium=1.50, current_option_price=5.00, calendar=cal)
        assert result.should_exit is True
        assert result.reason == "time_exit"

    def test_stop_loss_disabled(self):
        engine = SignalEngine(use_stop_loss=False, use_profit_target=False)
        cal = _mock_calendar(before_exit=True)
        result = engine.check_exit(entry_premium=1.50, current_option_price=10.00, calendar=cal)
        assert result.should_exit is False

    def test_from_config(self):
        cfg = {
            "execution": {"entry_time": "09:35", "exit_time": "15:00"},
            "exit": {
                "stop_loss_multiplier": 3.0,
                "profit_target_pct": 0.75,
                "use_stop_loss": False,
            },
        }
        engine = SignalEngine.from_config(cfg)
        assert engine.entry_time == "09:35"
        assert engine.exit_time == "15:00"
        assert engine.stop_loss_multiplier == 3.0
        assert engine.use_stop_loss is False
