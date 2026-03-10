"""Tests for risk limits."""

from datetime import date, timedelta

import pytest

from optionharvest.risk.limits import RiskLimits


class TestRiskLimits:
    def test_daily_loss_not_hit(self):
        limits = RiskLimits(max_daily_loss=500.0)
        today = date(2026, 3, 9)
        limits.record_pnl(today, -200.0)
        assert limits.daily_loss_limit_hit(today) is False

    def test_daily_loss_hit(self):
        limits = RiskLimits(max_daily_loss=500.0)
        today = date(2026, 3, 9)
        limits.record_pnl(today, -500.0)
        assert limits.daily_loss_limit_hit(today) is True

    def test_daily_loss_hit_cumulative(self):
        limits = RiskLimits(max_daily_loss=500.0)
        today = date(2026, 3, 9)
        limits.record_pnl(today, -300.0)
        limits.record_pnl(today, -250.0)  # total = -550
        assert limits.daily_loss_limit_hit(today) is True

    def test_daily_loss_different_days(self):
        limits = RiskLimits(max_daily_loss=500.0)
        day1 = date(2026, 3, 9)
        day2 = date(2026, 3, 10)
        limits.record_pnl(day1, -400.0)
        limits.record_pnl(day2, -200.0)
        assert limits.daily_loss_limit_hit(day1) is False
        assert limits.daily_loss_limit_hit(day2) is False

    def test_weekly_loss_not_hit(self):
        limits = RiskLimits(max_weekly_loss=1500.0)
        # Monday through Wednesday
        mon = date(2026, 3, 9)
        limits.record_pnl(mon, -400.0)
        limits.record_pnl(mon + timedelta(days=1), -300.0)
        limits.record_pnl(mon + timedelta(days=2), -200.0)
        assert limits.weekly_loss_limit_hit(mon + timedelta(days=2)) is False

    def test_weekly_loss_hit(self):
        limits = RiskLimits(max_weekly_loss=1500.0)
        mon = date(2026, 3, 9)
        limits.record_pnl(mon, -500.0)
        limits.record_pnl(mon + timedelta(days=1), -500.0)
        limits.record_pnl(mon + timedelta(days=2), -600.0)
        assert limits.weekly_loss_limit_hit(mon + timedelta(days=2)) is True

    def test_weekly_loss_resets_new_week(self):
        limits = RiskLimits(max_weekly_loss=1500.0)
        mon1 = date(2026, 3, 2)  # Monday
        limits.record_pnl(mon1, -1000.0)
        limits.record_pnl(mon1 + timedelta(days=1), -600.0)
        # Week 1 total = -1600 -> hit
        assert limits.weekly_loss_limit_hit(mon1 + timedelta(days=1)) is True

        # New week
        mon2 = date(2026, 3, 9)  # Next Monday
        limits.record_pnl(mon2, -200.0)
        assert limits.weekly_loss_limit_hit(mon2) is False

    def test_check_buying_power_ok(self):
        limits = RiskLimits()
        ok, msg = limits.check_buying_power(required=150.0, available=10000.0)
        assert ok is True
        assert msg == ""

    def test_check_buying_power_insufficient(self):
        limits = RiskLimits()
        ok, msg = limits.check_buying_power(required=15000.0, available=10000.0)
        assert ok is False
        assert "Insufficient" in msg

    def test_check_position_size_ok(self):
        limits = RiskLimits(max_position_pct=0.05)
        ok, msg = limits.check_position_size(trade_risk=150.0, account_equity=100000.0)
        assert ok is True

    def test_check_position_size_too_large(self):
        limits = RiskLimits(max_position_pct=0.05)
        # 5% of 100K = 5000. Risk of 6000 is too much.
        ok, msg = limits.check_position_size(trade_risk=6000.0, account_equity=100000.0)
        assert ok is False
        assert "too large" in msg

    def test_get_today_pnl(self):
        limits = RiskLimits()
        today = date(2026, 3, 9)
        limits.record_pnl(today, 150.0)
        limits.record_pnl(today, -50.0)
        assert limits.get_today_pnl(today) == 100.0

    def test_get_today_pnl_no_trades(self):
        limits = RiskLimits()
        assert limits.get_today_pnl(date(2026, 3, 9)) == 0.0

    def test_from_config(self):
        cfg = {
            "risk": {
                "max_daily_loss": 300.0,
                "max_weekly_loss": 1000.0,
                "max_position_pct": 0.03,
            }
        }
        limits = RiskLimits.from_config(cfg)
        assert limits.max_daily_loss == 300.0
        assert limits.max_weekly_loss == 1000.0
        assert limits.max_position_pct == 0.03
