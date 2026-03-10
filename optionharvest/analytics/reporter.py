"""
Analytics and reporting.

Computes full performance metrics from the trade log:
  - Max drawdown, longest streaks, Sharpe-like ratio
  - Weekly and monthly roll-ups
  - Daily summary with account context
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from optionharvest.analytics.tracker import TradeTracker
from optionharvest.utils.logger import get_logger

log = get_logger("reporter")


class Reporter:
    """Generate performance reports from the trade log."""

    def __init__(self, tracker: TradeTracker) -> None:
        self.tracker = tracker

    # ------------------------------------------------------------------
    # Full metrics (Task 7.1)
    # ------------------------------------------------------------------

    def full_metrics(self) -> dict[str, Any]:
        """
        Compute all performance metrics.

        Returns dict with:
            total_trades, total_pnl, win_rate, avg_win, avg_loss,
            profit_factor, best_trade, worst_trade, max_drawdown,
            longest_win_streak, longest_lose_streak, avg_daily_pnl,
            trading_days
        """
        trades = self.tracker.get_all_trades()
        if not trades:
            return {"total_trades": 0, "total_pnl": 0.0}

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_pnl = sum(pnls)
        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))

        # Daily P&L aggregation
        daily_pnl = self._aggregate_by_date(trades)
        trading_days = len(daily_pnl)

        # Streaks
        win_streak, lose_streak = self._compute_streaks(pnls)

        # Max drawdown
        max_dd = self._compute_max_drawdown(pnls)

        return {
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
            "avg_win": round(gross_wins / len(wins), 2) if wins else 0.0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "profit_factor": round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf"),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
            "max_drawdown": round(max_dd, 2),
            "longest_win_streak": win_streak,
            "longest_lose_streak": lose_streak,
            "avg_daily_pnl": round(total_pnl / trading_days, 2) if trading_days > 0 else 0.0,
            "trading_days": trading_days,
        }

    # ------------------------------------------------------------------
    # Weekly / monthly roll-ups (Task 7.4)
    # ------------------------------------------------------------------

    def weekly_rollup(self) -> list[dict[str, Any]]:
        """
        Aggregate trades into weekly summaries.

        Returns list of dicts sorted by week start date:
            week_start, trades, pnl, wins, losses, win_rate
        """
        trades = self.tracker.get_all_trades()
        if not trades:
            return []

        # Group by ISO week
        weeks: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            d = date.fromisoformat(t["date"])
            # Monday of that week
            monday = d - __import__("datetime").timedelta(days=d.weekday())
            weeks[str(monday)].append(t["pnl"])

        result = []
        for week_start in sorted(weeks.keys()):
            pnls = weeks[week_start]
            wins = sum(1 for p in pnls if p > 0)
            result.append({
                "week_start": week_start,
                "trades": len(pnls),
                "pnl": round(sum(pnls), 2),
                "wins": wins,
                "losses": len(pnls) - wins,
                "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
            })
        return result

    def monthly_rollup(self) -> list[dict[str, Any]]:
        """
        Aggregate trades into monthly summaries.

        Returns list of dicts sorted by month:
            month, trades, pnl, wins, losses, win_rate
        """
        trades = self.tracker.get_all_trades()
        if not trades:
            return []

        months: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            month_key = t["date"][:7]  # "2026-03"
            months[month_key].append(t["pnl"])

        result = []
        for month in sorted(months.keys()):
            pnls = months[month]
            wins = sum(1 for p in pnls if p > 0)
            result.append({
                "month": month,
                "trades": len(pnls),
                "pnl": round(sum(pnls), 2),
                "wins": wins,
                "losses": len(pnls) - wins,
                "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
            })
        return result

    # ------------------------------------------------------------------
    # Print reports (Task 7.3)
    # ------------------------------------------------------------------

    def print_full_report(self) -> None:
        """Print a comprehensive performance report to the log."""
        metrics = self.full_metrics()
        if metrics["total_trades"] == 0:
            log.info("No trades recorded yet")
            return

        log.info("========== PERFORMANCE REPORT ==========")
        log.info("Total trades: %d over %d trading days",
                 metrics["total_trades"], metrics["trading_days"])
        log.info("Total P&L: $%.2f", metrics["total_pnl"])
        log.info("Avg daily P&L: $%.2f", metrics["avg_daily_pnl"])
        log.info("Win rate: %.1f%%", metrics["win_rate"])
        log.info("Avg win: $%.2f | Avg loss: $%.2f", metrics["avg_win"], metrics["avg_loss"])
        log.info("Profit factor: %.2f", metrics["profit_factor"])
        log.info("Best trade: $%.2f | Worst trade: $%.2f",
                 metrics["best_trade"], metrics["worst_trade"])
        log.info("Max drawdown: $%.2f", metrics["max_drawdown"])
        log.info("Longest win streak: %d | Longest lose streak: %d",
                 metrics["longest_win_streak"], metrics["longest_lose_streak"])
        log.info("=========================================")

    def print_weekly_report(self) -> None:
        """Print weekly performance breakdown."""
        weeks = self.weekly_rollup()
        if not weeks:
            log.info("No weekly data")
            return

        log.info("=== WEEKLY BREAKDOWN ===")
        for w in weeks:
            log.info(
                "Week %s: %d trades, P&L=$%.2f, win rate=%.1f%%",
                w["week_start"], w["trades"], w["pnl"], w["win_rate"],
            )
        log.info("========================")

    def print_monthly_report(self) -> None:
        """Print monthly performance breakdown."""
        months = self.monthly_rollup()
        if not months:
            log.info("No monthly data")
            return

        log.info("=== MONTHLY BREAKDOWN ===")
        for m in months:
            log.info(
                "%s: %d trades, P&L=$%.2f, win rate=%.1f%%",
                m["month"], m["trades"], m["pnl"], m["win_rate"],
            )
        log.info("=========================")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_by_date(trades: list[dict]) -> dict[str, float]:
        """Sum P&L by date."""
        daily: dict[str, float] = defaultdict(float)
        for t in trades:
            daily[t["date"]] += t["pnl"]
        return dict(daily)

    @staticmethod
    def _compute_streaks(pnls: list[float]) -> tuple[int, int]:
        """Return (longest_win_streak, longest_lose_streak)."""
        max_win = 0
        max_lose = 0
        cur_win = 0
        cur_lose = 0

        for p in pnls:
            if p > 0:
                cur_win += 1
                cur_lose = 0
                max_win = max(max_win, cur_win)
            elif p < 0:
                cur_lose += 1
                cur_win = 0
                max_lose = max(max_lose, cur_lose)
            else:
                cur_win = 0
                cur_lose = 0

        return max_win, max_lose

    @staticmethod
    def _compute_max_drawdown(pnls: list[float]) -> float:
        """
        Max drawdown from cumulative P&L curve.

        Returns a positive number representing the largest
        peak-to-trough decline in cumulative P&L.
        """
        if not pnls:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return max_dd
