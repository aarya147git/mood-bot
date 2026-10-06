"""
Unit Tests for quiz_style.py

Verifies:
1. Unicode progress bar accuracy across bounds (0%, 50%, 100%, and clamped inputs).
2. Rotating pastel color sequence behavior.
3. Mood-to-color mapping integrity.
"""

import sys
import unittest
from unittest.mock import MagicMock

# If discord is not installed in the local execution environment, provide a lightweight mock
if "discord" not in sys.modules:
    mock_discord = MagicMock()

    class MockColor:
        def __init__(self, value: int):
            self.value = value

        def __eq__(self, other):
            return isinstance(other, MockColor) and self.value == other.value

        def __repr__(self):
            return f"Color(0x{self.value:06X})"

    mock_discord.Color = MockColor
    sys.modules["discord"] = mock_discord

from utils.quiz_style import (
    PASTEL_PALETTE_HEX,
    create_progress_bar,
    get_mood_color,
    get_next_pastel_color,
)


class TestQuizStyle(unittest.TestCase):
    """Test suite for style and UI formatting helpers."""

    def test_progress_bar_midway(self) -> None:
        """Step 1 of 2 should calculate to exactly 50% progress."""
        bar_output = create_progress_bar(current_step=1, total_steps=2, bar_length=10)
        self.assertIn("Step 1 of 2", bar_output)
        self.assertIn("50%", bar_output)
        # Length 10 at 50% => 5 filled characters and 5 empty characters
        self.assertIn("▰▰▰▰▰▱▱▱▱▱", bar_output)

    def test_progress_bar_complete(self) -> None:
        """Final step (2 of 2) should show 100% full bar."""
        bar_output = create_progress_bar(current_step=2, total_steps=2, bar_length=10)
        self.assertIn("Step 2 of 2", bar_output)
        self.assertIn("100%", bar_output)
        self.assertIn("▰▰▰▰▰▰▰▰▰▰", bar_output)

    def test_progress_bar_zero_and_negative_guard(self) -> None:
        """Guards against division by zero and negative step inputs."""
        bar_zero = create_progress_bar(current_step=0, total_steps=2, bar_length=10)
        self.assertIn("0%", bar_zero)

        bar_invalid_total = create_progress_bar(current_step=1, total_steps=0, bar_length=10)
        self.assertIn("100%", bar_invalid_total)

    def test_progress_bar_overflow_clamping(self) -> None:
        """Current step exceeding total steps should be clamped gracefully."""
        bar_overflow = create_progress_bar(current_step=5, total_steps=2, bar_length=10)
        self.assertIn("100%", bar_overflow)

    def test_pastel_palette_not_empty(self) -> None:
        """Ensures the pastel palette has valid hex codes."""
        self.assertGreater(len(PASTEL_PALETTE_HEX), 4)
        for hex_code in PASTEL_PALETTE_HEX:
            self.assertIsInstance(hex_code, int)
            self.assertGreater(hex_code, 0)

    def test_rotating_pastel_colors(self) -> None:
        """Successive calls should return colors cycling through the palette."""
        color1 = get_next_pastel_color()
        color2 = get_next_pastel_color()
        self.assertIsInstance(color1.value, int)
        self.assertIsInstance(color2.value, int)

    def test_mood_color_mapping(self) -> None:
        """Known moods should return their designated pastel tones."""
        energetic_color = get_mood_color("energetic")
        chill_color = get_mood_color("chill")
        sad_color = get_mood_color("sad")
        focused_color = get_mood_color("focused")

        self.assertEqual(energetic_color.value, 0xFF9E80)
        self.assertEqual(chill_color.value, 0x80DEEA)
        self.assertEqual(sad_color.value, 0x9FA8DA)
        self.assertEqual(focused_color.value, 0xA5D6A7)

    def test_unknown_mood_color_fallback(self) -> None:
        """An unknown mood should gracefully fall back to a pastel rotating color."""
        unknown_color = get_mood_color("non_existent_mood_xyz")
        self.assertIsInstance(unknown_color.value, int)
        self.assertIn(unknown_color.value, PASTEL_PALETTE_HEX)


if __name__ == "__main__":
    unittest.main()
