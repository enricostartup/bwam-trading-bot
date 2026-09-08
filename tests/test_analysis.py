import unittest

from bwam_bot.analysis import backtest_coin
from bwam_bot.config import BotConfig
from bwam_bot.models import Coin


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coin = Coin(
            mint="mint",
            creator=BotConfig().wallet,
            name="name",
            symbol="SYM",
            created_at_ms=900_000,
            complete=True,
            pool_address="pool",
            market_cap_usd=10_000,
            market_cap_quote=100,
            ath_market_cap_usd=20_000,
            quote_mint=None,
            total_supply=100_000,
        )

    def test_intrabar_ambiguity_is_conservative(self) -> None:
        candles = [
            [1000, 1.0, 1.1, 0.9, 1.0, 10],
            [1060, 1.0, 1.6, 0.6, 1.2, 10],
        ]
        result = backtest_coin(self.coin, candles, BotConfig())
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_reason, "stop_loss")


if __name__ == "__main__":
    unittest.main()
