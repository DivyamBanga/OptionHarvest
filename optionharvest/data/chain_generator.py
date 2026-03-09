"""
Generate synthetic 0DTE options chains from real QQQ + VIX data.

For each historical trading day this module builds a full options chain:
  - OPEN prices  → Black-Scholes model (modeled, ~85-90 % accurate)
  - CLOSE prices → exact intrinsic value at expiry (0 % error)
  - HIGH prices  → BS at the worst underlying level for the seller
  - LOW prices   → minimum of open and close

The chain is returned as a DataFrame conforming to schema.CHAIN_COLUMNS.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from optionharvest.data import schema as S
from optionharvest.data.market_data import MarketDataFetcher
from optionharvest.data.pricer import apply_skew, bs_delta, bs_price, estimate_iv
from optionharvest.utils.logger import get_logger

log = get_logger("chain_generator")

# Trading year: 252 days × 6.5 hours each
_TRADING_HOURS_PER_DAY = 6.5
_TRADING_DAYS_PER_YEAR = 252
_T_OPEN = 1.0 / _TRADING_DAYS_PER_YEAR  # ≈ 0.00397 years ≈ 6.5 hours


class ChainGeneratorConfig:
    """Parameters that control chain generation."""

    def __init__(
        self,
        strike_range_pct: float = 0.10,
        strike_spacing: float = 1.0,
        risk_free_rate: float = 0.05,
        qqq_vix_ratio: float = 1.15,
        term_structure_adj: float = 0.90,
        put_skew_slope: float = 1.5,
        call_skew_slope: float = 0.3,
    ) -> None:
        self.strike_range_pct = strike_range_pct
        self.strike_spacing = strike_spacing
        self.risk_free_rate = risk_free_rate
        self.qqq_vix_ratio = qqq_vix_ratio
        self.term_structure_adj = term_structure_adj
        self.put_skew_slope = put_skew_slope
        self.call_skew_slope = call_skew_slope

    @classmethod
    def from_yaml(cls, cfg: dict) -> "ChainGeneratorConfig":
        """Build from the 'chain' + 'iv_model' sections of settings.yaml."""
        chain = cfg.get("chain", {})
        iv = cfg.get("iv_model", {})
        return cls(
            strike_range_pct=chain.get("strike_range_pct", 0.10),
            strike_spacing=chain.get("strike_spacing", 1.0),
            risk_free_rate=chain.get("risk_free_rate", 0.05),
            qqq_vix_ratio=iv.get("qqq_vix_ratio", 1.15),
            term_structure_adj=iv.get("term_structure_0dte", 0.90),
            put_skew_slope=iv.get("skew_put_slope", 1.5),
            call_skew_slope=iv.get("skew_call_slope", 0.3),
        )


class ChainGenerator:
    """Builds synthetic 0DTE chains from underlying + VIX data."""

    def __init__(
        self,
        config: ChainGeneratorConfig | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.cfg = config or ChainGeneratorConfig()
        self.fetcher = MarketDataFetcher(cache_dir=cache_dir)

        # Lazily loaded and cached
        self._qqq: pd.DataFrame | None = None
        self._vix: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_chain(self, trading_date: date) -> pd.DataFrame:
        """
        Generate the full 0DTE chain for a single trading day.

        Returns a DataFrame with columns defined in schema.CHAIN_COLUMNS.
        Raises ValueError if the date is not a trading day (no data).
        """
        qqq_row = self._underlying_row(trading_date)
        vix_close = self._vix_close(trading_date)

        spot_open = float(qqq_row["Open"])
        spot_high = float(qqq_row["High"])
        spot_low = float(qqq_row["Low"])
        spot_close = float(qqq_row["Close"])

        atm_iv = estimate_iv(
            vix_close,
            qqq_vix_ratio=self.cfg.qqq_vix_ratio,
            term_structure_adj=self.cfg.term_structure_adj,
        )

        strikes = self._generate_strikes(spot_open)
        r = self.cfg.risk_free_rate

        rows: list[dict] = []
        for strike in strikes:
            for opt_type in ("call", "put"):
                iv = apply_skew(
                    atm_iv,
                    strike,
                    spot_open,
                    opt_type,
                    put_skew_slope=self.cfg.put_skew_slope,
                    call_skew_slope=self.cfg.call_skew_slope,
                )

                # --- OPEN (modeled via BS) ---
                open_price = bs_price(spot_open, strike, _T_OPEN, r, iv, opt_type)

                # --- CLOSE (exact intrinsic at expiry) ---
                close_price = (
                    max(0.0, spot_close - strike)
                    if opt_type == "call"
                    else max(0.0, strike - spot_close)
                )

                # --- HIGH (worst case for option seller) ---
                worst_spot = spot_low if opt_type == "put" else spot_high
                high_price = bs_price(
                    worst_spot, strike, _T_OPEN / 2, r, iv, opt_type
                )
                high_price = max(high_price, open_price, close_price)

                # --- LOW ---
                low_price = min(open_price, close_price)

                # --- DELTA at open ---
                delta = bs_delta(spot_open, strike, _T_OPEN, r, iv, opt_type)

                # --- BID / ASK (simple spread model) ---
                spread = max(0.01, 0.02 * open_price)
                bid = round(max(0.0, open_price - spread / 2), 2)
                ask = round(open_price + spread / 2, 2)

                rows.append(
                    {
                        S.DATE: trading_date,
                        S.STRIKE: strike,
                        S.OPTION_TYPE: opt_type,
                        S.OPEN: round(open_price, 2),
                        S.HIGH: round(high_price, 2),
                        S.LOW: round(low_price, 2),
                        S.CLOSE: round(close_price, 2),
                        S.VOLUME: 0,
                        S.BID_OPEN: bid,
                        S.ASK_OPEN: ask,
                        S.DELTA: round(delta, 4),
                        S.IMPLIED_VOL: round(iv, 4),
                        S.UNDERLYING_OPEN: round(spot_open, 2),
                        S.UNDERLYING_HIGH: round(spot_high, 2),
                        S.UNDERLYING_LOW: round(spot_low, 2),
                        S.UNDERLYING_CLOSE: round(spot_close, 2),
                    }
                )

        df = pd.DataFrame(rows, columns=S.CHAIN_COLUMNS)
        log.info(
            "Generated chain for %s -- %d rows, spot=%.2f, IV=%.1f%%",
            trading_date,
            len(df),
            spot_open,
            atm_iv * 100,
        )
        return df

    def generate_chains(
        self,
        start: date,
        end: date,
    ) -> dict[date, pd.DataFrame]:
        """
        Generate chains for every trading day in [start, end].

        Returns a dict mapping each date to its chain DataFrame.
        """
        trading_dates = self._trading_dates(start, end)
        log.info(
            "Generating chains for %d trading days (%s -> %s)",
            len(trading_dates),
            start,
            end,
        )

        chains: dict[date, pd.DataFrame] = {}
        for i, d in enumerate(trading_dates):
            try:
                chains[d] = self.generate_chain(d)
            except (ValueError, KeyError) as exc:
                log.warning("Skipping %s: %s", d, exc)
            if (i + 1) % 50 == 0:
                log.info("  … generated %d / %d", i + 1, len(trading_dates))

        log.info("Done -- %d chains generated", len(chains))
        return chains

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_data(self, start: date, end: date) -> None:
        """Ensure QQQ and VIX data is loaded for the requested range."""
        margin = pd.Timedelta(days=10)
        s = (pd.Timestamp(start) - margin).strftime("%Y-%m-%d")
        e = (pd.Timestamp(end) + margin).strftime("%Y-%m-%d")

        if self._qqq is None:
            self._qqq = self.fetcher.fetch_underlying("QQQ", start=s, end=e)
        if self._vix is None:
            self._vix = self.fetcher.fetch_vix(start=s, end=e)

    def _underlying_row(self, d: date) -> pd.Series:
        if self._qqq is None or pd.Timestamp(d) not in self._qqq.index:
            self._qqq = self.fetcher.fetch_underlying(
                "QQQ",
                start=(pd.Timestamp(d) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                end=(pd.Timestamp(d) + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
            )
        ts = pd.Timestamp(d)
        if ts not in self._qqq.index:
            raise ValueError(f"{d} is not a trading day (no QQQ data)")
        return self._qqq.loc[ts]

    def _vix_close(self, d: date) -> float:
        if self._vix is None or pd.Timestamp(d) not in self._vix.index:
            self._vix = self.fetcher.fetch_vix(
                start=(pd.Timestamp(d) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                end=(pd.Timestamp(d) + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
            )
        ts = pd.Timestamp(d)
        if ts not in self._vix.index:
            raise ValueError(f"No VIX data for {d}")
        return float(self._vix.loc[ts, "Close"])

    def _trading_dates(self, start: date, end: date) -> list[date]:
        """Return sorted list of dates where QQQ data exists."""
        self._load_data(start, end)
        assert self._qqq is not None
        mask = (self._qqq.index >= pd.Timestamp(start)) & (
            self._qqq.index <= pd.Timestamp(end)
        )
        return [ts.date() for ts in self._qqq.index[mask]]

    def _generate_strikes(self, spot: float) -> np.ndarray:
        """Generate strike prices around the current spot."""
        pct = self.cfg.strike_range_pct
        spacing = self.cfg.strike_spacing
        lo = math._floor_to(spot * (1 - pct), spacing)
        hi = math._ceil_to(spot * (1 + pct), spacing)
        return np.arange(lo, hi + spacing, spacing)


# ---------------------------------------------------------------------------
# Small math helpers (avoid importing the whole math module at module level)
# ---------------------------------------------------------------------------

import math as _math  # noqa: E402  (deferred to keep module-level imports clean)


class math:
    """Namespace for strike-rounding helpers."""

    @staticmethod
    def _floor_to(value: float, multiple: float) -> float:
        return _math.floor(value / multiple) * multiple

    @staticmethod
    def _ceil_to(value: float, multiple: float) -> float:
        return _math.ceil(value / multiple) * multiple
