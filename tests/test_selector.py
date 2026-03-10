"""Tests for strike selector."""

import pandas as pd
import pytest

from optionharvest.strategy.selector import StrikeSelector, Selection


def _make_chain() -> pd.DataFrame:
    """Build a minimal test chain DataFrame."""
    return pd.DataFrame([
        {"symbol": "QQQ260309P00480000", "strike": 480, "option_type": "put",
         "mid": 0.80, "bid": 0.75, "ask": 0.85, "open_interest": 500},
        {"symbol": "QQQ260309P00490000", "strike": 490, "option_type": "put",
         "mid": 1.50, "bid": 1.45, "ask": 1.55, "open_interest": 300},
        {"symbol": "QQQ260309P00495000", "strike": 495, "option_type": "put",
         "mid": 2.50, "bid": 2.40, "ask": 2.60, "open_interest": 200},
        {"symbol": "QQQ260309C00510000", "strike": 510, "option_type": "call",
         "mid": 1.40, "bid": 1.35, "ask": 1.45, "open_interest": 400},
        {"symbol": "QQQ260309C00520000", "strike": 520, "option_type": "call",
         "mid": 0.60, "bid": 0.55, "ask": 0.65, "open_interest": 250},
    ])


class TestStrikeSelector:
    def test_select_put_by_premium(self):
        selector = StrikeSelector(
            target_premium=1.50, option_type="put", strike_selection="premium",
        )
        chain = _make_chain()
        results = selector.select(chain, underlying_price=500.0)

        assert len(results) == 1
        assert results[0].option_type == "put"
        assert results[0].strike == 490  # mid=1.50, closest to target
        assert results[0].mid_price == 1.50

    def test_select_call_by_premium(self):
        selector = StrikeSelector(
            target_premium=1.40, option_type="call", strike_selection="premium",
        )
        results = selector.select(_make_chain(), underlying_price=500.0)

        assert len(results) == 1
        assert results[0].option_type == "call"
        assert results[0].strike == 510

    def test_select_both_strangle(self):
        selector = StrikeSelector(
            target_premium=1.50, option_type="both", strike_selection="premium",
        )
        results = selector.select(_make_chain(), underlying_price=500.0)

        assert len(results) == 2
        types = {r.option_type for r in results}
        assert types == {"put", "call"}

    def test_empty_chain_returns_empty(self):
        selector = StrikeSelector()
        results = selector.select(pd.DataFrame(), underlying_price=500.0)
        assert results == []

    def test_filter_by_open_interest(self):
        selector = StrikeSelector(
            target_premium=1.50, option_type="put",
            min_open_interest=1000,  # very high threshold
        )
        results = selector.select(_make_chain(), underlying_price=500.0)
        assert results == []  # all options filtered out

    def test_filter_by_bid_ask_spread(self):
        selector = StrikeSelector(
            target_premium=1.50, option_type="put",
            max_bid_ask_spread=0.05,  # very tight
        )
        results = selector.select(_make_chain(), underlying_price=500.0)
        assert results == []  # all spreads are $0.10+

    def test_only_otm_options_selected(self):
        """Puts must be below spot, calls above spot."""
        selector = StrikeSelector(
            target_premium=2.50, option_type="put", strike_selection="premium",
        )
        results = selector.select(_make_chain(), underlying_price=500.0)

        # All selected puts should have strike < 500
        for r in results:
            if r.option_type == "put":
                assert r.strike < 500

    def test_from_config(self):
        cfg = {
            "strategy": {
                "target_premium": 2.00,
                "option_type": "call",
                "strike_selection": "delta",
                "target_delta": 0.15,
                "min_open_interest": 50,
                "max_bid_ask_spread": 1.00,
            }
        }
        selector = StrikeSelector.from_config(cfg)
        assert selector.target_premium == 2.00
        assert selector.option_type == "call"
        assert selector.target_delta == 0.15

    def test_selection_spread_property(self):
        s = Selection(
            symbol="QQQ260309P00490000", strike=490, option_type="put",
            mid_price=1.50, bid=1.45, ask=1.55, open_interest=300,
        )
        assert s.spread == 0.10
