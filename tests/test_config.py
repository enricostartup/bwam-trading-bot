import unittest

from bwam_bot.config import BotConfig


class ConfigTests(unittest.TestCase):
    def test_rejects_live_mode(self) -> None:
        config = BotConfig(mode="live")
        with self.assertRaisesRegex(ValueError, "paper-only"):
            config.validate()

    def test_default_is_valid(self) -> None:
        BotConfig().validate()


if __name__ == "__main__":
    unittest.main()

