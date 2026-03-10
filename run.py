"""
OptionHarvest entry point.

Usage:
    python run.py                    # run the trading bot
    python run.py --dry-run          # validate config and connection only
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
    args = parser.parse_args()

    try:
        if args.dry_run:
            log.info("=== DRY RUN MODE ===")
            cfg = load_config(args.config)
            log.info("Config loaded: %s", args.config)

            bot = TradingBot.from_config(args.config)
            log.info("All components initialized")

            if bot.client.verify_connection():
                log.info("Connection verified -- dry run PASSED")
            else:
                log.error("Connection failed -- dry run FAILED")
                sys.exit(1)
        else:
            bot = TradingBot.from_config(args.config)
            bot.run()

    except KeyboardInterrupt:
        log.info("Interrupted by user -- shutting down")
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
