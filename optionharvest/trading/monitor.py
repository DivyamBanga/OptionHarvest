"""
Position monitoring loop.

After a trade is filled, this polls the option price at a regular interval
and checks exit signals (stop-loss, profit target, time exit, circuit breaker).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.api.market_data import MarketData
    from optionharvest.api.orders import OrderManager
    from optionharvest.risk.circuit_breaker import CircuitBreaker
    from optionharvest.strategy.signals import SignalEngine
    from optionharvest.utils.calendar import TradingCalendar

log = get_logger("monitor")


class PositionMonitor:
    """Monitors an open short option position and triggers exits."""

    def __init__(
        self,
        market_data: "MarketData",
        orders: "OrderManager",
        signals: "SignalEngine",
        circuit_breaker: "CircuitBreaker",
        calendar: "TradingCalendar",
        poll_interval: int = 60,
    ) -> None:
        self.market_data = market_data
        self.orders = orders
        self.signals = signals
        self.circuit_breaker = circuit_breaker
        self.calendar = calendar
        self.poll_interval = poll_interval

    def monitor_until_exit(
        self,
        symbol: str,
        entry_price: float,
        qty: int,
        qqq_open: float,
        account_equity: float,
    ) -> dict:
        """
        Poll the position until an exit condition is met.

        Returns a dict with exit details:
            exit_reason, exit_price, exit_time, unrealized_pnl
        """
        log.info(
            "Monitoring position: %s x%d entry=$%.2f (poll every %ds)",
            symbol, qty, entry_price, self.poll_interval,
        )

        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            try:
                result = self._check_once(
                    symbol, entry_price, qty, qqq_open, account_equity,
                )
                consecutive_errors = 0  # reset on success
                if result is not None:
                    return result
            except Exception as exc:
                consecutive_errors += 1
                log.error(
                    "Monitor poll error (%d/%d): %s",
                    consecutive_errors, max_consecutive_errors, exc,
                )
                if consecutive_errors >= max_consecutive_errors:
                    log.critical(
                        "Too many consecutive errors -- force closing position"
                    )
                    return self._execute_exit(
                        symbol, qty, entry_price, "api_error",
                    )

            time.sleep(self.poll_interval)

    def _check_once(
        self,
        symbol: str,
        entry_price: float,
        qty: int,
        qqq_open: float,
        account_equity: float,
    ) -> dict | None:
        """
        Run one monitoring cycle. Returns exit dict if should exit, None otherwise.
        """
        # Get current option price
        quotes = self.market_data.get_option_quotes([symbol])
        if symbol not in quotes:
            log.warning("No quote for %s -- skipping cycle", symbol)
            return None

        current_price = quotes[symbol]["mid"]
        if current_price <= 0:
            current_price = quotes[symbol]["ask"]

        # Unrealized P&L for short position: (entry - current) * 100 * qty
        unrealized_pnl = (entry_price - current_price) * 100 * qty

        log.info(
            "%s: current=$%.2f entry=$%.2f unrealized=$%.2f",
            symbol, current_price, entry_price, unrealized_pnl,
        )

        # Check circuit breaker
        qqq_current = self.market_data.get_underlying_price("QQQ")
        should_close, cb_reason = self.circuit_breaker.check(
            unrealized_pnl=unrealized_pnl,
            account_equity=account_equity,
            qqq_open=qqq_open,
            qqq_current=qqq_current,
        )
        if should_close:
            return self._execute_exit(
                symbol, qty, current_price, f"circuit_breaker:{cb_reason}",
            )

        # Check exit signals (stop-loss, profit target, time exit)
        exit_signal = self.signals.check_exit(
            entry_premium=entry_price,
            current_option_price=current_price,
            calendar=self.calendar,
        )
        if exit_signal.should_exit:
            return self._execute_exit(
                symbol, qty, current_price, exit_signal.reason,
            )

        return None

    def _execute_exit(
        self,
        symbol: str,
        qty: int,
        current_price: float,
        reason: str,
    ) -> dict:
        """Place a buy-to-close order and return exit details."""
        log.info("EXIT triggered: %s reason=%s", symbol, reason)

        # Use market order for stop-loss and circuit breaker (urgency)
        # Use limit order for profit target (price is favorable)
        if reason in ("profit_target",):
            order = self.orders.buy_to_close(
                symbol=symbol, qty=qty, limit_price=current_price,
            )
        else:
            order = self.orders.buy_to_close(symbol=symbol, qty=qty)

        # Wait for fill
        filled = self.orders.wait_for_fill(order["id"], timeout_seconds=60)
        exit_price = filled.get("filled_avg_price") or current_price

        from optionharvest.utils.calendar import now_et
        exit_time = now_et().strftime("%H:%M:%S")

        return {
            "exit_reason": reason,
            "exit_price": exit_price,
            "exit_time": exit_time,
            "order": filled,
        }
