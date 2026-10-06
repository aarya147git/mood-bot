"""
Unit Tests for xp_service.py
"""

import tempfile
import unittest
from pathlib import Path
from services.xp_service import XPService, calculate_level, xp_for_level


class TestXPService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "test_stats.json"
        self.service = XPService(data_path=self.data_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_level_calculation(self) -> None:
        """Level calculation should scale quadratically."""
        self.assertEqual(calculate_level(0), 1)
        self.assertEqual(calculate_level(99), 1)
        self.assertEqual(calculate_level(100), 2)
        self.assertEqual(calculate_level(399), 2)
        self.assertEqual(calculate_level(400), 3)
        self.assertEqual(calculate_level(900), 4)

    def test_xp_for_level(self) -> None:
        self.assertEqual(xp_for_level(1), 0)
        self.assertEqual(xp_for_level(2), 100)
        self.assertEqual(xp_for_level(3), 400)

    def test_add_xp_and_level_up(self) -> None:
        xp, leveled_up, level = self.service.add_xp(user_id=123, amount=150)
        self.assertEqual(xp, 150)
        self.assertTrue(leveled_up)
        self.assertEqual(level, 2)

    def test_record_focus_session(self) -> None:
        xp_earned, leveled_up, level, streak = self.service.record_focus_session(user_id=456, minutes=25)
        self.assertEqual(xp_earned, 250)
        self.assertEqual(streak, 1)
        profile = self.service.get_user_profile(user_id=456)
        self.assertEqual(profile["focus_minutes"], 25)
        self.assertEqual(profile["focus_sessions"], 1)

    def test_record_wordle_game(self) -> None:
        xp_earned, _, _ = self.service.record_wordle_game(user_id=789, won=True, attempts=3)
        self.assertEqual(xp_earned, 100)
        profile = self.service.get_user_profile(user_id=789)
        self.assertEqual(profile["wordle_wins"], 1)
        self.assertEqual(profile["wordle_played"], 1)


if __name__ == "__main__":
    unittest.main()
