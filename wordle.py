"""
Wordle Module (wordle.py)

Exposes the Wordle mini-game, multiplayer state management, and puzzle views at the project root.
"""

from cogs.wordle_cog import WORD_BANK, WordleCog, get_random_word, setup
from ui.wordle_view import MultiplayerWordleGame, WordleGameView, evaluate_guess

__all__ = [
    "WordleCog",
    "WordleGameView",
    "MultiplayerWordleGame",
    "WORD_BANK",
    "get_random_word",
    "evaluate_guess",
    "setup",
]
