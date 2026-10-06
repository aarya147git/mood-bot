"""
Unit Tests for Wordle logic in wordle_view.py
"""

import unittest
from ui.wordle_view import evaluate_guess, TILE_CORRECT, TILE_PRESENT, TILE_ABSENT


class TestWordleLogic(unittest.TestCase):
    def test_exact_match(self) -> None:
        result = evaluate_guess("MUSIC", "MUSIC")
        self.assertEqual(result, [TILE_CORRECT] * 5)

    def test_all_wrong(self) -> None:
        result = evaluate_guess("AUDIO", "SWEET")
        self.assertEqual(result, [TILE_ABSENT] * 5)

    def test_partial_match(self) -> None:
        # Target: FOCUS. Guess: FROST
        # F: Correct (🟩), R: Absent (⬛), O: Present (🟨), S: Present (🟨, in FOCUS at pos 4), T: Absent (⬛)
        result = evaluate_guess("FROST", "FOCUS")
        self.assertEqual(result[0], TILE_CORRECT)
        self.assertEqual(result[1], TILE_ABSENT)
        self.assertEqual(result[2], TILE_PRESENT)
        self.assertEqual(result[3], TILE_PRESENT)
        self.assertEqual(result[4], TILE_ABSENT)

    def test_duplicate_letter_handling(self) -> None:
        # Target: SPEED (two Es). Guess: SWEET (two Es)
        # S: Correct, W: Absent, E: Correct, E: Correct, T: Absent
        result = evaluate_guess("SWEET", "SPEED")
        self.assertEqual(result, [TILE_CORRECT, TILE_ABSENT, TILE_CORRECT, TILE_CORRECT, TILE_ABSENT])

        # Target: PIANO (one A at pos 2). Guess: SLATE (one A at pos 2) -> Exact match
        result = evaluate_guess("SLATE", "PIANO")
        self.assertEqual(result[2], TILE_CORRECT)

        # Target: PIANO (one A at pos 2). Guess: ALERT (A at pos 0) -> Present (Yellow)
        result = evaluate_guess("ALERT", "PIANO")
        self.assertEqual(result[0], TILE_PRESENT)


if __name__ == "__main__":
    unittest.main()
