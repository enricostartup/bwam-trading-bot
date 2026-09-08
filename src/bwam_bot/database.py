from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .models import Coin, Position


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS coins (
    mint TEXT PRIMARY KEY,
    creator TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    complete INTEGER NOT NULL,
    pool_address TEXT,
    market_cap_usd REAL NOT NULL,
    ath_market_cap_usd REAL NOT NULL,
    first_seen_at INTEGER NOT NULL,
    first_completed_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL UNIQUE REFERENCES coins(mint),
    symbol TEXT NOT NULL,
    opened_at INTEGER NOT NULL,
    entry_market_cap_usd REAL NOT NULL,
    notional_usd REAL NOT NULL,
    exposure_units REAL NOT NULL,
    entry_cost_usd REAL NOT NULL,
    peak_market_cap_usd REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
    closed_at INTEGER,
    exit_market_cap_usd REAL,
    exit_value_usd REAL,
    pnl_usd REAL,
    exit_reason TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    observed_at INTEGER NOT NULL,
    market_cap_usd REAL NOT NULL,
    complete INTEGER NOT NULL,
    UNIQUE(mint, observed_at)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at INTEGER NOT NULL,
    kind TEXT NOT NULL,
    mint TEXT,
    detail TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def upsert_coin(self, coin: Coin, observed_at: int | None = None) -> None:
        now = observed_at or int(time.time())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO coins (
                    mint, creator, name, symbol, created_at_ms, complete, pool_address,
                    market_cap_usd, ath_market_cap_usd, first_seen_at,
                    first_completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mint) DO UPDATE SET
                    name=excluded.name,
                    symbol=excluded.symbol,
                    complete=excluded.complete,
                    pool_address=COALESCE(excluded.pool_address, coins.pool_address),
                    market_cap_usd=excluded.market_cap_usd,
                    ath_market_cap_usd=MAX(coins.ath_market_cap_usd, excluded.ath_market_cap_usd),
                    first_completed_at=CASE
                        WHEN coins.first_completed_at IS NULL
                             AND coins.complete=0 AND excluded.complete=1
                        THEN excluded.updated_at ELSE coins.first_completed_at END,
                    updated_at=excluded.updated_at
                """,
                (
                    coin.mint,
                    coin.creator,
                    coin.name,
                    coin.symbol,
                    coin.created_at_ms,
                    int(coin.complete),
                    coin.pool_address,
                    coin.market_cap_usd,
                    coin.ath_market_cap_usd,
                    now,
                    # A coin first observed as already complete is historical state,
                    # not a migration signal. Only an observed false -> true transition
                    # is eligible for entry (handled by the conflict clause above).
                    None,
                    now,
                ),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO observations VALUES (NULL, ?, ?, ?, ?)",
                (coin.mint, now, coin.market_cap_usd, int(coin.complete)),
            )

    def first_completed_at(self, mint: str) -> int | None:
        row = self.connection.execute(
            "SELECT first_completed_at FROM coins WHERE mint=?", (mint,)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def has_position(self, mint: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM positions WHERE mint=?", (mint,)
        ).fetchone() is not None

    def open_positions(self) -> list[Position]:
        rows = self.connection.execute(
            """SELECT id, mint, symbol, opened_at, entry_market_cap_usd,
                      notional_usd, exposure_units, peak_market_cap_usd, status
               FROM positions WHERE status='open' ORDER BY opened_at"""
        ).fetchall()
        return [Position(**dict(row)) for row in rows]

    def open_position(
        self,
        coin: Coin,
        notional_usd: float,
        exposure_units: float,
        entry_cost_usd: float,
        now: int,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO positions (
                       mint, symbol, opened_at, entry_market_cap_usd, notional_usd,
                       exposure_units, entry_cost_usd, peak_market_cap_usd, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                (
                    coin.mint,
                    coin.symbol,
                    now,
                    coin.market_cap_usd,
                    notional_usd,
                    exposure_units,
                    entry_cost_usd,
                    coin.market_cap_usd,
                ),
            )
            self.event("entry", coin.mint, f"paper entry at mcap ${coin.market_cap_usd:.2f}", now)

    def update_peak(self, position_id: int, peak_market_cap_usd: float) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE positions SET peak_market_cap_usd=? WHERE id=?",
                (peak_market_cap_usd, position_id),
            )

    def close_position(
        self,
        position: Position,
        exit_market_cap_usd: float,
        exit_value_usd: float,
        reason: str,
        now: int,
    ) -> float:
        pnl = exit_value_usd - position.notional_usd
        with self.connection:
            self.connection.execute(
                """UPDATE positions SET status='closed', closed_at=?,
                       exit_market_cap_usd=?, exit_value_usd=?, pnl_usd=?, exit_reason=?
                   WHERE id=? AND status='open'""",
                (now, exit_market_cap_usd, exit_value_usd, pnl, reason, position.id),
            )
            self.event("exit", position.mint, f"{reason}; paper PnL ${pnl:.2f}", now)
        return pnl

    def realized_pnl_since(self, since_epoch: int) -> float:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM positions WHERE closed_at>=?",
            (since_epoch,),
        ).fetchone()
        return float(row[0])

    def event(self, kind: str, mint: str | None, detail: str, now: int | None = None) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO events VALUES (NULL, ?, ?, ?, ?)",
                (now or int(time.time()), kind, mint, detail),
            )

    def summary(self) -> dict[str, float | int]:
        open_count = self.connection.execute(
            "SELECT COUNT(*) FROM positions WHERE status='open'"
        ).fetchone()[0]
        closed_count, pnl = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_usd), 0) FROM positions WHERE status='closed'"
        ).fetchone()
        watched, completed = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(complete), 0) FROM coins"
        ).fetchone()
        return {
            "watched_coins": int(watched),
            "completed_coins": int(completed),
            "open_positions": int(open_count),
            "closed_positions": int(closed_count),
            "realized_pnl_usd": float(pnl),
        }
