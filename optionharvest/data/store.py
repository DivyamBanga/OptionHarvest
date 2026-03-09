"""
Local Parquet storage for generated options chains.

Layout on disk:
    data/processed/chains/2024-01-02.parquet
    data/processed/chains/2024-01-03.parquet
    ...

Each file stores a single day's 0DTE chain conforming to
schema.CHAIN_COLUMNS.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from optionharvest.data import schema as S
from optionharvest.utils.logger import get_logger

log = get_logger("store")

_DEFAULT_CHAINS_DIR = Path("data/processed/chains")


class ChainStore:
    """Read / write daily chain Parquet files."""

    def __init__(self, chains_dir: Path | str | None = None) -> None:
        self.chains_dir = Path(chains_dir) if chains_dir else _DEFAULT_CHAINS_DIR
        self.chains_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, chain: pd.DataFrame, trading_date: date) -> Path:
        """
        Persist a single day's chain to Parquet.

        Returns the path to the written file.
        """
        path = self._path_for(trading_date)
        chain[S.CHAIN_COLUMNS].to_parquet(path, index=False)
        log.info("Saved chain %s  (%d rows)", path.name, len(chain))
        return path

    def load(self, trading_date: date) -> pd.DataFrame | None:
        """
        Load a single day's chain from Parquet.

        Returns None if the file does not exist.
        """
        path = self._path_for(trading_date)
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        # Restore date column to datetime.date objects
        df[S.DATE] = pd.to_datetime(df[S.DATE]).dt.date
        return df

    def load_range(self, start: date, end: date) -> pd.DataFrame:
        """
        Load and concatenate chains for every day in [start, end]
        that has a cached file.

        Returns an empty DataFrame (with correct columns) if nothing
        is cached.
        """
        frames: list[pd.DataFrame] = []
        for path in sorted(self.chains_dir.glob("*.parquet")):
            file_date = self._date_from_path(path)
            if file_date and start <= file_date <= end:
                df = pd.read_parquet(path)
                df[S.DATE] = pd.to_datetime(df[S.DATE]).dt.date
                frames.append(df)

        if not frames:
            return pd.DataFrame(columns=S.CHAIN_COLUMNS)

        combined = pd.concat(frames, ignore_index=True)
        log.info(
            "Loaded %d days (%d rows) from cache  [%s -> %s]",
            len(frames),
            len(combined),
            start,
            end,
        )
        return combined

    def has(self, trading_date: date) -> bool:
        """Check whether a chain file exists for this date."""
        return self._path_for(trading_date).exists()

    def cached_dates(self) -> list[date]:
        """Return sorted list of all dates that have cached chain files."""
        dates: list[date] = []
        for path in self.chains_dir.glob("*.parquet"):
            d = self._date_from_path(path)
            if d:
                dates.append(d)
        return sorted(dates)

    def delete(self, trading_date: date) -> bool:
        """Remove a cached chain file. Returns True if deleted."""
        path = self._path_for(trading_date)
        if path.exists():
            path.unlink()
            log.info("Deleted chain %s", path.name)
            return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _path_for(self, d: date) -> Path:
        return self.chains_dir / f"{d.isoformat()}.parquet"

    @staticmethod
    def _date_from_path(path: Path) -> date | None:
        try:
            return date.fromisoformat(path.stem)
        except ValueError:
            return None
