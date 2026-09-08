from __future__ import annotations

from datetime import datetime, timezone

from .config import BotConfig
from .models import Coin, ExitDecision, Position


def paper_entry_exposure(config: BotConfig) -> tuple[float, float]:
    fee_fraction = config.fee_and_slippage_bps_per_leg / 10_000
    exposure = max(
        0.0,
        (config.position_size_usd - config.fixed_cost_usd_per_leg) * (1 - fee_fraction),
    )
    return exposure, config.position_size_usd - exposure


def paper_exit_value(config: BotConfig, position: Position, market_cap_usd: float) -> float:
    gross = position.exposure_units * market_cap_usd
    fee_fraction = config.fee_and_slippage_bps_per_leg / 10_000
    return max(0.0, gross * (1 - fee_fraction) - config.fixed_cost_usd_per_leg)


def can_enter(
    config: BotConfig,
    coin: Coin,
    first_completed_at: int | None,
    open_positions: int,
    realized_today_usd: float,
    now: int,
) -> tuple[bool, str]:
    if coin.creator != config.wallet:
        return False, "wrong_creator"
    if not coin.complete or not coin.pool_address:
        return False, "not_migrated"
    if coin.market_cap_usd < config.min_market_cap_usd:
        return False, "below_min_market_cap"
    if coin.market_cap_usd > config.max_market_cap_usd:
        return False, "above_max_market_cap"
    if first_completed_at is None:
        return False, "migration_time_unknown"
    if now - first_completed_at > config.entry_window_minutes * 60:
        return False, "entry_window_expired"
    if open_positions >= config.max_open_positions:
        return False, "max_open_positions"
    if realized_today_usd <= -config.daily_loss_limit_usd:
        return False, "daily_loss_limit"
    return True, "eligible"


def exit_decision(config: BotConfig, position: Position, market_cap_usd: float, now: int) -> ExitDecision:
    if market_cap_usd <= 0:
        return ExitDecision(False)
    change_pct = (market_cap_usd / position.entry_market_cap_usd - 1) * 100
    if change_pct <= -config.stop_loss_pct:
        return ExitDecision(True, "stop_loss")
    if change_pct >= config.take_profit_pct:
        return ExitDecision(True, "take_profit")
    peak_change_pct = (position.peak_market_cap_usd / position.entry_market_cap_usd - 1) * 100
    if peak_change_pct >= config.trailing_activation_pct:
        drawdown_pct = (1 - market_cap_usd / position.peak_market_cap_usd) * 100
        if drawdown_pct >= config.trailing_stop_pct:
            return ExitDecision(True, "trailing_stop")
    if now - position.opened_at >= config.max_hold_minutes * 60:
        return ExitDecision(True, "max_hold")
    return ExitDecision(False)


def utc_day_start(now: int) -> int:
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    return int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

