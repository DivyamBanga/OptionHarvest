"""
Main trading bot orchestrator.

Ties together all components for the full daily flow:
    connect -> fetch chain -> select strike -> place order ->
    monitor -> check exits -> close -> log P&L
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from optionharvest.api.client import AlpacaClient
from optionharvest.api.market_data import MarketData
from optionharvest.api.orders import OrderManager
from optionharvest.analytics.tracker import TradeTracker
from optionharvest.risk.circuit_breaker import CircuitBreaker
from optionharvest.risk.limits import RiskLimits
from optionharvest.strategy.selector import StrikeSelector
from optionharvest.strategy.signals import SignalEngine
from optionharvest.trading.monitor import PositionMonitor
from optionharvest.utils.calendar import TradingCalendar, now_et
from optionharvest.utils.logger import get_logger

log = get_logger("executor")


def load_config(path: str = "config/settings.yaml") -> dict:
    """Load YAML config file."""
    with open(path) as f:
        return yaml.safe_load(f)


class TradingBot:
    """
    The main trading bot. Runs one full trading day cycle.

    Usage:
        bot = TradingBot.from_config("config/settings.yaml")
        bot.run()
    """

    def __init__(
        self,
        client: AlpacaClient,
        market_data: MarketData,
        orders: OrderManager,
        calendar: TradingCalendar,
        selector: StrikeSelector,
        signals: SignalEngine,
        limits: RiskLimits,
        circuit_breaker: CircuitBreaker,
        tracker: TradeTracker,
        cfg: dict,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.orders = orders
        self.calendar = calendar
        self.selector = selector
        self.signals = signals
        self.limits = limits
        self.circuit_breaker = circuit_breaker
        self.tracker = tracker
        self.cfg = cfg

        # Runtime state
        self._qqq_open: float = 0.0
        self._account_equity: float = 0.0

    @classmethod
    def from_config(cls, config_path: str = "config/settings.yaml") -> "TradingBot":
        """Build the bot from a YAML config file."""
        cfg = load_config(config_path)

        client = AlpacaClient()
        market_data = MarketData(client)
        orders = OrderManager(client)
        calendar = TradingCalendar(client)

        selector = StrikeSelector.from_config(cfg)
        signals = SignalEngine.from_config(cfg)
        limits = RiskLimits.from_config(cfg)
        circuit_breaker = CircuitBreaker.from_config(cfg)
        tracker = TradeTracker.from_config(cfg)

        return cls(
            client=client,
            market_data=market_data,
            orders=orders,
            calendar=calendar,
            selector=selector,
            signals=signals,
            limits=limits,
            circuit_breaker=circuit_breaker,
            tracker=tracker,
            cfg=cfg,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the full daily trading cycle."""
        log.info("=== OptionHarvest starting ===")

        # Step 1: Connect and verify
        if not self._startup_checks():
            return

        # Step 2: Wait for entry time
        self._wait_for_entry()

        # Step 3: Enter a trade
        trade_result = self._enter_trade()
        if trade_result is None:
            log.info("No trade entered today -- shutting down")
            self._end_of_day()
            return

        # Step 4: Monitor until exit
        exit_result = self._monitor_position(trade_result)

        # Step 5: Record and clean up
        self._record_trade(trade_result, exit_result)
        self._end_of_day()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _startup_checks(self) -> bool:
        """Verify connection, account status, and trading day."""
        try:
            if not self.client.verify_connection():
                log.error("Alpaca connection failed -- aborting")
                return False

            acct = self.client.get_account()
            self._account_equity = acct["equity"]
            log.info("Account equity: $%.2f", self._account_equity)

            # Check if it's a trading day
            if not self.calendar.is_trading_day():
                log.info("Not a trading day -- skipping")
                return False

            # Check weekly loss limit
            if self.limits.weekly_loss_limit_hit():
                log.warning("Weekly loss limit hit -- skipping today")
                return False

            # Check for existing option positions
            positions = self.orders.get_option_positions()
            if positions:
                log.warning(
                    "Already have %d open option position(s) -- skipping entry",
                    len(positions),
                )
                return False

            return True

        except Exception as exc:
            log.error("Startup check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Wait for entry
    # ------------------------------------------------------------------

    def _wait_for_entry(self) -> None:
        """Wait until the market is open and past entry time."""
        entry_time = self.cfg.get("execution", {}).get("entry_time", "09:31")

        while not self.calendar.is_market_open():
            secs = 30
            log.info("Market not open yet -- waiting %ds", secs)
            time.sleep(secs)

        while not self.calendar.is_after_entry_time(entry_time):
            secs = self.calendar.seconds_until(entry_time)
            wait = min(max(secs, 1), 30)
            log.info("Waiting for entry time %s ET (%.0fs away)", entry_time, secs)
            time.sleep(wait)

        log.info("Entry time reached -- proceeding")

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def _enter_trade(self) -> dict[str, Any] | None:
        """Fetch chain, select strike, place sell order, wait for fill."""

        # Pre-trade checks
        daily_limit_hit = self.limits.daily_loss_limit_hit()
        has_positions = len(self.orders.get_option_positions()) > 0

        should_enter, reason = self.signals.check_entry(
            calendar=self.calendar,
            has_open_position=has_positions,
            daily_loss_limit_hit=daily_limit_hit,
        )
        if not should_enter:
            log.info("Entry blocked: %s", reason)
            return None

        # Get QQQ open price (for circuit breaker reference)
        self._qqq_open = self.market_data.get_underlying_price("QQQ")
        log.info("QQQ price at entry: $%.2f", self._qqq_open)

        # Build the live chain
        chain = self.market_data.build_chain(
            underlying="QQQ",
            strike_range_pct=self.cfg.get("chain", {}).get("strike_range_pct", 0.10),
        )
        if chain.empty:
            log.warning("Empty chain -- cannot trade today")
            return None

        # Select strike(s)
        selections = self.selector.select(chain, self._qqq_open)
        if not selections:
            log.warning("No suitable strike found -- skipping today")
            return None

        # Check position sizing
        selection = selections[0]  # First leg (or only leg for single)
        acct = self.client.get_account()
        trade_risk = selection.mid_price * 100  # risk per contract in dollars
        ok, msg = self.limits.check_position_size(trade_risk, acct["equity"])
        if not ok:
            log.warning("Position size check failed: %s", msg)
            return None

        # Check buying power
        ok, msg = self.limits.check_buying_power(
            required=trade_risk,
            available=acct["buying_power"],
        )
        if not ok:
            log.warning("Buying power check failed: %s", msg)
            return None

        # Place sell-to-open order
        num_contracts = self.cfg.get("strategy", {}).get("num_contracts", 1)
        order = self.orders.sell_to_open(
            symbol=selection.symbol,
            qty=num_contracts,
            limit_price=selection.mid_price,
        )

        # Wait for fill (with price adjustment)
        filled = self._wait_for_fill_with_adjustment(
            order, selection.bid, max_adjustments=3,
        )

        if filled["status"] != "filled":
            log.warning("Order not filled (status=%s) -- cancelling", filled["status"])
            self.orders.cancel_all_orders()
            return None

        entry_price = filled["filled_avg_price"] or selection.mid_price
        entry_time = now_et().strftime("%H:%M:%S")

        log.info(
            "TRADE ENTERED: %s x%d @ $%.2f",
            selection.symbol, num_contracts, entry_price,
        )

        return {
            "symbol": selection.symbol,
            "strike": selection.strike,
            "option_type": selection.option_type,
            "qty": num_contracts,
            "entry_price": entry_price,
            "entry_time": entry_time,
            "order": filled,
        }

    def _wait_for_fill_with_adjustment(
        self,
        order: dict,
        bid_price: float,
        max_adjustments: int = 3,
    ) -> dict:
        """
        Wait for fill. If not filled within 2 min, adjust price toward bid.
        After max adjustments, try market order.
        """
        adjustments = 0
        current_order = order

        while adjustments <= max_adjustments:
            filled = self.orders.wait_for_fill(
                current_order["id"], timeout_seconds=120, poll_interval=5,
            )

            if filled["status"] == "filled":
                return filled

            if adjustments < max_adjustments:
                # Move price $0.05 toward the bid (lower for sells)
                old_price = current_order.get("limit_price", 0)
                if old_price:
                    new_price = max(round(old_price - 0.05, 2), bid_price)
                    log.info(
                        "Adjusting price: $%.2f -> $%.2f (attempt %d/%d)",
                        old_price, new_price, adjustments + 1, max_adjustments,
                    )
                    current_order = self.orders.adjust_limit_price(
                        current_order["id"], new_price,
                    )
                else:
                    break

            adjustments += 1

        # Final attempt: market order
        if current_order["status"] not in ("filled", "canceled"):
            log.info("Switching to market order after %d adjustments", max_adjustments)
            self.orders.cancel_all_orders()
            time.sleep(1)
            current_order = self.orders.sell_to_open(
                symbol=order["symbol"],
                qty=order["qty"],
            )
            return self.orders.wait_for_fill(
                current_order["id"], timeout_seconds=60,
            )

        return current_order

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def _monitor_position(self, trade: dict[str, Any]) -> dict[str, Any]:
        """Monitor the position until exit condition is met."""
        poll_interval = self.cfg.get("execution", {}).get("monitor_interval", 60)

        monitor = PositionMonitor(
            market_data=self.market_data,
            orders=self.orders,
            signals=self.signals,
            circuit_breaker=self.circuit_breaker,
            calendar=self.calendar,
            poll_interval=poll_interval,
        )

        return monitor.monitor_until_exit(
            symbol=trade["symbol"],
            entry_price=trade["entry_price"],
            qty=trade["qty"],
            qqq_open=self._qqq_open,
            account_equity=self._account_equity,
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _record_trade(
        self,
        trade: dict[str, Any],
        exit_result: dict[str, Any],
    ) -> None:
        """Record the completed trade."""
        qqq_close = 0.0
        try:
            qqq_close = self.market_data.get_underlying_price("QQQ")
        except Exception:
            pass

        self.tracker.record_trade(
            trading_date=date.today(),
            symbol=trade["symbol"],
            strike=trade["strike"],
            option_type=trade["option_type"],
            qty=trade["qty"],
            entry_price=trade["entry_price"],
            exit_price=exit_result["exit_price"],
            entry_time=trade["entry_time"],
            exit_time=exit_result["exit_time"],
            exit_reason=exit_result["exit_reason"],
            qqq_open=self._qqq_open,
            qqq_close=qqq_close,
        )

        # Record realized P&L for risk limits
        pnl = (trade["entry_price"] - exit_result["exit_price"]) * 100 * trade["qty"]
        self.limits.record_pnl(date.today(), pnl)

    # ------------------------------------------------------------------
    # End of day
    # ------------------------------------------------------------------

    def _end_of_day(self) -> None:
        """Clean up: verify positions closed, print summary."""
        log.info("=== End of day cleanup ===")

        # Force close any remaining positions
        positions = self.orders.get_option_positions()
        if positions:
            log.warning("Found %d remaining positions -- force closing", len(positions))
            for pos in positions:
                self.orders.close_position(pos["symbol"])

        # Cancel any open orders
        open_orders = self.orders.get_open_orders()
        if open_orders:
            log.warning("Found %d open orders -- cancelling", len(open_orders))
            self.orders.cancel_all_orders()

        # Print daily summary
        self.tracker.print_daily_summary()

        log.info("=== OptionHarvest shutdown ===")
