"""Tests for ChainStore (Parquet persistence)."""

from datetime import date

import pandas as pd
import pytest

from optionharvest.data import schema as S
from optionharvest.data.store import ChainStore


class TestChainStore:
    def test_save_and_load(self, sample_chain, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)
        d = date(2024, 6, 3)

        store.save(sample_chain, d)
        loaded = store.load(d)

        assert loaded is not None
        assert len(loaded) == len(sample_chain)
        assert list(loaded.columns) == S.CHAIN_COLUMNS
        # Check values survived round-trip
        assert loaded[S.STRIKE].tolist() == sample_chain[S.STRIKE].tolist()
        assert loaded[S.OPEN].tolist() == sample_chain[S.OPEN].tolist()
        assert loaded[S.CLOSE].tolist() == sample_chain[S.CLOSE].tolist()

    def test_load_nonexistent_returns_none(self, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)
        assert store.load(date(2099, 1, 1)) is None

    def test_has(self, sample_chain, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)
        d = date(2024, 6, 3)

        assert not store.has(d)
        store.save(sample_chain, d)
        assert store.has(d)

    def test_cached_dates(self, sample_chain, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)

        # Save two days
        d1 = date(2024, 6, 3)
        d2 = date(2024, 6, 4)
        chain2 = sample_chain.copy()
        chain2[S.DATE] = d2

        store.save(sample_chain, d1)
        store.save(chain2, d2)

        dates = store.cached_dates()
        assert dates == [d1, d2]

    def test_load_range(self, sample_chain, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)

        d1 = date(2024, 6, 3)
        d2 = date(2024, 6, 4)
        d3 = date(2024, 6, 5)

        chain2 = sample_chain.copy()
        chain2[S.DATE] = d2
        chain3 = sample_chain.copy()
        chain3[S.DATE] = d3

        store.save(sample_chain, d1)
        store.save(chain2, d2)
        store.save(chain3, d3)

        # Load subset
        df = store.load_range(d1, d2)
        dates_loaded = sorted(df[S.DATE].unique())
        assert dates_loaded == [d1, d2]

    def test_load_range_empty(self, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)
        df = store.load_range(date(2024, 1, 1), date(2024, 1, 31))
        assert df.empty
        assert list(df.columns) == S.CHAIN_COLUMNS

    def test_delete(self, sample_chain, tmp_chains_dir):
        store = ChainStore(chains_dir=tmp_chains_dir)
        d = date(2024, 6, 3)

        store.save(sample_chain, d)
        assert store.has(d)

        assert store.delete(d) is True
        assert not store.has(d)

        # Deleting again returns False
        assert store.delete(d) is False

    def test_date_column_type_after_load(self, sample_chain, tmp_chains_dir):
        """Ensure date column comes back as datetime.date, not Timestamp."""
        store = ChainStore(chains_dir=tmp_chains_dir)
        d = date(2024, 6, 3)
        store.save(sample_chain, d)
        loaded = store.load(d)
        assert all(isinstance(v, date) for v in loaded[S.DATE])
