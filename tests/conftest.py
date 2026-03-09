"""Shared test fixtures for OptionHarvest tests."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from optionharvest.data import schema as S


@pytest.fixture
def sample_chain() -> pd.DataFrame:
    """A small, valid 0DTE chain for testing (4 rows: 2 strikes × 2 types)."""
    spot_open = 500.0
    spot_close = 502.0
    rows = [
        {
            S.DATE: date(2024, 6, 3),
            S.STRIKE: 498.0,
            S.OPTION_TYPE: "put",
            S.OPEN: 1.45,
            S.HIGH: 2.80,
            S.LOW: 0.00,
            S.CLOSE: 0.00,   # expired OTM (spot_close > strike)
            S.VOLUME: 0,
            S.BID_OPEN: 1.42,
            S.ASK_OPEN: 1.48,
            S.DELTA: -0.25,
            S.IMPLIED_VOL: 0.18,
            S.UNDERLYING_OPEN: spot_open,
            S.UNDERLYING_HIGH: 504.0,
            S.UNDERLYING_LOW: 497.0,
            S.UNDERLYING_CLOSE: spot_close,
        },
        {
            S.DATE: date(2024, 6, 3),
            S.STRIKE: 498.0,
            S.OPTION_TYPE: "call",
            S.OPEN: 3.10,
            S.HIGH: 6.20,
            S.LOW: 2.00,
            S.CLOSE: 4.00,   # expired ITM (spot_close - strike = 4)
            S.VOLUME: 0,
            S.BID_OPEN: 3.04,
            S.ASK_OPEN: 3.16,
            S.DELTA: 0.65,
            S.IMPLIED_VOL: 0.17,
            S.UNDERLYING_OPEN: spot_open,
            S.UNDERLYING_HIGH: 504.0,
            S.UNDERLYING_LOW: 497.0,
            S.UNDERLYING_CLOSE: spot_close,
        },
        {
            S.DATE: date(2024, 6, 3),
            S.STRIKE: 503.0,
            S.OPTION_TYPE: "put",
            S.OPEN: 3.80,
            S.HIGH: 6.50,
            S.LOW: 1.00,
            S.CLOSE: 1.00,   # expired ITM (strike - spot_close = 1)
            S.VOLUME: 0,
            S.BID_OPEN: 3.72,
            S.ASK_OPEN: 3.88,
            S.DELTA: -0.60,
            S.IMPLIED_VOL: 0.19,
            S.UNDERLYING_OPEN: spot_open,
            S.UNDERLYING_HIGH: 504.0,
            S.UNDERLYING_LOW: 497.0,
            S.UNDERLYING_CLOSE: spot_close,
        },
        {
            S.DATE: date(2024, 6, 3),
            S.STRIKE: 503.0,
            S.OPTION_TYPE: "call",
            S.OPEN: 1.20,
            S.HIGH: 2.50,
            S.LOW: 0.00,
            S.CLOSE: 0.00,   # expired OTM (spot_close < strike)
            S.VOLUME: 0,
            S.BID_OPEN: 1.18,
            S.ASK_OPEN: 1.22,
            S.DELTA: 0.30,
            S.IMPLIED_VOL: 0.16,
            S.UNDERLYING_OPEN: spot_open,
            S.UNDERLYING_HIGH: 504.0,
            S.UNDERLYING_LOW: 497.0,
            S.UNDERLYING_CLOSE: spot_close,
        },
    ]
    return pd.DataFrame(rows, columns=S.CHAIN_COLUMNS)


@pytest.fixture
def tmp_chains_dir(tmp_path):
    """Temporary directory for chain Parquet files."""
    d = tmp_path / "chains"
    d.mkdir()
    return d


@pytest.fixture
def tmp_underlying_dir(tmp_path):
    """Temporary directory for underlying data cache."""
    d = tmp_path / "underlying"
    d.mkdir()
    return d
