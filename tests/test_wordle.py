"""
Unit Tests for Wordle logic and Multiplayer FIFO Queue state in wordle_view.py
"""

import unittest
from unittest.mock import MagicMock
from ui.wordle_view import (
    MultiplayerWordleGame,
    WordleGameView,
    evaluate_guess,
    TILE_CORRECT,
    TILE_PRESENT,
    TILE_ABSENT,
)


class TestWordleLogic(unittest.TestCase):
    def test_exact_match(self) -> None:
        result = evaluate_guess("MUSIC", "MUSIC")
        self.assertEqual(result, [TILE_CORRECT] * 5)

    def test_all_wrong(self) -> None:
        result = evaluate_guess("AUDIO", "SWEET")
        self.assertEqual(result, [TILE_ABSENT] * 5)

    def test_partial_match(self) -> None:
        result = evaluate_guess("FROST", "FOCUS")
        self.assertEqual(result[0], TILE_CORRECT)
        self.assertEqual(result[1], TILE_ABSENT)
        self.assertEqual(result[2], TILE_PRESENT)
        self.assertEqual(result[3], TILE_PRESENT)
        self.assertEqual(result[4], TILE_ABSENT)

    def test_duplicate_letter_handling(self) -> None:
        result = evaluate_guess("SWEET", "SPEED")
        self.assertEqual(result, [TILE_CORRECT, TILE_ABSENT, TILE_CORRECT, TILE_CORRECT, TILE_ABSENT])

        result = evaluate_guess("SLATE", "PIANO")
        self.assertEqual(result[2], TILE_CORRECT)

        result = evaluate_guess("ALERT", "PIANO")
        self.assertEqual(result[0], TILE_PRESENT)


class TestMultiplayerWordleGame(unittest.TestCase):
    def setUp(self) -> None:
        self.p1 = MagicMock(id=101, display_name="Player1", mention="<@101>")
        self.p2 = MagicMock(id=102, display_name="Player2", mention="<@102>")
        self.p3 = MagicMock(id=103, display_name="Player3", mention="<@103>")

    def test_roster_deduplication_and_order(self) -> None:
        # Pass p1 twice, order should be p1, p2, p3
        roster = [self.p1, self.p2, self.p1, self.p3]
        game = MultiplayerWordleGame(channel_id=1, roster=roster, target_word="MUSIC")

        self.assertEqual(len(game.roster), 3)
        self.assertEqual(game.roster[0].id, 101)
        self.assertEqual(game.roster[1].id, 102)
        self.assertEqual(game.roster[2].id, 103)

    def test_fifo_turn_rotation(self) -> None:
        game = MultiplayerWordleGame(channel_id=1, roster=[self.p1, self.p2, self.p3], target_word="MUSIC")

        # Player 1 turn initially
        self.assertEqual(game.current_player.id, 101)
        self.assertEqual(game.next_player.id, 102)
        self.assertTrue(game.is_current_turn(101))
        self.assertFalse(game.is_current_turn(102))

        # Player 1 guesses wrong -> turns rotates to Player 2
        game.process_guess(self.p1, "AUDIO")
        self.assertEqual(game.current_player.id, 102)
        self.assertEqual(game.next_player.id, 103)
        self.assertTrue(game.is_current_turn(102))

        # Player 2 guesses wrong -> turns rotates to Player 3
        game.process_guess(self.p2, "CHILL")
        self.assertEqual(game.current_player.id, 103)
        self.assertEqual(game.next_player.id, 101)
        self.assertTrue(game.is_current_turn(103))

        # Player 3 guesses wrong -> turns rotates back to Player 1 (FIFO loop)
        game.process_guess(self.p3, "BEATS")
        self.assertEqual(game.current_player.id, 101)
        self.assertEqual(game.next_player.id, 102)

    def test_roster_restriction(self) -> None:
        game = MultiplayerWordleGame(channel_id=1, roster=[self.p1, self.p2], target_word="MUSIC")

        self.assertTrue(game.is_player_in_roster(101))
        self.assertTrue(game.is_player_in_roster(102))
        self.assertFalse(game.is_player_in_roster(999))  # Outsider

    def test_win_condition(self) -> None:
        game = MultiplayerWordleGame(channel_id=1, roster=[self.p1, self.p2], target_word="MUSIC")

        game.process_guess(self.p1, "MUSIC")
        self.assertTrue(game.is_over)
        self.assertTrue(game.won)

    def test_loss_condition_after_6_attempts(self) -> None:
        game = MultiplayerWordleGame(channel_id=1, roster=[self.p1, self.p2], target_word="MUSIC")

        for _ in range(5):
            game.process_guess(game.current_player, "AUDIO")
            self.assertFalse(game.is_over)

        # 6th attempt
        game.process_guess(game.current_player, "AUDIO")
        self.assertTrue(game.is_over)
        self.assertFalse(game.won)

    def test_embed_rendering_with_fifo_queue(self) -> None:
        mock_cog = MagicMock()
        game = MultiplayerWordleGame(channel_id=1, roster=[self.p1, self.p2], target_word="MUSIC")
        view = WordleGameView(game=game, cog=mock_cog)

        embed = view.render_embed()
        self.assertIn("First-In, First-Out", embed.description)
        self.assertIn("Current Turn:", embed.description)
        self.assertIn("Next in Line:", embed.description)
        self.assertEqual(embed.color.value, 0xBAE1FF)  # Soft pastel blue for active game


if __name__ == "__main__":
    unittest.main()
