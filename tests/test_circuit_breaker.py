"""Tests for circuit breaker."""

from pathlib import Path

import pytest

from optionharvest.risk.circuit_breaker import CircuitBreaker, KILL_SWITCH_FILE


class TestCircuitBreaker:
    def test_no_trigger_normal_conditions(self):
        cb = CircuitBreaker(loss_pct_threshold=0.03, qqq_move_threshold=0.03)
        should_close, reason = cb.check(
            unrealized_pnl=-100.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=501.0,
        )
        assert should_close is False
        assert reason == ""

    def test_trigger_unrealized_loss(self):
        cb = CircuitBreaker(loss_pct_threshold=0.03)
        should_close, reason = cb.check(
            unrealized_pnl=-3500.0,  # 3.5% of 100K
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is True
        assert reason == "unrealized_loss"

    def test_no_trigger_at_threshold_boundary(self):
        cb = CircuitBreaker(loss_pct_threshold=0.03)
        # Exactly at 2.9% -- should NOT trigger
        should_close, reason = cb.check(
            unrealized_pnl=-2900.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is False

    def test_trigger_exactly_at_threshold(self):
        cb = CircuitBreaker(loss_pct_threshold=0.03)
        # Exactly at 3% -- SHOULD trigger
        should_close, reason = cb.check(
            unrealized_pnl=-3000.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is True
        assert reason == "unrealized_loss"

    def test_trigger_qqq_big_move_down(self):
        cb = CircuitBreaker(qqq_move_threshold=0.03)
        # QQQ dropped 4% from open
        should_close, reason = cb.check(
            unrealized_pnl=0.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=480.0,
        )
        assert should_close is True
        assert reason == "qqq_big_move"

    def test_trigger_qqq_big_move_up(self):
        cb = CircuitBreaker(qqq_move_threshold=0.03)
        # QQQ rallied 3.5% from open
        should_close, reason = cb.check(
            unrealized_pnl=0.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=517.5,
        )
        assert should_close is True
        assert reason == "qqq_big_move"

    def test_no_trigger_small_qqq_move(self):
        cb = CircuitBreaker(qqq_move_threshold=0.03)
        should_close, reason = cb.check(
            unrealized_pnl=0.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=505.0,  # only 1% move
        )
        assert should_close is False

    def test_kill_switch(self, tmp_path, monkeypatch):
        """Kill switch file triggers emergency close."""
        kill_file = tmp_path / "KILL_SWITCH"
        kill_file.touch()
        monkeypatch.setattr(
            "optionharvest.risk.circuit_breaker.KILL_SWITCH_FILE", kill_file
        )

        cb = CircuitBreaker()
        should_close, reason = cb.check(
            unrealized_pnl=0.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is True
        assert reason == "kill_switch"

    def test_no_kill_switch_file(self, tmp_path, monkeypatch):
        """No kill switch file means no trigger from that check."""
        kill_file = tmp_path / "KILL_SWITCH"
        # Don't create the file
        monkeypatch.setattr(
            "optionharvest.risk.circuit_breaker.KILL_SWITCH_FILE", kill_file
        )

        cb = CircuitBreaker()
        should_close, reason = cb.check(
            unrealized_pnl=0.0,
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is False

    def test_positive_pnl_no_trigger(self):
        cb = CircuitBreaker(loss_pct_threshold=0.03)
        should_close, reason = cb.check(
            unrealized_pnl=500.0,  # profit, not loss
            account_equity=100000.0,
            qqq_open=500.0,
            qqq_current=500.0,
        )
        assert should_close is False

    def test_from_config(self):
        cfg = {
            "risk": {
                "circuit_breaker_loss_pct": 0.05,
                "circuit_breaker_qqq_move": 0.04,
            }
        }
        cb = CircuitBreaker.from_config(cfg)
        assert cb.loss_pct_threshold == 0.05
        assert cb.qqq_move_threshold == 0.04
