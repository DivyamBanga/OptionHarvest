"""
Intraday circuit breakers and kill switch.

Triggers emergency position close when:
- Unrealized loss exceeds a threshold
- QQQ moves too far from open
- Kill switch file exists
"""

from __future__ import annotations

from pathlib import Path

from optionharvest.utils.logger import get_logger

log = get_logger("circuit_breaker")

KILL_SWITCH_FILE = Path("KILL_SWITCH")


class CircuitBreaker:
    """Emergency exit logic."""

    def __init__(
        self,
        loss_pct_threshold: float = 0.03,
        qqq_move_threshold: float = 0.03,
    ) -> None:
        self.loss_pct_threshold = loss_pct_threshold
        self.qqq_move_threshold = qqq_move_threshold

    @classmethod
    def from_config(cls, cfg: dict) -> "CircuitBreaker":
        risk = cfg.get("risk", {})
        return cls(
            loss_pct_threshold=risk.get("circuit_breaker_loss_pct", 0.03),
            qqq_move_threshold=risk.get("circuit_breaker_qqq_move", 0.03),
        )

    def check(
        self,
        unrealized_pnl: float,
        account_equity: float,
        qqq_open: float,
        qqq_current: float,
    ) -> tuple[bool, str]:
        """
        Check all circuit breaker conditions.

        Returns (should_close_all, reason).
        """
        # Kill switch file
        if KILL_SWITCH_FILE.exists():
            log.critical("KILL SWITCH ACTIVATED -- closing all positions")
            return True, "kill_switch"

        # Unrealized loss check
        if account_equity > 0 and unrealized_pnl < 0:
            loss_pct = abs(unrealized_pnl) / account_equity
            if loss_pct >= self.loss_pct_threshold:
                log.critical(
                    "CIRCUIT BREAKER: unrealized loss $%.2f = %.1f%% of equity "
                    "(threshold: %.1f%%)",
                    unrealized_pnl, loss_pct * 100, self.loss_pct_threshold * 100,
                )
                return True, "unrealized_loss"

        # QQQ big move check
        if qqq_open > 0:
            move_pct = abs(qqq_current - qqq_open) / qqq_open
            if move_pct >= self.qqq_move_threshold:
                direction = "UP" if qqq_current > qqq_open else "DOWN"
                log.critical(
                    "CIRCUIT BREAKER: QQQ moved %.1f%% %s from open "
                    "(threshold: %.1f%%)",
                    move_pct * 100, direction, self.qqq_move_threshold * 100,
                )
                return True, "qqq_big_move"

        return False, ""
