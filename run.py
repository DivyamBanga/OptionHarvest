"""
OptionHarvest entry point.

Usage:
    python run.py                    # run the trading bot for today
    python run.py --schedule         # run continuously (every trading day)
    python run.py --dry-run          # validate config and connection only
    python run.py --report           # print full performance report
    python run.py --config path.yaml # use a custom config file
"""

from __future__ import annotations

import argparse
import sys

from optionharvest.trading.executor import TradingBot, load_config
from optionharvest.utils.logger import get_logger

log = get_logger("main")


def main() -> None:
    parser = argparse.ArgumentParser(description="OptionHarvest 0DTE trading bot")
    parser.add_argument(
        "--config", default="config/settings.yaml",
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate config and connection without trading",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run continuously -- auto-trade every trading day",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print full performance report and exit",
    )
    args = parser.parse_args()

    try:
        if args.dry_run:
            _dry_run(args.config)
        elif args.report:
            _show_report(args.config)
        elif args.schedule:
            _run_scheduled(args.config)
        else:
            bot = TradingBot.from_config(args.config)
            bot.run()

    except KeyboardInterrupt:
        log.info("Interrupted by user -- shutting down")
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


def _dry_run(config_path: str) -> None:
    log.info("=== DRY RUN MODE ===")
    cfg = load_config(config_path)
    log.info("Config loaded: %s", config_path)

    bot = TradingBot.from_config(config_path)
    log.info("All components initialized")

    if bot.client.verify_connection():
        log.info("Connection verified -- dry run PASSED")
    else:
        log.error("Connection failed -- dry run FAILED")
        sys.exit(1)


def _show_report(config_path: str) -> None:
    from optionharvest.analytics.reporter import Reporter
    from optionharvest.analytics.tracker import TradeTracker

    cfg = load_config(config_path)
    tracker = TradeTracker.from_config(cfg)
    reporter = Reporter(tracker)

    reporter.print_full_report()
    reporter.print_weekly_report()
    reporter.print_monthly_report()


def _run_scheduled(config_path: str) -> None:
    from optionharvest.trading.scheduler import TradingScheduler

    bot = TradingBot.from_config(config_path)
    scheduler = TradingScheduler.from_bot(bot)
    scheduler.run_forever()


if __name__ == "__main__":
    main()
