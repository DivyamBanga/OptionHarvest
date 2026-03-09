"""Tests for ChainGenerator — uses mock market data (no network calls)."""

from datetime import date
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from optionharvest.data import schema as S
from optionharvest.data.chain_generator import ChainGenerator, ChainGeneratorConfig


def _mock_qqq_df():
    """Create fake QQQ daily data for a few trading days."""
    dates = pd.to_datetime(["2024-06-03", "2024-06-04", "2024-06-05"])
    data = {
        "Open":   [500.0, 502.0, 498.0],
        "High":   [504.0, 506.0, 501.0],
        "Low":    [497.0, 499.0, 495.0],
        "Close":  [502.0, 505.0, 499.0],
        "Volume": [40_000_000, 42_000_000, 38_000_000],
    }
    return pd.DataFrame(data, index=dates)


def _mock_vix_df():
    """Create fake VIX data matching the QQQ dates."""
    dates = pd.to_datetime(["2024-06-03", "2024-06-04", "2024-06-05"])
    data = {
        "Open":   [18.0, 17.0, 20.0],
        "High":   [19.0, 18.0, 22.0],
        "Low":    [17.0, 16.0, 19.0],
        "Close":  [18.5, 17.5, 21.0],
        "Volume": [0, 0, 0],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def generator(tmp_underlying_dir):
    """ChainGenerator with mocked market data fetcher."""
    cfg = ChainGeneratorConfig(
        strike_range_pct=0.02,   # narrow range for faster tests
        strike_spacing=1.0,
        risk_free_rate=0.05,
    )
    gen = ChainGenerator(config=cfg, cache_dir=tmp_underlying_dir)
    # Inject mock data directly
    gen._qqq = _mock_qqq_df()
    gen._vix = _mock_vix_df()
    return gen


class TestChainGenerator:
    def test_generate_single_chain(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))

        # Should have data
        assert not chain.empty
        # Should have all schema columns
        assert list(chain.columns) == S.CHAIN_COLUMNS
        # Should have both calls and puts
        assert set(chain[S.OPTION_TYPE]) == {"call", "put"}

    def test_chain_has_correct_underlying(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        assert (chain[S.UNDERLYING_OPEN] == 500.0).all()
        assert (chain[S.UNDERLYING_CLOSE] == 502.0).all()

    def test_close_price_is_intrinsic(self, generator):
        """Close price must be exact intrinsic value at expiry."""
        chain = generator.generate_chain(date(2024, 6, 3))
        spot_close = 502.0

        for _, row in chain.iterrows():
            if row[S.OPTION_TYPE] == "call":
                expected = max(0.0, spot_close - row[S.STRIKE])
            else:
                expected = max(0.0, row[S.STRIKE] - spot_close)
            assert row[S.CLOSE] == round(expected, 2), (
                f"Strike {row[S.STRIKE]} {row[S.OPTION_TYPE]}: "
                f"close={row[S.CLOSE]}, expected={expected}"
            )

    def test_open_price_positive_for_near_atm(self, generator):
        """Near-ATM options should have positive open price."""
        chain = generator.generate_chain(date(2024, 6, 3))
        spot = 500.0

        near_atm = chain[abs(chain[S.STRIKE] - spot) <= 2]
        assert (near_atm[S.OPEN] > 0).all()

    def test_high_gte_open_and_close(self, generator):
        """High should be >= max(open, close)."""
        chain = generator.generate_chain(date(2024, 6, 3))
        for _, row in chain.iterrows():
            assert row[S.HIGH] >= row[S.OPEN] - 0.01, (
                f"High {row[S.HIGH]} < Open {row[S.OPEN]}"
            )
            assert row[S.HIGH] >= row[S.CLOSE] - 0.01, (
                f"High {row[S.HIGH]} < Close {row[S.CLOSE]}"
            )

    def test_low_lte_open_and_close(self, generator):
        """Low should be <= min(open, close)."""
        chain = generator.generate_chain(date(2024, 6, 3))
        for _, row in chain.iterrows():
            assert row[S.LOW] <= row[S.OPEN] + 0.01
            assert row[S.LOW] <= row[S.CLOSE] + 0.01

    def test_bid_lt_ask(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        mask = chain[S.OPEN] > 0.02  # skip near-zero options
        subset = chain[mask]
        assert (subset[S.BID_OPEN] <= subset[S.ASK_OPEN]).all()

    def test_call_delta_positive(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        calls = chain[chain[S.OPTION_TYPE] == "call"]
        assert (calls[S.DELTA] >= 0).all()
        assert (calls[S.DELTA] <= 1).all()

    def test_put_delta_negative(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        puts = chain[chain[S.OPTION_TYPE] == "put"]
        assert (puts[S.DELTA] <= 0).all()
        assert (puts[S.DELTA] >= -1).all()

    def test_non_trading_day_raises(self, generator):
        with pytest.raises(ValueError, match="not a trading day"):
            generator.generate_chain(date(2024, 6, 1))  # Saturday

    def test_generate_multiple_chains(self, generator):
        chains = generator.generate_chains(date(2024, 6, 3), date(2024, 6, 5))
        assert len(chains) == 3
        for d, df in chains.items():
            assert not df.empty
            assert list(df.columns) == S.CHAIN_COLUMNS

    def test_strikes_centered_around_spot(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        spot = 500.0
        min_strike = chain[S.STRIKE].min()
        max_strike = chain[S.STRIKE].max()
        assert min_strike < spot
        assert max_strike > spot

    def test_all_prices_non_negative(self, generator):
        chain = generator.generate_chain(date(2024, 6, 3))
        for col in [S.OPEN, S.HIGH, S.LOW, S.CLOSE, S.BID_OPEN, S.ASK_OPEN]:
            assert (chain[col] >= 0).all(), f"{col} has negative values"
