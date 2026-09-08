from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import run_research
from .config import BotConfig
from .database import Database
from .engine import PaperEngine
from .http_client import GeckoTerminalClient, JsonHttpClient, PumpClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bwam-paperbot",
        description="Paper-only watcher for migrated Pump.fun coins from one creator.",
    )
    parser.add_argument("--config", default="config.json", help="JSON configuration path")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the paper monitor")
    run.add_argument("--once", action="store_true", help="perform one poll and exit")
    sub.add_parser("status", help="show the SQLite paper account summary")
    research = sub.add_parser("research", help="collect wallet launches and OHLCV backtest")
    research.add_argument("--days", type=int, default=14)
    research.add_argument("--output", default="research")
    return parser


def _clients(config: BotConfig) -> tuple[PumpClient, GeckoTerminalClient]:
    http = JsonHttpClient(config.request_timeout_seconds, config.max_http_retries)
    return PumpClient(http, config.pump_api_base), GeckoTerminalClient(http)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = BotConfig.load(args.config)
    if args.command == "status":
        database = Database(config.database_path)
        try:
            print(json.dumps(database.summary(), indent=2))
        finally:
            database.close()
        return 0

    pump, gecko = _clients(config)
    if args.command == "research":
        if args.days < 1 or args.days > 365:
            raise SystemExit("--days must be between 1 and 365")
        summary = run_research(pump, gecko, config, args.days, Path(args.output))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    database = Database(config.database_path)
    try:
        engine = PaperEngine(config, database, pump)
        if args.once:
            engine.poll_once()
        else:
            engine.run_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        database.close()
    return 0

