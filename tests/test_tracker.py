"""Tests for trade tracker."""

from datetime import date

import pytest

from optionharvest.analytics.tracker import TradeTracker


class TestTradeTracker:
    def test_record_trade(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        trade = tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="QQQ260309P00490000",
            strike=490.0,
            option_type="put",
            qty=1,
            entry_price=1.50,
            exit_price=0.75,
            entry_time="09:31:05",
            exit_time="14:22:10",
            exit_reason="profit_target",
            qqq_open=500.0,
            qqq_close=501.5,
        )
        # Short option P&L: (entry - exit) * 100 * qty = (1.50 - 0.75) * 100 = $75
        assert trade["pnl"] == 75.0
        assert trade["qqq_move_pct"] == 0.30  # (501.5-500)/500 * 100

    def test_csv_created(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="QQQ260309P00490000",
            strike=490.0,
            option_type="put",
            qty=1,
            entry_price=1.50,
            exit_price=0.75,
            entry_time="09:31:05",
            exit_time="14:22:10",
            exit_reason="profit_target",
        )
        csv_path = tmp_path / "trade_log.csv"
        assert csv_path.exists()

    def test_get_all_trades(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="QQQ260309P00490000",
            strike=490.0,
            option_type="put",
            qty=1,
            entry_price=1.50,
            exit_price=0.75,
            entry_time="09:31:05",
            exit_time="14:22:10",
            exit_reason="profit_target",
        )
        tracker.record_trade(
            trading_date=date(2026, 3, 10),
            symbol="QQQ260310P00485000",
            strike=485.0,
            option_type="put",
            qty=1,
            entry_price=1.20,
            exit_price=2.40,
            entry_time="09:31:02",
            exit_time="11:05:30",
            exit_reason="stop_loss",
        )

        trades = tracker.get_all_trades()
        assert len(trades) == 2
        assert trades[0]["pnl"] == 75.0  # win
        assert trades[1]["pnl"] == -120.0  # loss: (1.20-2.40)*100

    def test_get_today_pnl(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="QQQ260309P00490000",
            strike=490.0,
            option_type="put",
            qty=1,
            entry_price=1.50,
            exit_price=0.75,
            entry_time="09:31:05",
            exit_time="14:22:10",
            exit_reason="profit_target",
        )
        assert tracker.get_today_pnl() == 75.0

    def test_cumulative_stats(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        # Two wins, one loss
        tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="SYM1", strike=490.0, option_type="put", qty=1,
            entry_price=1.50, exit_price=0.75,
            entry_time="09:31:00", exit_time="14:00:00",
            exit_reason="profit_target",
        )
        tracker.record_trade(
            trading_date=date(2026, 3, 10),
            symbol="SYM2", strike=485.0, option_type="put", qty=1,
            entry_price=1.20, exit_price=0.50,
            entry_time="09:31:00", exit_time="14:00:00",
            exit_reason="profit_target",
        )
        tracker.record_trade(
            trading_date=date(2026, 3, 11),
            symbol="SYM3", strike=495.0, option_type="put", qty=1,
            entry_price=1.00, exit_price=2.00,
            entry_time="09:31:00", exit_time="11:00:00",
            exit_reason="stop_loss",
        )

        stats = tracker.get_cumulative_stats()
        assert stats["total_trades"] == 3
        assert stats["total_pnl"] == 75.0 + 70.0 - 100.0  # 45.0
        assert stats["win_rate"] == pytest.approx(66.7, abs=0.1)

    def test_empty_stats(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        stats = tracker.get_cumulative_stats()
        assert stats["total_trades"] == 0
        assert stats["total_pnl"] == 0.0

    def test_reset_daily(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="SYM1", strike=490.0, option_type="put", qty=1,
            entry_price=1.50, exit_price=0.75,
            entry_time="09:31:00", exit_time="14:00:00",
            exit_reason="profit_target",
        )
        assert tracker.get_today_pnl() == 75.0

        tracker.reset_daily()
        assert tracker.get_today_pnl() == 0.0
        # CSV still has the data
        assert len(tracker.get_all_trades()) == 1

    def test_from_config(self, tmp_path):
        cfg = {"analytics": {"trade_log_dir": str(tmp_path / "custom")}}
        tracker = TradeTracker.from_config(cfg)
        assert tracker.log_dir == tmp_path / "custom"

    def test_pnl_multiple_contracts(self, tmp_path):
        tracker = TradeTracker(log_dir=tmp_path)
        trade = tracker.record_trade(
            trading_date=date(2026, 3, 9),
            symbol="SYM1", strike=490.0, option_type="put", qty=3,
            entry_price=1.50, exit_price=0.75,
            entry_time="09:31:00", exit_time="14:00:00",
            exit_reason="profit_target",
        )
        # (1.50 - 0.75) * 100 * 3 = $225
        assert trade["pnl"] == 225.0
