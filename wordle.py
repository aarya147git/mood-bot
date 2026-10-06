"""
Wordle Module (wordle.py)

Exposes the Wordle mini-game and puzzle views at the project root.
"""

from cogs.wordle_cog import WORD_BANK, WordleCog, get_random_word, setup
from ui.wordle_view import WordleGameView, evaluate_guess

__all__ = [
    "WordleCog",
    "WordleGameView",
    "WORD_BANK",
    "get_random_word",
    "evaluate_guess",
    "setup",
]
