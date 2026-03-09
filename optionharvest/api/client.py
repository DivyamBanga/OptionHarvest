"""
Alpaca client wrapper for OptionHarvest.

Initializes and manages all three Alpaca clients:
  - TradingClient: account info, option contracts, orders, positions
  - OptionHistoricalDataClient: option quotes and snapshots
  - StockHistoricalDataClient: QQQ underlying price

Loads credentials from .env file or environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient

from optionharvest.utils.logger import get_logger

log = get_logger("client")


class AlpacaClient:
    """Single entry point for all Alpaca API access."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
    ) -> None:
        # Load from .env if not provided directly
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)

        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET", "")
        self.paper = paper if api_key else os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Alpaca API credentials not found. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET in .env or pass them directly."
            )

        # Initialize clients
        self.trading = TradingClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
            paper=self.paper,
        )

        self.options_data = OptionHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
        )

        self.stock_data = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
        )

        log.info(
            "Alpaca client initialized (paper=%s)", self.paper
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """
        Get account summary.

        Returns dict with keys: equity, cash, buying_power,
        portfolio_value, status, options_trading_level, etc.
        """
        acct = self.trading.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "status": acct.status.value if acct.status else "unknown",
            "pattern_day_trader": acct.pattern_day_trader,
            "options_trading_level": getattr(acct, "options_trading_level", None),
        }

    def verify_connection(self) -> bool:
        """
        Test the connection and log account details.

        Returns True if connection is healthy, False otherwise.
        """
        try:
            info = self.get_account()
            log.info("Account status: %s", info["status"])
            log.info("Equity: $%.2f", info["equity"])
            log.info("Buying power: $%.2f", info["buying_power"])
            log.info("Cash: $%.2f", info["cash"])
            log.info("Options level: %s", info["options_trading_level"])
            log.info("Paper trading: %s", self.paper)
            return info["status"] == "ACTIVE"
        except Exception as exc:
            log.error("Connection verification failed: %s", exc)
            return False
