"""
Daily and weekly loss limits.

Tracks realized P&L and blocks trading when limits are hit.
"""

from __future__ import annotations

from datetime import date, timedelta

from optionharvest.utils.logger import get_logger

log = get_logger("limits")


class RiskLimits:
    """Track realized losses and enforce limits."""

    def __init__(
        self,
        max_daily_loss: float = 500.0,
        max_weekly_loss: float = 1500.0,
        max_position_pct: float = 0.05,
    ) -> None:
        self.max_daily_loss = max_daily_loss
        self.max_weekly_loss = max_weekly_loss
        self.max_position_pct = max_position_pct

        # Track realized P&L by date
        self._daily_pnl: dict[date, float] = {}

    @classmethod
    def from_config(cls, cfg: dict) -> "RiskLimits":
        risk = cfg.get("risk", {})
        return cls(
            max_daily_loss=risk.get("max_daily_loss", 500.0),
            max_weekly_loss=risk.get("max_weekly_loss", 1500.0),
            max_position_pct=risk.get("max_position_pct", 0.05),
        )

    def record_pnl(self, trading_date: date, pnl: float) -> None:
        """Record realized P&L for a day."""
        self._daily_pnl[trading_date] = self._daily_pnl.get(trading_date, 0.0) + pnl
        log.info("Recorded P&L for %s: $%.2f (day total: $%.2f)",
                 trading_date, pnl, self._daily_pnl[trading_date])

    def daily_loss_limit_hit(self, trading_date: date | None = None) -> bool:
        """Has today's realized loss exceeded the daily limit?"""
        d = trading_date or date.today()
        today_pnl = self._daily_pnl.get(d, 0.0)
        hit = today_pnl <= -self.max_daily_loss
        if hit:
            log.warning(
                "DAILY LOSS LIMIT HIT: $%.2f (limit: -$%.2f)",
                today_pnl, self.max_daily_loss,
            )
        return hit

    def weekly_loss_limit_hit(self, trading_date: date | None = None) -> bool:
        """Has this week's realized loss exceeded the weekly limit?"""
        d = trading_date or date.today()
        # Monday of this week
        monday = d - timedelta(days=d.weekday())
        week_pnl = sum(
            pnl for dt, pnl in self._daily_pnl.items()
            if monday <= dt <= d
        )
        hit = week_pnl <= -self.max_weekly_loss
        if hit:
            log.warning(
                "WEEKLY LOSS LIMIT HIT: $%.2f (limit: -$%.2f)",
                week_pnl, self.max_weekly_loss,
            )
        return hit

    def check_buying_power(
        self,
        required: float,
        available: float,
    ) -> tuple[bool, str]:
        """Check if we have enough buying power for a trade."""
        if required > available:
            msg = f"Insufficient buying power: need ${required:.2f}, have ${available:.2f}"
            log.warning(msg)
            return False, msg
        return True, ""

    def check_position_size(
        self,
        trade_risk: float,
        account_equity: float,
    ) -> tuple[bool, str]:
        """Check if position size is within limits."""
        max_risk = account_equity * self.max_position_pct
        if trade_risk > max_risk:
            msg = (f"Position too large: risk ${trade_risk:.2f} > "
                   f"max ${max_risk:.2f} ({self.max_position_pct:.0%} of equity)")
            log.warning(msg)
            return False, msg
        return True, ""

    def get_today_pnl(self, trading_date: date | None = None) -> float:
        d = trading_date or date.today()
        return self._daily_pnl.get(d, 0.0)
