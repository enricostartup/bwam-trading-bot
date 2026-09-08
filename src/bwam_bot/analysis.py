from __future__ import annotations

import csv
import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BotConfig
from .http_client import GeckoTerminalClient, PumpClient
from .models import Coin


@dataclass(slots=True)
class TradeResult:
    mint: str
    symbol: str
    pool_address: str
    created_at: int
    inferred_migration_at: int
    migration_delay_minutes: float
    entry_at: int
    entry_price_usd: float
    entry_market_cap_usd: float
    exit_at: int
    exit_price_usd: float
    exit_reason: str
    gross_multiple: float
    net_return_pct: float
    current_market_cap_usd: float
    ath_market_cap_usd: float
    return_5m_pct: float | None
    return_15m_pct: float | None
    return_60m_pct: float | None
    return_360m_pct: float | None


def collect_launches(
    pump: PumpClient,
    wallet: str,
    days: int,
    page_size: int = 70,
    max_pages: int = 500,
    pause_seconds: float = 0.15,
) -> list[Coin]:
    cutoff_ms = int((time.time() - days * 86400) * 1000)
    found: dict[str, Coin] = {}
    for page in range(max_pages):
        coins = pump.creator_coins(wallet, page * page_size, page_size)
        if not coins:
            break
        for coin in coins:
            found[coin.mint] = coin
        oldest = min(coin.created_at_ms for coin in coins)
        if oldest < cutoff_ms or len(coins) < page_size:
            break
        time.sleep(pause_seconds)
    return sorted(
        (coin for coin in found.values() if coin.created_at_ms >= cutoff_ms),
        key=lambda coin: coin.created_at_ms,
    )


def _net_return_pct(
    multiple: float,
    notional_usd: float,
    bps_per_leg: float,
    fixed_cost_per_leg: float,
) -> float:
    fee = bps_per_leg / 10_000
    exposure = max(0.0, (notional_usd - fixed_cost_per_leg) * (1 - fee))
    exit_value = max(0.0, exposure * multiple * (1 - fee) - fixed_cost_per_leg)
    return (exit_value / notional_usd - 1) * 100


def _price_at_or_before(candles: list[list[float]], target: int) -> float | None:
    eligible = [row for row in candles if int(row[0]) <= target]
    return float(eligible[-1][4]) if eligible else None


def backtest_coin(
    coin: Coin,
    candles: list[list[float]],
    config: BotConfig,
    entry_delay_seconds: int = 60,
) -> TradeResult | None:
    if not coin.pool_address or len(candles) < 2:
        return None
    first_ts = int(candles[0][0])
    entry_target = first_ts + entry_delay_seconds
    entry_index = next(
        (index for index, row in enumerate(candles) if int(row[0]) >= entry_target),
        None,
    )
    if entry_index is None:
        return None
    entry_row = candles[entry_index]
    entry_at = int(entry_row[0])
    entry_price = float(entry_row[1])
    if entry_price <= 0:
        return None
    entry_market_cap = entry_price * coin.total_supply
    if not config.min_market_cap_usd <= entry_market_cap <= config.max_market_cap_usd:
        return None

    stop_price = entry_price * (1 - config.stop_loss_pct / 100)
    take_price = entry_price * (1 + config.take_profit_pct / 100)
    timeout = entry_at + config.max_hold_minutes * 60
    exit_at = entry_at
    exit_price = entry_price
    reason = "max_hold"

    for row in candles[entry_index:]:
        timestamp, _open, high, low, close, _volume = row[:6]
        timestamp = int(timestamp)
        if timestamp > timeout:
            break
        # Conservative convention when both thresholds occur in one candle.
        if float(low) <= stop_price:
            exit_at, exit_price, reason = timestamp, stop_price, "stop_loss"
            break
        if float(high) >= take_price:
            exit_at, exit_price, reason = timestamp, take_price, "take_profit"
            break
        exit_at, exit_price = timestamp, float(close)

    gross_multiple = exit_price / entry_price
    horizons: dict[int, float | None] = {}
    for minutes in (5, 15, 60, 360):
        price = _price_at_or_before(candles, entry_at + minutes * 60)
        horizons[minutes] = (
            _net_return_pct(
                price / entry_price,
                config.position_size_usd,
                config.fee_and_slippage_bps_per_leg,
                config.fixed_cost_usd_per_leg,
            )
            if price and price > 0
            else None
        )
    return TradeResult(
        mint=coin.mint,
        symbol=coin.symbol,
        pool_address=coin.pool_address,
        created_at=coin.created_at_ms // 1000,
        inferred_migration_at=first_ts,
        migration_delay_minutes=max(0.0, (first_ts - coin.created_at_ms / 1000) / 60),
        entry_at=entry_at,
        entry_price_usd=entry_price,
        entry_market_cap_usd=entry_market_cap,
        exit_at=exit_at,
        exit_price_usd=exit_price,
        exit_reason=reason,
        gross_multiple=gross_multiple,
        net_return_pct=_net_return_pct(
            gross_multiple,
            config.position_size_usd,
            config.fee_and_slippage_bps_per_leg,
            config.fixed_cost_usd_per_leg,
        ),
        current_market_cap_usd=coin.market_cap_usd,
        ath_market_cap_usd=coin.ath_market_cap_usd,
        return_5m_pct=horizons[5],
        return_15m_pct=horizons[15],
        return_60m_pct=horizons[60],
        return_360m_pct=horizons[360],
    )


def _safe_median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _summary(
    launches: list[Coin],
    trades: list[TradeResult],
    days: int,
    usable_ohlcv: int,
    migration_delays: list[float],
) -> dict[str, Any]:
    complete = [coin for coin in launches if coin.complete and coin.pool_address]
    day_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"launches": 0, "migrations": 0})
    for coin in launches:
        day = datetime.fromtimestamp(coin.created_at_ms / 1000, tz=timezone.utc).date().isoformat()
        day_counts[day]["launches"] += 1
        if coin.complete and coin.pool_address:
            day_counts[day]["migrations"] += 1
    returns = [trade.net_return_pct for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    horizon_summary: dict[str, Any] = {}
    for field in ("return_5m_pct", "return_15m_pct", "return_60m_pct", "return_360m_pct"):
        values = [float(getattr(trade, field)) for trade in trades if getattr(trade, field) is not None]
        horizon_summary[field] = {
            "sample": len(values),
            "median": _safe_median(values),
            "mean": statistics.fmean(values) if values else None,
            "win_rate_pct": 100 * sum(value > 0 for value in values) / len(values) if values else None,
        }
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if launches:
        oldest = min(coin.created_at_ms for coin in launches) / 1000
        newest = max(coin.created_at_ms for coin in launches) / 1000
        observed_span_days = max((newest - oldest) / 86400, 1 / 24)
        oldest_age_days = max(0.0, (time.time() - oldest) / 86400)
    else:
        observed_span_days = 0.0
        oldest_age_days = 0.0
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "requested_days": days,
        "observed_span_days": observed_span_days,
        "history_truncated_by_source": bool(launches and oldest_age_days + 0.25 < days),
        "launches": len(launches),
        "migrations": len(complete),
        "migration_rate_pct": 100 * len(complete) / len(launches) if launches else 0,
        "launches_per_observed_day": len(launches) / observed_span_days if observed_span_days else 0,
        "migrations_per_observed_day": len(complete) / observed_span_days if observed_span_days else 0,
        "ohlcv_usable": usable_ohlcv,
        "eligible_entries": len(trades),
        "filtered_by_entry_market_cap": usable_ohlcv - len(trades),
        "missing_ohlcv": len(complete) - usable_ohlcv,
        "median_migration_delay_minutes": _safe_median(migration_delays),
        "baseline": {
            "mean_net_return_pct": statistics.fmean(returns) if returns else None,
            "median_net_return_pct": _safe_median(returns),
            "win_rate_pct": 100 * len(wins) / len(returns) if returns else None,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "take_profit_count": sum(trade.exit_reason == "take_profit" for trade in trades),
            "stop_loss_count": sum(trade.exit_reason == "stop_loss" for trade in trades),
            "max_hold_count": sum(trade.exit_reason == "max_hold" for trade in trades),
        },
        "horizons": horizon_summary,
        "daily": dict(sorted(day_counts.items())),
    }


def _sensitivity(
    migrated: list[Coin],
    candles_by_mint: dict[str, list[list[float]]],
    config: BotConfig,
) -> list[dict[str, Any]]:
    variants = [
        ("instant_50tp_30sl_60m", 0, 50, 30, 60),
        ("delay1m_50tp_30sl_60m", 60, 50, 30, 60),
        ("delay2m_50tp_30sl_60m", 120, 50, 30, 60),
        ("delay5m_50tp_30sl_60m", 300, 50, 30, 60),
        ("delay1m_25tp_20sl_15m", 60, 25, 20, 15),
        ("delay1m_100tp_30sl_60m", 60, 100, 30, 60),
    ]
    output: list[dict[str, Any]] = []
    for name, delay, take_profit, stop_loss, hold in variants:
        variant_config = replace(
            config,
            take_profit_pct=float(take_profit),
            stop_loss_pct=float(stop_loss),
            max_hold_minutes=int(hold),
        )
        results = [
            result
            for coin in migrated
            if (
                result := backtest_coin(
                    coin,
                    candles_by_mint.get(coin.mint, []),
                    variant_config,
                    entry_delay_seconds=delay,
                )
            )
            is not None
        ]
        returns = [result.net_return_pct for result in results]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value <= 0]
        output.append(
            {
                "name": name,
                "entry_delay_seconds": delay,
                "take_profit_pct": take_profit,
                "stop_loss_pct": stop_loss,
                "max_hold_minutes": hold,
                "eligible_entries": len(results),
                "mean_net_return_pct": statistics.fmean(returns) if returns else None,
                "median_net_return_pct": _safe_median(returns),
                "win_rate_pct": 100 * len(wins) / len(returns) if returns else None,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            }
        )
    return output


def write_research_artifacts(
    output_dir: Path,
    launches: list[Coin],
    trades: list[TradeResult],
    summary: dict[str, Any],
    config: BotConfig,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis_snapshot.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    with (output_dir / "launches_snapshot.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "mint",
                "symbol",
                "created_at_utc",
                "complete",
                "pool_address",
                "market_cap_usd_at_snapshot",
                "ath_market_cap_usd",
            ]
        )
        for coin in launches:
            writer.writerow(
                [
                    coin.mint,
                    coin.symbol,
                    datetime.fromtimestamp(coin.created_at_ms / 1000, tz=timezone.utc).isoformat(),
                    coin.complete,
                    coin.pool_address or "",
                    coin.market_cap_usd,
                    coin.ath_market_cap_usd,
                ]
            )
    with (output_dir / "migration_backtest.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(asdict(trades[0])) if trades else [field.name for field in TradeResult.__dataclass_fields__.values()]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(trade) for trade in trades)

    baseline = summary["baseline"]
    median_return = baseline.get("median_net_return_pct")
    median_text = f"{median_return:.2f}%" if median_return is not None else "n/d"
    history_truncated_text = "sì" if summary["history_truncated_by_source"] else "no"
    profit_factor = baseline.get("profit_factor")
    profit_factor_text = f"{profit_factor:.3f}" if profit_factor is not None else "n/d"
    verdict = (
        "NO-GO per denaro reale; GO soltanto per forward paper trading."
        if not trades or (median_return is not None and median_return <= 0)
        else "Dati preliminari non sufficienti: continuare solo in paper trading."
    )
    report = f"""# Audit del wallet e baseline storica

Generato: {summary['generated_at']}

## Verdetto

**{verdict}** Il campione storico non dimostra eseguibilità reale: OHLCV a un minuto non contiene mempool latency, price impact individuale, transazioni fallite o MEV.

## Campione

- Finestra richiesta: {summary['requested_days']} giorni
- Finestra effettivamente restituita dalla sorgente: {summary['observed_span_days']:.2f} giorni
- Storico troncato dalla sorgente: {history_truncated_text}
- Launch osservati: {summary['launches']}
- Migrazioni: {summary['migrations']} ({summary['migration_rate_pct']:.2f}%)
- Frequenza media sul periodo osservato: {summary['migrations_per_observed_day']:.2f} migrazioni/giorno
- Token migrati con OHLCV utilizzabile: {summary['ohlcv_usable']}
- Ingressi che superano il filtro market cap: {summary['eligible_entries']}
- Esclusi dal filtro market cap: {summary['filtered_by_entry_market_cap']}
- Token migrati senza OHLCV utilizzabile: {summary['missing_ohlcv']}
- Ritardo mediano launch → prima candela del pool: {summary['median_migration_delay_minutes'] or 0:.1f} minuti

## Baseline dichiarata prima del test

Ingresso: apertura della prima candela disponibile almeno 60 secondi dopo la prima candela del pool. Uscita: take profit +{config.take_profit_pct:.0f}%, stop -{config.stop_loss_pct:.0f}% o {config.max_hold_minutes} minuti. Se TP e SL compaiono nella stessa candela, viene contato prima lo stop. Capitale ${config.position_size_usd:.2f}; costo per tratta {config.fee_and_slippage_bps_per_leg:.0f} bps + ${config.fixed_cost_usd_per_leg:.2f}.

- Rendimento netto mediano: {median_text}
- Win rate: {baseline.get('win_rate_pct') or 0:.2f}%
- Rendimento netto medio: {baseline.get('mean_net_return_pct') or 0:.2f}%
- Profit factor: {profit_factor_text}
- Esiti: TP {baseline.get('take_profit_count')}, stop {baseline.get('stop_loss_count')}, timeout {baseline.get('max_hold_count')}

## Sensibilità (non ottimizzazione)

| Variante | N | Media netta | Mediana netta | Win rate | Profit factor |
|---|---:|---:|---:|---:|---:|
{chr(10).join(f"| {row['name']} | {row['eligible_entries']} | {(row['mean_net_return_pct'] or 0):.2f}% | {(row['median_net_return_pct'] or 0):.2f}% | {(row['win_rate_pct'] or 0):.2f}% | {row['profit_factor']:.3f} |" if row['profit_factor'] is not None else f"| {row['name']} | {row['eligible_entries']} | {(row['mean_net_return_pct'] or 0):.2f}% | {(row['median_net_return_pct'] or 0):.2f}% | {(row['win_rate_pct'] or 0):.2f}% | n/d |" for row in summary['sensitivity'])}

Le varianti sono state fissate per controllare la robustezza a ritardo e uscite, non per scegliere retrospettivamente la migliore. Più righe testate aumentano il rischio di data snooping.

## Limiti che impediscono conclusioni forti

1. L’endpoint Pump.fun usato è pubblico ma non è un contratto di servizio stabile.
2. La prima candela GeckoTerminal approssima la migrazione; non è un timestamp di fill.
3. Le candele a un minuto creano ambiguità intrabar e nascondono slippage/MEV.
4. La sorgente ha troncato lo storico a {summary['launches']} launch ({summary['observed_span_days']:.2f} giorni effettivi) e il risultato può dipendere dal regime di mercato.
5. Le metriche del creator riportate da tracker terzi non sono un audit contabile.
6. L’ultimo prezzo scambiato non garantisce che una posizione della size ipotizzata sia liquidabile a quel prezzo.

Il criterio “market cap > 30k” non seleziona molto se l’ingresso avviene **dopo** la migrazione: la graduation stessa avviene normalmente a una capitalizzazione superiore. Va trattato come controllo anti-crollo al momento del rilevamento, non come fonte di edge.

## Cosa significa davvero “safe”

La documentazione ufficiale Pump.fun dice che, dopo la graduation, il pool canonico appartiene al protocollo: il creator non può semplicemente ritirare quella liquidità. È una protezione contro il classico liquidity rug, non contro vendite, sniper, concentrazione degli holder o un crollo del 90%.

L’affermazione assoluta “questo creator non vende” è falsa almeno in un caso direttamente visibile: nella cronologia del token `AE3jmK…Kk8r`, Solscan mostra 268.249.999,999999 token trasferiti dalla bonding curve al wallet e poi dal wallet indietro alla bonding curve. Inoltre, due token migrati controllati durante questo audit non risultavano più nei token account del wallet. Questo non prova un rug; prova che “non vende mai” non è una premessa utilizzabile.

TokenRadar etichetta il deployer “Serial rugger” e mostra 32 token “safe” su 6.979 indicizzati. È una classificazione euristica di terzi e non viene usata come verità nel backtest, ma contraddice l’idea che la reputazione “tutte safe” sia pacifica.

## Fonti

- [Wallet su Solscan](https://solscan.io/account/bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa)
- [Bonding curve e migrazione, documentazione Pump.fun](https://pump.fun/docs/bonding-curve)
- [Fee schedule Pump.fun/PumpSwap](https://pump.fun/docs/fees)
- [Programma Pump ufficiale](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md)
- [Esempio di acquisto e restituzione dei token del creator](https://solscan.io/account/AE3jmKsufnYbBUaZ1rFXQZLmsA6mxaEf151a4VfnKk8r)
- [Profilo euristico TokenRadar](https://tokenradar.app/deployers/bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa)
"""
    (output_dir / "REPORT_IT.md").write_text(report, encoding="utf-8")


def run_research(
    pump: PumpClient,
    gecko: GeckoTerminalClient,
    config: BotConfig,
    days: int,
    output_dir: Path,
    gecko_pause_seconds: float = 12.5,
    emit=print,
) -> dict[str, Any]:
    launches = collect_launches(pump, config.wallet, days)
    migrated = [coin for coin in launches if coin.complete and coin.pool_address]
    emit(f"launches={len(launches)} migrations={len(migrated)}")
    cache_dir = output_dir / "ohlcv_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    trades: list[TradeResult] = []
    usable_ohlcv = 0
    migration_delays: list[float] = []
    candles_by_mint: dict[str, list[list[float]]] = {}
    for index, coin in enumerate(migrated, start=1):
        cache_path = cache_dir / f"{coin.mint}.json"
        candles: list[list[float]] | None = None
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            # Empty files from an interrupted/limited collection are retried.
            if cached:
                candles = cached
        if candles is None:
            before = min(int(time.time()), coin.created_at_ms // 1000 + 24 * 3600)
            try:
                candles = gecko.minute_ohlcv(coin.pool_address or "", before, 1000)
            except RuntimeError as error:
                emit(f"ohlcv {index}/{len(migrated)} {coin.symbol}: {error}")
                candles = []
            else:
                cache_path.write_text(json.dumps(candles), encoding="utf-8")
            time.sleep(gecko_pause_seconds)
        if len(candles) >= 2:
            usable_ohlcv += 1
            migration_delays.append(
                max(0.0, (int(candles[0][0]) - coin.created_at_ms / 1000) / 60)
            )
        candles_by_mint[coin.mint] = candles
        result = backtest_coin(coin, candles, config)
        if result:
            trades.append(result)
        if index % 10 == 0 or index == len(migrated):
            emit(f"ohlcv progress {index}/{len(migrated)} eligible={len(trades)}")
    summary = _summary(launches, trades, days, usable_ohlcv, migration_delays)
    summary["sensitivity"] = _sensitivity(migrated, candles_by_mint, config)
    write_research_artifacts(output_dir, launches, trades, summary, config)
    return summary
