from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Coin:
    mint: str
    creator: str
    name: str
    symbol: str
    created_at_ms: int
    complete: bool
    pool_address: str | None
    market_cap_usd: float
    market_cap_quote: float
    ath_market_cap_usd: float
    quote_mint: str | None
    total_supply: float
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Coin":
        created = int(_number(raw.get("created_timestamp")))
        if created and created < 10_000_000_000:
            created *= 1000
        pool = raw.get("pool_address") or raw.get("raydium_pool")
        market_cap_usd = _number(raw.get("market_cap_usd"))
        if market_cap_usd <= 0:
            market_cap_usd = _number(raw.get("usd_market_cap"))
        total_supply = _number(raw.get("total_supply_str") or raw.get("total_supply"))
        decimals = int(_number(raw.get("base_decimals"), 6))
        if total_supply > 1_000_000_000_000 and decimals > 0:
            total_supply /= 10**decimals
        return cls(
            mint=str(raw.get("mint") or ""),
            creator=str(raw.get("creator") or ""),
            name=str(raw.get("name") or ""),
            symbol=str(raw.get("symbol") or ""),
            created_at_ms=created,
            complete=bool(raw.get("complete")),
            pool_address=str(pool) if pool else None,
            market_cap_usd=market_cap_usd,
            market_cap_quote=_number(raw.get("market_cap_quote") or raw.get("market_cap")),
            ath_market_cap_usd=_number(raw.get("ath_market_cap")),
            quote_mint=str(raw.get("quote_mint")) if raw.get("quote_mint") else None,
            total_supply=total_supply,
            raw=raw,
        )


@dataclass(slots=True)
class Position:
    id: int
    mint: str
    symbol: str
    opened_at: int
    entry_market_cap_usd: float
    notional_usd: float
    exposure_units: float
    peak_market_cap_usd: float
    status: str


@dataclass(frozen=True, slots=True)
class ExitDecision:
    should_exit: bool
    reason: str | None = None
