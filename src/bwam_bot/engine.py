from __future__ import annotations

import time
from collections.abc import Callable

from .config import BotConfig
from .database import Database
from .http_client import PumpClient
from .models import Coin
from .strategy import (
    can_enter,
    exit_decision,
    paper_entry_exposure,
    paper_exit_value,
    utc_day_start,
)


class PaperEngine:
    def __init__(
        self,
        config: BotConfig,
        database: Database,
        pump: PumpClient,
        emit: Callable[[str], None] = print,
    ) -> None:
        config.validate()
        self.config = config
        self.database = database
        self.pump = pump
        self.emit = emit

    def discover(self) -> list[Coin]:
        found: dict[str, Coin] = {}
        for page in range(self.config.discovery_pages):
            coins = self.pump.creator_coins(
                self.config.wallet,
                offset=page * self.config.page_size,
                limit=self.config.page_size,
            )
            for coin in coins:
                found[coin.mint] = coin
            if len(coins) < self.config.page_size:
                break
        return sorted(found.values(), key=lambda coin: coin.created_at_ms, reverse=True)

    def poll_once(self, now: int | None = None) -> dict[str, int]:
        current_time = now or int(time.time())
        coins = self.discover()
        for coin in coins:
            self.database.upsert_coin(coin, current_time)

        self._mark_and_exit(current_time)
        entered = self._enter_eligible(coins, current_time)
        complete = sum(1 for coin in coins if coin.complete and coin.pool_address)
        self.emit(
            f"poll coins={len(coins)} migrated={complete} entered={entered} "
            f"open={len(self.database.open_positions())}"
        )
        return {"coins": len(coins), "migrated": complete, "entered": entered}

    def _mark_and_exit(self, now: int) -> None:
        for position in self.database.open_positions():
            try:
                coin = self.pump.coin(position.mint)
            except RuntimeError as error:
                self.database.event("data_error", position.mint, str(error), now)
                continue
            self.database.upsert_coin(coin, now)
            if coin.market_cap_usd > position.peak_market_cap_usd:
                position.peak_market_cap_usd = coin.market_cap_usd
                self.database.update_peak(position.id, position.peak_market_cap_usd)
            decision = exit_decision(self.config, position, coin.market_cap_usd, now)
            if decision.should_exit and decision.reason:
                value = paper_exit_value(self.config, position, coin.market_cap_usd)
                pnl = self.database.close_position(
                    position, coin.market_cap_usd, value, decision.reason, now
                )
                self.emit(f"EXIT {coin.symbol} reason={decision.reason} pnl=${pnl:.2f}")

    def _enter_eligible(self, coins: list[Coin], now: int) -> int:
        entered = 0
        for coin in sorted(coins, key=lambda candidate: candidate.created_at_ms):
            if self.database.has_position(coin.mint):
                continue
            open_count = len(self.database.open_positions())
            realized_today = self.database.realized_pnl_since(utc_day_start(now))
            allowed, reason = can_enter(
                self.config,
                coin,
                self.database.first_completed_at(coin.mint),
                open_count,
                realized_today,
                now,
            )
            if not allowed:
                continue
            exposure_usd, entry_cost = paper_entry_exposure(self.config)
            if exposure_usd <= 0 or coin.market_cap_usd <= 0:
                self.database.event("rejected", coin.mint, "non_positive_exposure", now)
                continue
            units = exposure_usd / coin.market_cap_usd
            self.database.open_position(
                coin, self.config.position_size_usd, units, entry_cost, now
            )
            self.emit(
                f"ENTRY {coin.symbol} mint={coin.mint} mcap=${coin.market_cap_usd:.0f} "
                f"notional=${self.config.position_size_usd:.2f}"
            )
            entered += 1
        return entered

    def run_forever(self) -> None:
        self.emit("paper engine started; no transaction signing code is present")
        while True:
            started = time.monotonic()
            try:
                self.poll_once()
            except KeyboardInterrupt:
                raise
            except Exception as error:  # daemon boundary: log and keep paper monitor alive
                self.database.event("poll_error", None, repr(error))
                self.emit(f"poll error: {error}")
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, self.config.poll_seconds - elapsed))

