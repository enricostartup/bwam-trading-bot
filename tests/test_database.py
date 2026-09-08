import tempfile
import unittest
from pathlib import Path

from bwam_bot.database import Database
from bwam_bot.models import Coin


class DatabaseTests(unittest.TestCase):
    def test_already_completed_coin_is_not_a_fresh_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "paper.db")
            historical = Coin(
                mint="historical",
                creator="creator",
                name="name",
                symbol="OLD",
                created_at_ms=1,
                complete=True,
                pool_address="pool",
                market_cap_usd=60_000,
                market_cap_quote=600,
                ath_market_cap_usd=80_000,
                quote_mint=None,
                total_supply=1,
            )
            database.upsert_coin(historical, 100)
            database.upsert_coin(historical, 200)
            self.assertIsNone(database.first_completed_at("historical"))
            database.close()

    def test_first_completion_time_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "paper.db")
            base = dict(
                mint="mint",
                creator="creator",
                name="name",
                symbol="SYM",
                created_at_ms=1,
                pool_address=None,
                market_cap_usd=10,
                market_cap_quote=1,
                ath_market_cap_usd=10,
                quote_mint=None,
                total_supply=1,
            )
            database.upsert_coin(Coin(complete=False, **base), 100)
            database.upsert_coin(Coin(complete=True, **{**base, "pool_address": "pool"}), 200)
            database.upsert_coin(Coin(complete=True, **{**base, "pool_address": "pool"}), 300)
            self.assertEqual(database.first_completed_at("mint"), 200)
            database.close()


if __name__ == "__main__":
    unittest.main()
