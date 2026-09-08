import unittest

from bwam_bot.config import BotConfig
from bwam_bot.models import Coin, Position
from bwam_bot.strategy import can_enter, exit_decision, paper_entry_exposure, paper_exit_value


def coin(**overrides):
    values = dict(
        mint="A" * 44,
        creator=BotConfig().wallet,
        name="Token",
        symbol="TKN",
        created_at_ms=1_000_000,
        complete=True,
        pool_address="P" * 44,
        market_cap_usd=60_000,
        market_cap_quote=600,
        ath_market_cap_usd=80_000,
        quote_mint=None,
        total_supply=1_000_000_000,
    )
    values.update(overrides)
    return Coin(**values)


class StrategyTests(unittest.TestCase):
    def test_requires_migration_and_pool(self) -> None:
        config = BotConfig()
        allowed, reason = can_enter(config, coin(complete=False), 100, 0, 0, 100)
        self.assertFalse(allowed)
        self.assertEqual(reason, "not_migrated")

    def test_market_cap_filter(self) -> None:
        config = BotConfig()
        allowed, reason = can_enter(config, coin(market_cap_usd=29_999), 100, 0, 0, 100)
        self.assertFalse(allowed)
        self.assertEqual(reason, "below_min_market_cap")

    def test_eligible_coin(self) -> None:
        config = BotConfig()
        allowed, reason = can_enter(config, coin(), 100, 0, 0, 101)
        self.assertTrue(allowed)
        self.assertEqual(reason, "eligible")

    def test_costs_make_flat_trade_a_loss(self) -> None:
        config = BotConfig()
        exposure, entry_cost = paper_entry_exposure(config)
        position = Position(1, "mint", "TKN", 0, 60_000, 50, exposure / 60_000, 60_000, "open")
        exit_value = paper_exit_value(config, position, 60_000)
        self.assertLess(exit_value, 50)
        self.assertGreater(entry_cost, 0)

    def test_stop_and_take_profit(self) -> None:
        config = BotConfig()
        position = Position(1, "mint", "TKN", 0, 100, 50, 0.5, 100, "open")
        self.assertEqual(exit_decision(config, position, 69, 1).reason, "stop_loss")
        self.assertEqual(exit_decision(config, position, 151, 1).reason, "take_profit")


if __name__ == "__main__":
    unittest.main()

