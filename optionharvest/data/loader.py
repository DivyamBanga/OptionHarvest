"""
High-level data loader that orchestrates chain generation, caching,
and validation.

Usage:
    loader = DataLoader()
    df = loader.load(date(2024, 1, 2), date(2024, 12, 31))
    # df is a single DataFrame with all trading days in the range

The loader checks local Parquet cache first.  Missing dates are
generated via ChainGenerator and saved automatically.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from optionharvest.data.chain_generator import ChainGenerator, ChainGeneratorConfig
from optionharvest.data.store import ChainStore
from optionharvest.data.validator import ChainValidator, ValidationResult
from optionharvest.data import schema as S
from optionharvest.utils.logger import get_logger

log = get_logger("loader")


class DataLoader:
    """One-stop shop: load chains for a date range, generating as needed."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        chains_dir: str | Path | None = None,
        underlying_cache_dir: str | Path | None = None,
    ) -> None:
        # Load YAML config if provided
        cfg_dict: dict = {}
        if config_path:
            with open(config_path) as f:
                cfg_dict = yaml.safe_load(f) or {}

        gen_config = ChainGeneratorConfig.from_yaml(cfg_dict) if cfg_dict else ChainGeneratorConfig()

        self.store = ChainStore(chains_dir=chains_dir)
        self.generator = ChainGenerator(config=gen_config, cache_dir=underlying_cache_dir)
        self.validator = ChainValidator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        start: date,
        end: date,
        *,
        validate: bool = True,
        force_regenerate: bool = False,
    ) -> pd.DataFrame:
        """
        Load chains for [start, end], generating and caching any
        dates that aren't already stored.

        Parameters
        ----------
        start, end : date range (inclusive)
        validate : run quality checks on each generated chain
        force_regenerate : ignore cache and regenerate everything

        Returns
        -------
        Single DataFrame covering all trading days in the range,
        conforming to schema.CHAIN_COLUMNS.
        """
        if force_regenerate:
            cached_dates: set[date] = set()
        else:
            cached_dates = set(self.store.cached_dates())

        # Determine which dates need generating
        all_chains = self.generator.generate_chains(start, end)
        generated_dates = set(all_chains.keys())

        # Save any dates not already cached
        new_count = 0
        for d, chain_df in all_chains.items():
            if d not in cached_dates or force_regenerate:
                if validate:
                    result = self.validator.validate(chain_df)
                    if not result.passed:
                        log.warning("Skipping %s -- validation failed:\n%s", d, result.summary())
                        continue
                self.store.save(chain_df, d)
                new_count += 1

        log.info(
            "Generated and saved %d new chains  (%d already cached)",
            new_count,
            len(generated_dates) - new_count,
        )

        # Load everything from cache (now complete)
        return self.store.load_range(start, end)

    def load_cached(self, start: date, end: date) -> pd.DataFrame:
        """Load only what's already cached — no generation."""
        return self.store.load_range(start, end)

    def load_single(self, trading_date: date) -> pd.DataFrame | None:
        """Load a single day, generating if needed."""
        cached = self.store.load(trading_date)
        if cached is not None:
            return cached

        try:
            chain = self.generator.generate_chain(trading_date)
        except ValueError as exc:
            log.warning("Cannot generate chain for %s: %s", trading_date, exc)
            return None

        result = self.validator.validate(chain)
        if not result.passed:
            log.warning("Validation failed for %s:\n%s", trading_date, result.summary())
            return None

        self.store.save(chain, trading_date)
        return chain

    def validate_cached(self, start: date, end: date) -> list[ValidationResult]:
        """Run validation on all cached chains in a range."""
        df = self.store.load_range(start, end)
        if df.empty:
            log.info("No cached data to validate for %s -> %s", start, end)
            return []
        return self.validator.validate_range(df)
