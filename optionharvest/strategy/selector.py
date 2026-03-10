"""
Strike selection for 0DTE option selling.

Given a live options chain DataFrame, selects the best strike(s)
to sell based on target premium, target delta, or both.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from optionharvest.utils.logger import get_logger

log = get_logger("selector")


@dataclass
class Selection:
    """Result of strike selection."""
    symbol: str          # OCC option symbol
    strike: float        # strike price
    option_type: str     # "put" or "call"
    mid_price: float     # mid-price at selection time
    bid: float           # bid price
    ask: float           # ask price
    open_interest: int   # open interest

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 2)


class StrikeSelector:
    """Select which option(s) to sell from a live chain."""

    def __init__(
        self,
        target_premium: float = 1.50,
        option_type: str = "put",
        strike_selection: str = "premium",
        target_delta: float = 0.10,
        min_open_interest: int = 100,
        max_bid_ask_spread: float = 0.50,
    ) -> None:
        self.target_premium = target_premium
        self.option_type = option_type
        self.strike_selection = strike_selection
        self.target_delta = target_delta
        self.min_open_interest = min_open_interest
        self.max_bid_ask_spread = max_bid_ask_spread

    @classmethod
    def from_config(cls, cfg: dict) -> "StrikeSelector":
        strategy = cfg.get("strategy", {})
        return cls(
            target_premium=strategy.get("target_premium", 1.50),
            option_type=strategy.get("option_type", "put"),
            strike_selection=strategy.get("strike_selection", "premium"),
            target_delta=strategy.get("target_delta", 0.10),
            min_open_interest=strategy.get("min_open_interest", 100),
            max_bid_ask_spread=strategy.get("max_bid_ask_spread", 0.50),
        )

    def select(
        self,
        chain: pd.DataFrame,
        underlying_price: float,
    ) -> list[Selection]:
        """
        Select strike(s) from the chain.

        Returns a list of Selection objects (1 for single leg, 2 for strangle).
        Returns empty list if no suitable option found.
        """
        if chain.empty:
            log.warning("Empty chain -- cannot select")
            return []

        selections = []

        if self.option_type in ("put", "both"):
            pick = self._pick_one(chain, underlying_price, "put")
            if pick:
                selections.append(pick)

        if self.option_type in ("call", "both"):
            pick = self._pick_one(chain, underlying_price, "call")
            if pick:
                selections.append(pick)

        if not selections:
            log.warning("No suitable options found matching criteria")
        else:
            for s in selections:
                log.info(
                    "Selected: %s strike=$%.0f mid=$%.2f bid=$%.2f ask=$%.2f OI=%d",
                    s.symbol, s.strike, s.mid_price, s.bid, s.ask, s.open_interest,
                )

        return selections

    def _pick_one(
        self,
        chain: pd.DataFrame,
        underlying_price: float,
        opt_type: str,
    ) -> Selection | None:
        """Pick a single option of the given type."""
        # Filter to the correct type
        df = chain[chain["option_type"] == opt_type].copy()
        if df.empty:
            return None

        # Only OTM options (puts below spot, calls above spot)
        if opt_type == "put":
            df = df[df["strike"] < underlying_price]
        else:
            df = df[df["strike"] > underlying_price]

        if df.empty:
            return None

        # Filter by liquidity
        df = df[df["mid"] > 0]
        if self.min_open_interest > 0:
            df = df[df["open_interest"] >= self.min_open_interest]
        if self.max_bid_ask_spread > 0:
            df = df[(df["ask"] - df["bid"]) <= self.max_bid_ask_spread]

        if df.empty:
            log.warning("No %s options pass liquidity filters", opt_type)
            return None

        # Select by premium or delta
        if self.strike_selection == "premium":
            df["diff"] = abs(df["mid"] - self.target_premium)
            best = df.loc[df["diff"].idxmin()]
        else:
            # For delta selection, we'd need delta in the chain
            # Fall back to premium if delta not available
            if "delta" in df.columns:
                target = -self.target_delta if opt_type == "put" else self.target_delta
                df["diff"] = abs(df["delta"] - target)
                best = df.loc[df["diff"].idxmin()]
            else:
                log.warning("Delta not in chain, falling back to premium selection")
                df["diff"] = abs(df["mid"] - self.target_premium)
                best = df.loc[df["diff"].idxmin()]

        return Selection(
            symbol=best["symbol"],
            strike=float(best["strike"]),
            option_type=opt_type,
            mid_price=float(best["mid"]),
            bid=float(best["bid"]),
            ask=float(best["ask"]),
            open_interest=int(best["open_interest"]),
        )
