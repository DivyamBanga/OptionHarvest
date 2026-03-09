"""Tests for DataLoader — end-to-end integration with mock data."""

from datetime import date
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from optionharvest.data import schema as S
from optionharvest.data.loader import DataLoader
from optionharvest.data.store import ChainStore


class TestDataLoader:
    """Test the loader using pre-saved sample chains (no network)."""

    def test_load_cached_returns_saved_data(self, sample_chain, tmp_path):
        chains_dir = tmp_path / "chains"
        chains_dir.mkdir()

        # Pre-save some data
        store = ChainStore(chains_dir=chains_dir)
        d = date(2024, 6, 3)
        store.save(sample_chain, d)

        loader = DataLoader(chains_dir=chains_dir)
        df = loader.load_cached(d, d)

        assert not df.empty
        assert len(df) == len(sample_chain)

    def test_load_cached_empty_range(self, tmp_path):
        chains_dir = tmp_path / "chains"
        chains_dir.mkdir()

        loader = DataLoader(chains_dir=chains_dir)
        df = loader.load_cached(date(2024, 1, 1), date(2024, 1, 31))
        assert df.empty

    def test_load_single_from_cache(self, sample_chain, tmp_path):
        chains_dir = tmp_path / "chains"
        chains_dir.mkdir()

        store = ChainStore(chains_dir=chains_dir)
        d = date(2024, 6, 3)
        store.save(sample_chain, d)

        loader = DataLoader(chains_dir=chains_dir)
        df = loader.load_single(d)

        assert df is not None
        assert len(df) == len(sample_chain)

    def test_validate_cached(self, sample_chain, tmp_path):
        chains_dir = tmp_path / "chains"
        chains_dir.mkdir()

        store = ChainStore(chains_dir=chains_dir)
        store.save(sample_chain, date(2024, 6, 3))

        loader = DataLoader(chains_dir=chains_dir)
        results = loader.validate_cached(date(2024, 6, 1), date(2024, 6, 30))

        assert len(results) == 1
        assert results[0].passed
