"""Tests for Alpaca client wrapper -- uses live paper trading API."""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

# Skip all tests if no API keys configured
pytestmark = pytest.mark.skipif(
    not os.getenv("ALPACA_API_KEY"),
    reason="ALPACA_API_KEY not set -- skipping live API tests",
)


class TestAlpacaClient:
    """Live connection tests against Alpaca paper trading."""

    def test_client_initializes(self):
        from optionharvest.api.client import AlpacaClient
        client = AlpacaClient()
        assert client.paper is True
        assert client.trading is not None
        assert client.options_data is not None
        assert client.stock_data is not None

    def test_verify_connection(self):
        from optionharvest.api.client import AlpacaClient
        client = AlpacaClient()
        assert client.verify_connection() is True

    def test_get_account(self):
        from optionharvest.api.client import AlpacaClient
        client = AlpacaClient()
        info = client.get_account()
        assert "equity" in info
        assert "buying_power" in info
        assert "cash" in info
        assert info["equity"] > 0
        assert info["status"] == "ACTIVE"

    def test_client_fails_without_keys(self, monkeypatch):
        from optionharvest.api.client import AlpacaClient
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
        # Prevent .env from being loaded
        monkeypatch.setattr("optionharvest.api.client.load_dotenv", lambda *a, **k: None)
        with pytest.raises(ValueError, match="credentials"):
            AlpacaClient(api_key="", api_secret="")


class TestMarketData:
    """Live market data tests -- may fail outside market hours."""

    def test_get_underlying_price(self):
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.market_data import MarketData
        client = AlpacaClient()
        md = MarketData(client)
        price = md.get_underlying_price("QQQ")
        # QQQ should be somewhere between $100 and $1000
        assert 100 < price < 1000

    def test_get_0dte_contracts(self):
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.market_data import MarketData
        client = AlpacaClient()
        md = MarketData(client)
        contracts = md.get_0dte_contracts("QQQ")
        # May be empty if no 0DTE options today (weekend/holiday)
        # Just verify it returns a list without errors
        assert isinstance(contracts, list)

    def test_build_chain(self):
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.market_data import MarketData
        client = AlpacaClient()
        md = MarketData(client)
        chain = md.build_chain("QQQ")
        # Chain may be empty on non-trading days
        if not chain.empty:
            assert "symbol" in chain.columns
            assert "strike" in chain.columns
            assert "bid" in chain.columns
            assert "ask" in chain.columns
            assert "mid" in chain.columns


class TestOrderManager:
    """Basic order manager tests (no actual trades placed)."""

    def test_get_option_positions(self):
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.orders import OrderManager
        client = AlpacaClient()
        om = OrderManager(client)
        positions = om.get_option_positions()
        assert isinstance(positions, list)

    def test_get_open_orders(self):
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.orders import OrderManager
        client = AlpacaClient()
        om = OrderManager(client)
        orders = om.get_open_orders()
        assert isinstance(orders, list)
