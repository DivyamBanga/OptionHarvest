"""Tests for analytics reporter."""

from datetime import date

import pytest

from optionharvest.analytics.reporter import Reporter
from optionharvest.analytics.tracker import TradeTracker


def _make_tracker_with_trades(tmp_path, trades):
    """Helper: create a tracker and record multiple trades."""
    tracker = TradeTracker(log_dir=tmp_path)
    for t in trades:
        tracker.record_trade(**t)
    return tracker


def _trade(d, pnl_target, **overrides):
    """Helper: build trade kwargs that produce a specific P&L."""
    # P&L = (entry - exit) * 100 * qty
    # For pnl_target with qty=1: exit = entry - pnl_target/100
    entry = 1.50
    exit_price = entry - pnl_target / 100
    defaults = {
        "trading_date": d,
        "symbol": f"QQQ{d.isoformat().replace('-', '')}P00490000",
        "strike": 490.0,
        "option_type": "put",
        "qty": 1,
        "entry_price": entry,
        "exit_price": round(exit_price, 4),
        "entry_time": "09:31:00",
        "exit_time": "14:00:00",
        "exit_reason": "profit_target" if pnl_target > 0 else "stop_loss",
        "qqq_open": 500.0,
        "qqq_close": 501.0,
    }
    defaults.update(overrides)
    return defaults


class TestFullMetrics:
    def test_empty_trades(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()
        assert metrics["total_trades"] == 0

    def test_all_wins(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 75.0),
            _trade(date(2026, 3, 10), 50.0),
            _trade(date(2026, 3, 11), 100.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()

        assert metrics["total_trades"] == 3
        assert metrics["win_rate"] == 100.0
        assert metrics["total_pnl"] == 225.0
        assert metrics["longest_win_streak"] == 3
        assert metrics["longest_lose_streak"] == 0
        assert metrics["max_drawdown"] == 0.0

    def test_mixed_results(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 75.0),    # win
            _trade(date(2026, 3, 10), -120.0),  # loss
            _trade(date(2026, 3, 11), 50.0),    # win
            _trade(date(2026, 3, 12), -80.0),   # loss
            _trade(date(2026, 3, 13), 60.0),    # win
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()

        assert metrics["total_trades"] == 5
        assert metrics["win_rate"] == 60.0
        assert metrics["best_trade"] == 75.0
        assert metrics["worst_trade"] == -120.0
        assert metrics["longest_win_streak"] == 1
        assert metrics["longest_lose_streak"] == 1

    def test_max_drawdown(self, tmp_path):
        # Cumulative: 100, 200, 0, 50 -> peak=200, trough=0, dd=200
        trades = [
            _trade(date(2026, 3, 9), 100.0),
            _trade(date(2026, 3, 10), 100.0),
            _trade(date(2026, 3, 11), -200.0),
            _trade(date(2026, 3, 12), 50.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()

        assert metrics["max_drawdown"] == 200.0

    def test_avg_daily_pnl(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 100.0),
            _trade(date(2026, 3, 10), -50.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()

        assert metrics["trading_days"] == 2
        assert metrics["avg_daily_pnl"] == 25.0

    def test_streaks(self, tmp_path):
        # W W W L L W
        trades = [
            _trade(date(2026, 3, 2), 50.0),
            _trade(date(2026, 3, 3), 60.0),
            _trade(date(2026, 3, 4), 70.0),
            _trade(date(2026, 3, 5), -40.0),
            _trade(date(2026, 3, 6), -30.0),
            _trade(date(2026, 3, 9), 80.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        metrics = reporter.full_metrics()

        assert metrics["longest_win_streak"] == 3
        assert metrics["longest_lose_streak"] == 2


class TestWeeklyRollup:
    def test_single_week(self, tmp_path):
        # Mon-Fri of same week
        trades = [
            _trade(date(2026, 3, 9), 75.0),
            _trade(date(2026, 3, 10), -50.0),
            _trade(date(2026, 3, 11), 60.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        weeks = reporter.weekly_rollup()

        assert len(weeks) == 1
        assert weeks[0]["trades"] == 3
        assert weeks[0]["pnl"] == 85.0
        assert weeks[0]["wins"] == 2

    def test_two_weeks(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 75.0),   # week 1
            _trade(date(2026, 3, 10), -50.0),  # week 1
            _trade(date(2026, 3, 16), 100.0),  # week 2
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        weeks = reporter.weekly_rollup()

        assert len(weeks) == 2
        assert weeks[0]["pnl"] == 25.0
        assert weeks[1]["pnl"] == 100.0

    def test_empty(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        reporter = Reporter(tracker)
        assert reporter.weekly_rollup() == []


class TestMonthlyRollup:
    def test_single_month(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 75.0),
            _trade(date(2026, 3, 10), -50.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        months = reporter.monthly_rollup()

        assert len(months) == 1
        assert months[0]["month"] == "2026-03"
        assert months[0]["pnl"] == 25.0

    def test_two_months(self, tmp_path):
        trades = [
            _trade(date(2026, 3, 9), 75.0),
            _trade(date(2026, 4, 1), 100.0),
        ]
        tracker = _make_tracker_with_trades(tmp_path, trades)
        reporter = Reporter(tracker)
        months = reporter.monthly_rollup()

        assert len(months) == 2
        assert months[0]["month"] == "2026-03"
        assert months[1]["month"] == "2026-04"


class TestHelpers:
    def test_compute_streaks_empty(self):
        assert Reporter._compute_streaks([]) == (0, 0)

    def test_compute_streaks_all_wins(self):
        assert Reporter._compute_streaks([10, 20, 30]) == (3, 0)

    def test_compute_streaks_all_losses(self):
        assert Reporter._compute_streaks([-10, -20, -30]) == (0, 3)

    def test_compute_max_drawdown_no_loss(self):
        assert Reporter._compute_max_drawdown([10, 20, 30]) == 0.0

    def test_compute_max_drawdown_all_loss(self):
        # Peak at 0, trough at -60
        assert Reporter._compute_max_drawdown([-10, -20, -30]) == 60.0

    def test_compute_max_drawdown_recovery(self):
        # Cumulative: 100, 50, 150 -> peak 100, trough 50, dd=50
        assert Reporter._compute_max_drawdown([100, -50, 100]) == 50.0
