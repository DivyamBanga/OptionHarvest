"""
Trade logging and P&L tracking.

Appends every trade to a CSV file and provides daily/cumulative stats.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from optionharvest.utils.logger import get_logger

log = get_logger("tracker")

TRADE_LOG_DIR = Path("data/trades")

TRADE_COLUMNS = [
    "date",
    "symbol",
    "strike",
    "option_type",
    "side",
    "qty",
    "entry_price",
    "exit_price",
    "entry_time",
    "exit_time",
    "exit_reason",
    "pnl",
    "qqq_open",
    "qqq_close",
    "qqq_move_pct",
]


class TradeTracker:
    """Log trades to CSV and compute basic stats."""

    def __init__(self, log_dir: str | Path = TRADE_LOG_DIR) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._today_trades: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, cfg: dict) -> "TradeTracker":
        analytics = cfg.get("analytics", {})
        return cls(log_dir=analytics.get("trade_log_dir", "data/trades"))

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_trade(
        self,
        trading_date: date,
        symbol: str,
        strike: float,
        option_type: str,
        qty: int,
        entry_price: float,
        exit_price: float,
        entry_time: str,
        exit_time: str,
        exit_reason: str,
        qqq_open: float = 0.0,
        qqq_close: float = 0.0,
    ) -> dict[str, Any]:
        """Record a completed trade to CSV and memory."""
        # P&L for a SHORT option: (entry - exit) * 100 * qty
        pnl = round((entry_price - exit_price) * 100 * qty, 2)

        qqq_move_pct = 0.0
        if qqq_open > 0:
            qqq_move_pct = round((qqq_close - qqq_open) / qqq_open * 100, 2)

        trade = {
            "date": str(trading_date),
            "symbol": symbol,
            "strike": strike,
            "option_type": option_type,
            "side": "sell",
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "exit_reason": exit_reason,
            "pnl": pnl,
            "qqq_open": qqq_open,
            "qqq_close": qqq_close,
            "qqq_move_pct": qqq_move_pct,
        }

        self._today_trades.append(trade)
        self._append_csv(trade)

        log.info(
            "Trade recorded: %s strike=$%.0f %s P&L=$%.2f (%s)",
            symbol, strike, option_type, pnl, exit_reason,
        )
        return trade

    def _append_csv(self, trade: dict[str, Any]) -> None:
        """Append a single trade row to the CSV file."""
        csv_path = self.log_dir / "trade_log.csv"
        file_exists = csv_path.exists()

        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_today_pnl(self) -> float:
        """Total P&L from trades recorded today."""
        return sum(t["pnl"] for t in self._today_trades)

    def get_today_trades(self) -> list[dict[str, Any]]:
        """All trades recorded in this session."""
        return list(self._today_trades)

    def get_all_trades(self) -> list[dict[str, Any]]:
        """Read all trades from the CSV file."""
        csv_path = self.log_dir / "trade_log.csv"
        if not csv_path.exists():
            return []

        trades = []
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["pnl"] = float(row["pnl"])
                row["strike"] = float(row["strike"])
                row["qty"] = int(row["qty"])
                row["entry_price"] = float(row["entry_price"])
                row["exit_price"] = float(row["exit_price"])
                row["qqq_open"] = float(row["qqq_open"])
                row["qqq_close"] = float(row["qqq_close"])
                row["qqq_move_pct"] = float(row["qqq_move_pct"])
                trades.append(row)
        return trades

    def get_cumulative_stats(self) -> dict[str, Any]:
        """Compute summary stats from all recorded trades."""
        trades = self.get_all_trades()
        if not trades:
            return {"total_trades": 0, "total_pnl": 0.0}

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) * 100 if pnls else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        return {
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
        }

    def print_daily_summary(self) -> None:
        """Print today's trading summary to the log."""
        trades = self._today_trades
        if not trades:
            log.info("No trades today")
            return

        total_pnl = sum(t["pnl"] for t in trades)
        wins = sum(1 for t in trades if t["pnl"] > 0)

        log.info("=== DAILY SUMMARY ===")
        log.info("Trades: %d | Wins: %d | Losses: %d", len(trades), wins, len(trades) - wins)
        log.info("Today P&L: $%.2f", total_pnl)
        for t in trades:
            log.info(
                "  %s $%.0f %s: entry=$%.2f exit=$%.2f P&L=$%.2f (%s)",
                t["option_type"], t["strike"], t["symbol"],
                t["entry_price"], t["exit_price"], t["pnl"], t["exit_reason"],
            )

        # Also show cumulative stats
        stats = self.get_cumulative_stats()
        log.info("Cumulative: %d trades, P&L=$%.2f, win rate=%.1f%%",
                 stats["total_trades"], stats["total_pnl"], stats["win_rate"])
        log.info("=====================")

    def reset_daily(self) -> None:
        """Clear today's in-memory trades (call at start of new day)."""
        self._today_trades = []
