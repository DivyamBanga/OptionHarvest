"""
Order management for options trading on Alpaca.

Handles: placing sell-to-open orders, monitoring fills,
closing positions, and querying order/position status.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    GetOrdersRequest,
    ClosePositionRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    QueryOrderStatus,
    OrderStatus,
)

from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.api.client import AlpacaClient

log = get_logger("orders")


class OrderManager:
    """Place and manage option orders on Alpaca."""

    def __init__(self, client: "AlpacaClient") -> None:
        self.client = client

    # ------------------------------------------------------------------
    # Place orders
    # ------------------------------------------------------------------

    def sell_to_open(
        self,
        symbol: str,
        qty: int = 1,
        limit_price: float | None = None,
    ) -> dict:
        """
        Sell-to-open an option contract (short position).

        Parameters
        ----------
        symbol : OCC option symbol (e.g. QQQ260309P00500000)
        qty : number of contracts
        limit_price : if provided, place limit order; otherwise market order

        Returns
        -------
        Dict with order details: id, status, symbol, qty, side, type, limit_price
        """
        if limit_price:
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit_price, 2),
            )
            log.info(
                "Placing SELL limit order: %s x%d @ $%.2f",
                symbol, qty, limit_price,
            )
        else:
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            log.info("Placing SELL market order: %s x%d", symbol, qty)

        order = self.client.trading.submit_order(order_data=order_data)
        return self._order_to_dict(order)

    def buy_to_close(
        self,
        symbol: str,
        qty: int = 1,
        limit_price: float | None = None,
    ) -> dict:
        """
        Buy-to-close an option contract (close short position).
        """
        if limit_price:
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit_price, 2),
            )
            log.info(
                "Placing BUY-TO-CLOSE limit: %s x%d @ $%.2f",
                symbol, qty, limit_price,
            )
        else:
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            log.info("Placing BUY-TO-CLOSE market: %s x%d", symbol, qty)

        order = self.client.trading.submit_order(order_data=order_data)
        return self._order_to_dict(order)

    # ------------------------------------------------------------------
    # Monitor fills
    # ------------------------------------------------------------------

    def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: int = 120,
        poll_interval: int = 5,
    ) -> dict:
        """
        Poll until an order is filled, cancelled, or timeout is reached.

        Returns the final order state as a dict.
        """
        log.info("Waiting for fill on order %s (timeout=%ds)", order_id, timeout_seconds)
        elapsed = 0

        while elapsed < timeout_seconds:
            order = self.client.trading.get_order_by_id(order_id)
            status = order.status

            if status == OrderStatus.FILLED:
                fill_price = float(order.filled_avg_price) if order.filled_avg_price else 0.0
                log.info(
                    "Order %s FILLED @ $%.2f (qty=%s)",
                    order_id, fill_price, order.filled_qty,
                )
                return self._order_to_dict(order)

            if status in (
                OrderStatus.CANCELED,
                OrderStatus.EXPIRED,
                OrderStatus.REJECTED,
            ):
                log.warning("Order %s ended with status: %s", order_id, status.value)
                return self._order_to_dict(order)

            time.sleep(poll_interval)
            elapsed += poll_interval

        log.warning("Order %s timed out after %ds", order_id, timeout_seconds)
        return self._order_to_dict(self.client.trading.get_order_by_id(order_id))

    def adjust_limit_price(
        self,
        order_id: str,
        new_price: float,
    ) -> dict:
        """Cancel existing order and resubmit with a new limit price."""
        old_order = self.client.trading.get_order_by_id(order_id)
        self.client.trading.cancel_order_by_id(order_id)
        log.info("Cancelled order %s, resubmitting at $%.2f", order_id, new_price)

        # Wait briefly for cancellation to process
        time.sleep(1)

        order_data = LimitOrderRequest(
            symbol=old_order.symbol,
            qty=int(old_order.qty),
            side=old_order.side,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            limit_price=round(new_price, 2),
        )
        new_order = self.client.trading.submit_order(order_data=order_data)
        return self._order_to_dict(new_order)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_option_positions(self) -> list[dict]:
        """Get all open option positions."""
        positions = self.client.trading.get_all_positions()
        option_positions = []

        for pos in positions:
            # Option symbols are longer than stock symbols (OCC format)
            if len(pos.symbol) > 10:
                option_positions.append({
                    "symbol": pos.symbol,
                    "qty": int(pos.qty),
                    "side": pos.side.value if pos.side else "unknown",
                    "avg_entry_price": float(pos.avg_entry_price),
                    "current_price": float(pos.current_price) if pos.current_price else 0.0,
                    "market_value": float(pos.market_value) if pos.market_value else 0.0,
                    "unrealized_pl": float(pos.unrealized_pl) if pos.unrealized_pl else 0.0,
                    "unrealized_plpc": float(pos.unrealized_plpc) if pos.unrealized_plpc else 0.0,
                })

        log.info("Open option positions: %d", len(option_positions))
        return option_positions

    def close_position(self, symbol: str, qty: int | None = None) -> dict | None:
        """Close an option position (fully or partially)."""
        try:
            close_opts = ClosePositionRequest(qty=str(qty)) if qty else None
            result = self.client.trading.close_position(
                symbol_or_asset_id=symbol,
                close_options=close_opts,
            )
            log.info("Closed position: %s", symbol)
            return self._order_to_dict(result)
        except Exception as exc:
            log.error("Failed to close position %s: %s", symbol, exc)
            return None

    def close_all_positions(self) -> bool:
        """Emergency: close all open positions."""
        try:
            self.client.trading.close_all_positions(cancel_orders=True)
            log.info("EMERGENCY: closed all positions and cancelled all orders")
            return True
        except Exception as exc:
            log.error("Failed to close all positions: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Order queries
    # ------------------------------------------------------------------

    def get_open_orders(self) -> list[dict]:
        """Get all currently open orders."""
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = self.client.trading.get_orders(filter=req)
        return [self._order_to_dict(o) for o in orders]

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.client.trading.cancel_orders()
            log.info("Cancelled all open orders")
            return True
        except Exception as exc:
            log.error("Failed to cancel orders: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _order_to_dict(order) -> dict:
        """Convert an Alpaca Order object to a plain dict."""
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": int(order.qty) if order.qty else 0,
            "filled_qty": int(order.filled_qty) if order.filled_qty else 0,
            "side": order.side.value if order.side else "unknown",
            "type": order.type.value if order.type else "unknown",
            "status": order.status.value if order.status else "unknown",
            "limit_price": float(order.limit_price) if order.limit_price else None,
            "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            "submitted_at": str(order.submitted_at) if order.submitted_at else None,
            "filled_at": str(order.filled_at) if order.filled_at else None,
        }
