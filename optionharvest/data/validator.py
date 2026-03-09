"""
Data quality checks for options chain DataFrames.

The validator runs a battery of checks and returns a structured report
so the caller can decide whether to trust the data or investigate
further.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from optionharvest.data import schema as S
from optionharvest.utils.logger import get_logger

log = get_logger("validator")


@dataclass
class ValidationResult:
    """Outcome of validating a single chain DataFrame."""

    trading_date: date | None = None
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        parts = [f"[{status}] {self.trading_date}"]
        for e in self.errors:
            parts.append(f"  ERROR: {e}")
        for w in self.warnings:
            parts.append(f"  WARN:  {w}")
        return "\n".join(parts)


class ChainValidator:
    """Run quality checks on a chain DataFrame."""

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """Validate a single day's chain and return a structured result."""
        result = ValidationResult()

        if df.empty:
            result.add_error("DataFrame is empty")
            return result

        # Determine the trading date
        if S.DATE in df.columns:
            dates = df[S.DATE].unique()
            if len(dates) == 1:
                result.trading_date = dates[0]
            else:
                result.add_warning(f"Multiple dates in one chain: {list(dates)}")
                result.trading_date = dates[0]

        self._check_columns(df, result)
        self._check_option_types(df, result)
        self._check_prices(df, result)
        self._check_strikes(df, result)
        self._check_greeks(df, result)

        if result.passed:
            log.info("Validation PASSED for %s", result.trading_date)
        else:
            log.warning("Validation FAILED for %s:\n%s", result.trading_date, result.summary())

        return result

    def validate_range(self, df: pd.DataFrame) -> list[ValidationResult]:
        """Validate a multi-day DataFrame, returning one result per date."""
        if df.empty:
            return [ValidationResult(passed=False, errors=["DataFrame is empty"])]

        results: list[ValidationResult] = []
        for d, group in df.groupby(S.DATE):
            results.append(self.validate(group))
        return results

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_columns(df: pd.DataFrame, result: ValidationResult) -> None:
        missing = set(S.CHAIN_COLUMNS) - set(df.columns)
        if missing:
            result.add_error(f"Missing columns: {sorted(missing)}")

    @staticmethod
    def _check_option_types(df: pd.DataFrame, result: ValidationResult) -> None:
        if S.OPTION_TYPE not in df.columns:
            return
        invalid = set(df[S.OPTION_TYPE].unique()) - S.VALID_OPTION_TYPES
        if invalid:
            result.add_error(f"Invalid option_type values: {invalid}")

        n_calls = (df[S.OPTION_TYPE] == "call").sum()
        n_puts = (df[S.OPTION_TYPE] == "put").sum()
        if n_calls == 0:
            result.add_warning("No call options in chain")
        if n_puts == 0:
            result.add_warning("No put options in chain")

    @staticmethod
    def _check_prices(df: pd.DataFrame, result: ValidationResult) -> None:
        for col in (S.OPEN, S.HIGH, S.LOW, S.CLOSE):
            if col not in df.columns:
                continue
            n_neg = (df[col] < 0).sum()
            if n_neg > 0:
                result.add_error(f"{col} has {n_neg} negative values")

            n_nan = df[col].isna().sum()
            if n_nan > 0:
                result.add_error(f"{col} has {n_nan} NaN values")

        # OHLC ordering: high >= max(open, close) and low <= min(open, close)
        price_cols = {S.OPEN, S.HIGH, S.LOW, S.CLOSE}
        if price_cols.issubset(df.columns):
            bad_high = (df[S.HIGH] < df[S.OPEN]).sum() + (df[S.HIGH] < df[S.CLOSE]).sum()
            if bad_high > 0:
                result.add_warning(f"High < Open or High < Close in {bad_high} rows")

            bad_low = (df[S.LOW] > df[S.OPEN]).sum() + (df[S.LOW] > df[S.CLOSE]).sum()
            if bad_low > 0:
                result.add_warning(f"Low > Open or Low > Close in {bad_low} rows")

        # Bid/ask sanity
        if S.BID_OPEN in df.columns and S.ASK_OPEN in df.columns:
            crossed = (df[S.BID_OPEN] > df[S.ASK_OPEN]).sum()
            if crossed > 0:
                result.add_error(f"Bid > Ask in {crossed} rows")

    @staticmethod
    def _check_strikes(df: pd.DataFrame, result: ValidationResult) -> None:
        if S.STRIKE not in df.columns or S.UNDERLYING_OPEN not in df.columns:
            return

        spot = df[S.UNDERLYING_OPEN].iloc[0]
        min_strike = df[S.STRIKE].min()
        max_strike = df[S.STRIKE].max()

        if min_strike > spot * 0.80:
            result.add_warning(
                f"Narrowest put strike ({min_strike}) > 80% of spot ({spot:.2f})"
            )
        if max_strike < spot * 1.20:
            result.add_warning(
                f"Widest call strike ({max_strike}) < 120% of spot ({spot:.2f})"
            )

    @staticmethod
    def _check_greeks(df: pd.DataFrame, result: ValidationResult) -> None:
        if S.DELTA not in df.columns:
            return

        calls = df[df[S.OPTION_TYPE] == "call"]
        puts = df[df[S.OPTION_TYPE] == "put"]

        if not calls.empty:
            bad = ((calls[S.DELTA] < 0) | (calls[S.DELTA] > 1)).sum()
            if bad > 0:
                result.add_warning(f"Call delta out of [0, 1] in {bad} rows")

        if not puts.empty:
            bad = ((puts[S.DELTA] > 0) | (puts[S.DELTA] < -1)).sum()
            if bad > 0:
                result.add_warning(f"Put delta out of [-1, 0] in {bad} rows")
