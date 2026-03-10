"""
Entry and exit signal logic for 0DTE option selling.

Entry: should we open a position right now?
Exit: should we close an existing position?
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from optionharvest.utils.logger import get_logger

if TYPE_CHECKING:
    from optionharvest.utils.calendar import TradingCalendar

log = get_logger("signals")


@dataclass
class ExitSignal:
    """Result of an exit check."""
    should_exit: bool
    reason: str  # "stop_loss", "profit_target", "time_exit", "circuit_breaker", ""


class SignalEngine:
    """Decides when to enter and exit trades."""

    def __init__(
        self,
        entry_time: str = "09:31",
        exit_time: str = "15:15",
        stop_loss_multiplier: float = 2.0,
        profit_target_pct: float = 0.50,
        use_stop_loss: bool = True,
        use_profit_target: bool = True,
    ) -> None:
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.stop_loss_multiplier = stop_loss_multiplier
        self.profit_target_pct = profit_target_pct
        self.use_stop_loss = use_stop_loss
        self.use_profit_target = use_profit_target

    @classmethod
    def from_config(cls, cfg: dict) -> "SignalEngine":
        execution = cfg.get("execution", {})
        exit_cfg = cfg.get("exit", {})
        return cls(
            entry_time=execution.get("entry_time", "09:31"),
            exit_time=execution.get("exit_time", "15:15"),
            stop_loss_multiplier=exit_cfg.get("stop_loss_multiplier", 2.0),
            profit_target_pct=exit_cfg.get("profit_target_pct", 0.50),
            use_stop_loss=exit_cfg.get("use_stop_loss", True),
            use_profit_target=exit_cfg.get("use_profit_target", True),
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def check_entry(
        self,
        calendar: "TradingCalendar",
        has_open_position: bool,
        daily_loss_limit_hit: bool,
    ) -> tuple[bool, str]:
        """
        Check if we should enter a trade right now.

        Returns (should_enter, reason_if_not).
        """
        if has_open_position:
            return False, "already have an open position"

        if daily_loss_limit_hit:
            return False, "daily loss limit hit"

        if not calendar.is_market_open():
            return False, "market is closed"

        if not calendar.is_after_entry_time(self.entry_time):
            return False, f"before entry time ({self.entry_time} ET)"

        if not calendar.is_before_exit_time(self.exit_time):
            return False, f"past exit time ({self.exit_time} ET)"

        return True, ""

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def check_exit(
        self,
        entry_premium: float,
        current_option_price: float,
        calendar: "TradingCalendar",
    ) -> ExitSignal:
        """
        Check if we should exit an existing short position.

        For a SHORT option position:
        - We sold at entry_premium, current price is current_option_price
        - If current price RISES above entry * stop_loss_multiplier -> stop loss
        - If current price DROPS below entry * profit_target_pct -> profit target
        - If past exit time -> time exit
        """
        # Time-based exit (highest priority)
        if not calendar.is_before_exit_time(self.exit_time):
            log.info("TIME EXIT: past %s ET", self.exit_time)
            return ExitSignal(should_exit=True, reason="time_exit")

        # Stop-loss: option price rose (bad for seller)
        if self.use_stop_loss:
            stop_price = entry_premium * self.stop_loss_multiplier
            if current_option_price >= stop_price:
                log.info(
                    "STOP LOSS: current=$%.2f >= stop=$%.2f (entry=$%.2f x %.1f)",
                    current_option_price, stop_price,
                    entry_premium, self.stop_loss_multiplier,
                )
                return ExitSignal(should_exit=True, reason="stop_loss")

        # Profit target: option price dropped (good for seller)
        if self.use_profit_target:
            target_price = entry_premium * self.profit_target_pct
            if current_option_price <= target_price:
                log.info(
                    "PROFIT TARGET: current=$%.2f <= target=$%.2f (entry=$%.2f x %.0f%%)",
                    current_option_price, target_price,
                    entry_premium, self.profit_target_pct * 100,
                )
                return ExitSignal(should_exit=True, reason="profit_target")

        return ExitSignal(should_exit=False, reason="")
