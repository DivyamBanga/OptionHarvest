"""
Live market data from Alpaca: QQQ price, 0DTE options chain, option quotes.

This module fetches real-time data -- no simulation, no modeling.
Everything comes directly from Alpaca's market data API.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import pandas as pd

from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import AssetStatus, ContractType
from alpaca.data.requests import (
    OptionLatestQuoteRequest,
    OptionSnapshotRequest,
    StockLatestTradeRequest,
)

from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.api.client import AlpacaClient

log = get_logger("market_data")


class MarketData:
    """Fetch live QQQ and options data from Alpaca."""

    def __init__(self, client: "AlpacaClient") -> None:
        self.client = client

    # ------------------------------------------------------------------
    # Underlying (QQQ)
    # ------------------------------------------------------------------

    def get_underlying_price(self, symbol: str = "QQQ") -> float:
        """Get the latest trade price for QQQ (or any symbol)."""
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        response = self.client.stock_data.get_stock_latest_trade(req)
        price = float(response[symbol].price)
        log.info("%s latest price: $%.2f", symbol, price)
        return price

    # ------------------------------------------------------------------
    # Options chain
    # ------------------------------------------------------------------

    def get_0dte_contracts(
        self,
        underlying: str = "QQQ",
        strike_range_pct: float = 0.10,
        option_type: str | None = None,
    ) -> list:
        """
        Fetch all active 0DTE option contracts for today.

        Parameters
        ----------
        underlying : ticker symbol
        strike_range_pct : filter strikes within +/- this % of spot
        option_type : "put", "call", or None for both

        Returns
        -------
        List of option contract objects from Alpaca.
        """
        spot = self.get_underlying_price(underlying)
        today = date.today()

        min_strike = round(spot * (1 - strike_range_pct), 2)
        max_strike = round(spot * (1 + strike_range_pct), 2)

        req_params = {
            "underlying_symbols": [underlying],
            "expiration_date": today.isoformat(),
            "status": AssetStatus.ACTIVE,
            "strike_price_gte": str(min_strike),
            "strike_price_lte": str(max_strike),
            "limit": 200,
        }

        if option_type == "put":
            req_params["type"] = ContractType.PUT
        elif option_type == "call":
            req_params["type"] = ContractType.CALL

        req = GetOptionContractsRequest(**req_params)
        response = self.client.trading.get_option_contracts(req)
        contracts = response.option_contracts if response.option_contracts else []

        log.info(
            "Found %d 0DTE contracts for %s (strikes $%.0f-$%.0f, expiry=%s)",
            len(contracts),
            underlying,
            min_strike,
            max_strike,
            today,
        )
        return contracts

    # ------------------------------------------------------------------
    # Option quotes
    # ------------------------------------------------------------------

    def get_option_quotes(self, symbols: list[str]) -> dict:
        """
        Get latest bid/ask quotes for a list of option symbols.

        Returns dict mapping symbol -> {bid, ask, mid, bid_size, ask_size}.
        """
        if not symbols:
            return {}

        # Alpaca may limit batch size, so chunk if needed
        quotes = {}
        chunk_size = 100
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i : i + chunk_size]
            req = OptionLatestQuoteRequest(symbol_or_symbols=chunk)
            response = self.client.options_data.get_option_latest_quote(req)

            for sym, quote in response.items():
                bid = float(quote.bid_price) if quote.bid_price else 0.0
                ask = float(quote.ask_price) if quote.ask_price else 0.0
                mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else 0.0
                quotes[sym] = {
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "bid_size": int(quote.bid_size) if quote.bid_size else 0,
                    "ask_size": int(quote.ask_size) if quote.ask_size else 0,
                }

        log.info("Fetched quotes for %d options", len(quotes))
        return quotes

    # ------------------------------------------------------------------
    # Build full chain DataFrame
    # ------------------------------------------------------------------

    def build_chain(
        self,
        underlying: str = "QQQ",
        strike_range_pct: float = 0.10,
        option_type: str | None = None,
        min_open_interest: int = 0,
    ) -> pd.DataFrame:
        """
        Build a complete 0DTE chain DataFrame with live quotes.

        Returns DataFrame with columns:
            symbol, strike, option_type, expiration,
            bid, ask, mid, bid_size, ask_size, open_interest
        """
        contracts = self.get_0dte_contracts(
            underlying, strike_range_pct, option_type
        )

        if not contracts:
            log.warning("No 0DTE contracts found for %s", underlying)
            return pd.DataFrame()

        # Build contract info
        rows = []
        symbols = []
        for c in contracts:
            symbols.append(c.symbol)
            rows.append({
                "symbol": c.symbol,
                "strike": float(c.strike_price),
                "option_type": c.type.value if c.type else "unknown",
                "expiration": str(c.expiration_date),
                "open_interest": int(c.open_interest) if c.open_interest else 0,
            })

        # Fetch live quotes for all contracts
        quotes = self.get_option_quotes(symbols)

        # Merge quotes into contract data
        for row in rows:
            q = quotes.get(row["symbol"], {})
            row["bid"] = q.get("bid", 0.0)
            row["ask"] = q.get("ask", 0.0)
            row["mid"] = q.get("mid", 0.0)
            row["bid_size"] = q.get("bid_size", 0)
            row["ask_size"] = q.get("ask_size", 0)

        df = pd.DataFrame(rows)

        # Filter by open interest
        if min_open_interest > 0:
            before = len(df)
            df = df[df["open_interest"] >= min_open_interest]
            log.info(
                "Filtered by OI >= %d: %d -> %d contracts",
                min_open_interest,
                before,
                len(df),
            )

        # Sort by strike
        df = df.sort_values(["option_type", "strike"]).reset_index(drop=True)

        log.info(
            "Chain built: %d options (%d puts, %d calls)",
            len(df),
            (df["option_type"] == "put").sum(),
            (df["option_type"] == "call").sum(),
        )
        return df
