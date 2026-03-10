"""Tests for dashboard helper functions."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from optionharvest.dashboard import app as dashboard


class TestConfigHelpers:
    def test_load_config(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "settings.yaml"
        cfg_path.write_text(yaml.dump({"strategy": {"target_premium": 2.00}}))
        monkeypatch.setattr(dashboard, "CONFIG_PATH", cfg_path)

        cfg = dashboard.load_config()
        assert cfg["strategy"]["target_premium"] == 2.00

    def test_load_config_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dashboard, "CONFIG_PATH", tmp_path / "nope.yaml")
        cfg = dashboard.load_config()
        assert cfg == {}

    def test_save_config(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "settings.yaml"
        monkeypatch.setattr(dashboard, "CONFIG_PATH", cfg_path)

        dashboard.save_config({"strategy": {"option_type": "call"}})
        assert cfg_path.exists()

        loaded = yaml.safe_load(cfg_path.read_text())
        assert loaded["strategy"]["option_type"] == "call"

    def test_save_and_reload_roundtrip(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "settings.yaml"
        monkeypatch.setattr(dashboard, "CONFIG_PATH", cfg_path)

        original = {
            "strategy": {"target_premium": 1.75, "option_type": "both"},
            "exit": {"stop_loss_multiplier": 3.0},
            "risk": {"max_daily_loss": 300.0},
        }
        dashboard.save_config(original)
        reloaded = dashboard.load_config()

        assert reloaded["strategy"]["target_premium"] == 1.75
        assert reloaded["strategy"]["option_type"] == "both"
        assert reloaded["exit"]["stop_loss_multiplier"] == 3.0
        assert reloaded["risk"]["max_daily_loss"] == 300.0


class TestKillSwitch:
    def test_kill_switch_off_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dashboard, "KILL_SWITCH_PATH", tmp_path / "KILL_SWITCH")
        assert dashboard.is_kill_switch_on() is False

    def test_toggle_kill_switch_on(self, tmp_path, monkeypatch):
        ks_path = tmp_path / "KILL_SWITCH"
        monkeypatch.setattr(dashboard, "KILL_SWITCH_PATH", ks_path)

        result = dashboard.toggle_kill_switch()
        assert result is True
        assert ks_path.exists()

    def test_toggle_kill_switch_off(self, tmp_path, monkeypatch):
        ks_path = tmp_path / "KILL_SWITCH"
        ks_path.touch()
        monkeypatch.setattr(dashboard, "KILL_SWITCH_PATH", ks_path)

        result = dashboard.toggle_kill_switch()
        assert result is False
        assert not ks_path.exists()

    def test_toggle_roundtrip(self, tmp_path, monkeypatch):
        ks_path = tmp_path / "KILL_SWITCH"
        monkeypatch.setattr(dashboard, "KILL_SWITCH_PATH", ks_path)

        assert dashboard.is_kill_switch_on() is False
        dashboard.toggle_kill_switch()  # on
        assert dashboard.is_kill_switch_on() is True
        dashboard.toggle_kill_switch()  # off
        assert dashboard.is_kill_switch_on() is False


class TestBuildConfig:
    def test_build_config_updates_strategy(self):
        base = {"strategy": {"min_open_interest": 100}, "chain": {}}
        result = dashboard._build_config(
            base,
            option_type="call",
            target_premium=2.50,
            num_contracts=3,
            strike_mode="delta",
            target_delta=0.15,
            use_stop_loss=True,
            stop_loss_mult=2.5,
            use_profit_target=False,
            profit_target=40,
            max_daily=800,
            max_weekly=2000,
            max_pos_pct=8,
            cb_loss=5,
            cb_qqq=4,
        )

        assert result["strategy"]["option_type"] == "call"
        assert result["strategy"]["target_premium"] == 2.50
        assert result["strategy"]["num_contracts"] == 3
        assert result["strategy"]["strike_selection"] == "delta"
        assert result["strategy"]["target_delta"] == 0.15
        # Preserved from base
        assert result["strategy"]["min_open_interest"] == 100

    def test_build_config_updates_exit(self):
        base = {}
        result = dashboard._build_config(
            base, "put", 1.50, 1, "premium", 0.10,
            use_stop_loss=False, stop_loss_mult=3.0,
            use_profit_target=True, profit_target=60,
            max_daily=500, max_weekly=1500, max_pos_pct=5,
            cb_loss=3, cb_qqq=3,
        )

        assert result["exit"]["use_stop_loss"] is False
        assert result["exit"]["stop_loss_multiplier"] == 3.0
        assert result["exit"]["use_profit_target"] is True
        assert result["exit"]["profit_target_pct"] == 0.60

    def test_build_config_updates_risk(self):
        base = {}
        result = dashboard._build_config(
            base, "put", 1.50, 1, "premium", 0.10,
            True, 2.0, True, 50,
            max_daily=1000, max_weekly=3000, max_pos_pct=10,
            cb_loss=7, cb_qqq=6,
        )

        assert result["risk"]["max_daily_loss"] == 1000.0
        assert result["risk"]["max_weekly_loss"] == 3000.0
        assert result["risk"]["max_position_pct"] == 0.10
        assert result["risk"]["circuit_breaker_loss_pct"] == 0.07
        assert result["risk"]["circuit_breaker_qqq_move"] == 0.06

    def test_preserves_non_edited_keys(self):
        base = {
            "chain": {"strike_range_pct": 0.10},
            "execution": {"entry_time": "09:31"},
            "analytics": {"trade_log_dir": "data/trades"},
        }
        result = dashboard._build_config(
            base, "put", 1.50, 1, "premium", 0.10,
            True, 2.0, True, 50, 500, 1500, 5, 3, 3,
        )

        # These should be untouched
        assert result["chain"]["strike_range_pct"] == 0.10
        assert result["execution"]["entry_time"] == "09:31"
        assert result["analytics"]["trade_log_dir"] == "data/trades"
