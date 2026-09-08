from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_WALLET = "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa"


@dataclass(slots=True)
class BotConfig:
    mode: str = "paper"
    wallet: str = DEFAULT_WALLET
    database_path: str = "data/paper.db"
    poll_seconds: int = 20
    page_size: int = 70
    discovery_pages: int = 3
    min_market_cap_usd: float = 30_000.0
    max_market_cap_usd: float = 250_000.0
    entry_window_minutes: int = 5
    position_size_usd: float = 50.0
    max_open_positions: int = 3
    daily_loss_limit_usd: float = 50.0
    take_profit_pct: float = 50.0
    stop_loss_pct: float = 30.0
    max_hold_minutes: int = 60
    trailing_activation_pct: float = 30.0
    trailing_stop_pct: float = 20.0
    fee_and_slippage_bps_per_leg: float = 250.0
    fixed_cost_usd_per_leg: float = 0.15
    request_timeout_seconds: int = 20
    max_http_retries: int = 4
    pump_api_base: str = "https://frontend-api-v3.pump.fun"

    @classmethod
    def load(cls, path: str | Path) -> "BotConfig":
        raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        unknown = set(raw) - set(asdict(cls()))
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        config = cls(**raw)
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode != "paper":
            raise ValueError("This repository is paper-only: mode must be 'paper'.")
        if len(self.wallet) < 32 or len(self.wallet) > 44:
            raise ValueError("wallet does not look like a Solana public key")
        if self.poll_seconds < 5:
            raise ValueError("poll_seconds must be >= 5 to avoid abusing the data API")
        if not 1 <= self.page_size <= 70:
            raise ValueError("page_size must be between 1 and 70")
        if not 1 <= self.discovery_pages <= 20:
            raise ValueError("discovery_pages must be between 1 and 20")
        if self.min_market_cap_usd < 0:
            raise ValueError("min_market_cap_usd must be non-negative")
        if self.max_market_cap_usd <= self.min_market_cap_usd:
            raise ValueError("max_market_cap_usd must exceed min_market_cap_usd")
        if self.position_size_usd <= 0 or self.max_open_positions < 1:
            raise ValueError("position sizing must be positive")
        for name in ("take_profit_pct", "stop_loss_pct", "trailing_stop_pct"):
            if not 0 < getattr(self, name) < 1000:
                raise ValueError(f"{name} is outside a sensible range")
        if self.fee_and_slippage_bps_per_leg < 0 or self.fixed_cost_usd_per_leg < 0:
            raise ValueError("cost assumptions cannot be negative")

