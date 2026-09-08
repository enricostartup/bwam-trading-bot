from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import Coin


class JsonHttpClient:
    def __init__(self, timeout: int = 20, max_retries: int = 4) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = "bwam-migration-paperbot/0.1 (+research; paper-only)"

    def get(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code < 600
                if not retryable or attempt >= self.max_retries:
                    raise RuntimeError(f"HTTP {error.code} for {url}") from error
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 1.5 * (2**attempt)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Request failed for {url}: {error}") from error
                delay = 1.5 * (2**attempt)
            time.sleep(delay + random.random() * 0.25)
        raise AssertionError("unreachable")


class PumpClient:
    def __init__(self, http: JsonHttpClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    def creator_coins(self, creator: str, offset: int = 0, limit: int = 70) -> list[Coin]:
        query = urllib.parse.urlencode(
            {
                "creator": creator,
                "offset": offset,
                "limit": limit,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "true",
            }
        )
        payload = self.http.get(f"{self.base_url}/coins?{query}")
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected Pump.fun creator-coins response")
        coins = [Coin.from_api(item) for item in payload if isinstance(item, dict)]
        return [coin for coin in coins if coin.creator == creator and coin.mint]

    def coin(self, mint: str) -> Coin:
        payload = self.http.get(f"{self.base_url}/coins/{urllib.parse.quote(mint)}")
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Pump.fun coin response")
        return Coin.from_api(payload)


class GeckoTerminalClient:
    BASE_URL = "https://api.geckoterminal.com/api/v2"

    def __init__(self, http: JsonHttpClient) -> None:
        self.http = http

    def minute_ohlcv(
        self, pool_address: str, before_timestamp: int, limit: int = 1000
    ) -> list[list[float]]:
        query = urllib.parse.urlencode(
            {
                "aggregate": 1,
                "before_timestamp": before_timestamp,
                "limit": min(limit, 1000),
                "currency": "usd",
            }
        )
        pool = urllib.parse.quote(pool_address)
        payload = self.http.get(
            f"{self.BASE_URL}/networks/solana/pools/{pool}/ohlcv/minute?{query}"
        )
        rows = payload.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
        if not isinstance(rows, list):
            return []
        clean = [row for row in rows if isinstance(row, list) and len(row) >= 6]
        return sorted(clean, key=lambda row: int(row[0]))

