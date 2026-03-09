"""
Fetch historical QQQ and VIX daily OHLC data via yfinance.

Data is cached locally as Parquet files so we only download once.
Subsequent calls read from cache and only fetch new dates if needed.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from optionharvest.utils.logger import get_logger

log = get_logger("market_data")

_DEFAULT_CACHE_DIR = Path("data/processed/underlying")


class MarketDataFetcher:
    """Downloads and caches daily bars for QQQ and VIX."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_underlying(
        self,
        ticker: str = "QQQ",
        start: str | date = "2020-01-01",
        end: str | date | None = None,
    ) -> pd.DataFrame:
        """
        Return daily OHLCV for *ticker* between *start* and *end*.

        Columns returned: Open, High, Low, Close, Volume  (adjusted).
        Index: DatetimeIndex named 'Date'.
        """
        end = end or (date.today() + timedelta(days=1)).isoformat()
        return self._get_or_download(ticker, str(start), str(end))

    def fetch_vix(
        self,
        start: str | date = "2020-01-01",
        end: str | date | None = None,
    ) -> pd.DataFrame:
        """Return daily OHLCV for the VIX index (^VIX)."""
        end = end or (date.today() + timedelta(days=1)).isoformat()
        return self._get_or_download("^VIX", str(start), str(end))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_path(self, ticker: str) -> Path:
        safe_name = ticker.replace("^", "").replace("/", "_")
        return self.cache_dir / f"{safe_name}.parquet"

    def _get_or_download(
        self, ticker: str, start: str, end: str
    ) -> pd.DataFrame:
        cache_file = self._cache_path(ticker)
        requested_start = date.fromisoformat(start) if isinstance(start, str) else start
        requested_end = date.fromisoformat(end) if isinstance(end, str) else end

        if cache_file.exists():
            cached = pd.read_parquet(cache_file)
            cached.index = pd.to_datetime(cached.index)
            first_cached = cached.index.min().date()
            last_cached = cached.index.max().date()

            # Check if cache fully covers the requested range
            covers_start = first_cached <= requested_start + timedelta(days=3)
            covers_end = last_cached >= requested_end - timedelta(days=3)

            if covers_start and covers_end:
                log.info(
                    "Cache hit for %s (%d rows, %s to %s)",
                    ticker,
                    len(cached),
                    first_cached,
                    last_cached,
                )
                mask = (cached.index >= start) & (cached.index <= end)
                return cached.loc[mask]

            # Cache is partial — download the full range and merge
            log.info(
                "Cache partial for %s (have %s to %s, need %s to %s)",
                ticker, first_cached, last_cached, requested_start, requested_end,
            )
            new_data = self._download(ticker, start, end)
            if not new_data.empty:
                combined = pd.concat([cached, new_data])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined.sort_index(inplace=True)
                combined.to_parquet(cache_file)
                mask = (combined.index >= start) & (combined.index <= end)
                return combined.loc[mask]
            mask = (cached.index >= start) & (cached.index <= end)
            return cached.loc[mask]

        log.info("No cache for %s -- downloading %s to %s", ticker, start, end)
        data = self._download(ticker, start, end)
        if not data.empty:
            data.to_parquet(cache_file)
        return data

    @staticmethod
    def _download(ticker: str, start: str, end: str) -> pd.DataFrame:
        """Call yfinance and normalise the result."""
        log.info("yfinance download: %s  [%s -> %s]", ticker, start, end)
        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )

        if df.empty:
            log.warning("No data returned for %s [%s -> %s]", ticker, start, end)
            return df

        # yfinance sometimes returns MultiIndex columns for single tickers
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Standardise column names
        df.columns = [c.strip().title() for c in df.columns]

        # Ensure expected columns exist
        expected = {"Open", "High", "Low", "Close", "Volume"}
        missing = expected - set(df.columns)
        if missing:
            log.warning("Missing columns in %s data: %s", ticker, missing)

        return df
