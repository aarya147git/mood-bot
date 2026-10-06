"""
Interactive Wordle Game View (wordle_view.py)

Implements the Discord UI for Wordle:
- Modal for typing 5-letter guesses.
- Unicode tile grid rendering (🟩 Green, 🟨 Yellow, ⬛ Gray, ⬜ Empty).
- Letter tracker for used/available letters.
- XP reward distribution upon completion.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set
import discord

from services.xp_service import xp_service
from utils.quiz_style import create_styled_embed

logger = logging.getLogger(__name__)

# Emojis for Wordle tiles
TILE_CORRECT = "🟩"   # Letter in correct spot
TILE_PRESENT = "🟨"   # Letter in word but wrong spot
TILE_ABSENT = "⬛"    # Letter not in word
TILE_EMPTY = "⬜"     # Unguessed block


def evaluate_guess(guess: str, target: str) -> List[str]:
    """
    Evaluates a 5-letter guess against the target word according to official Wordle rules.
    Accurately accounts for duplicate letters.
    """
    guess = guess.upper()
    target = target.upper()
    result = [TILE_ABSENT] * 5
    target_counts: dict[str, int] = {}

    # First pass: identify correct positions (Green)
    for i in range(5):
        if guess[i] == target[i]:
            result[i] = TILE_CORRECT
        else:
            target_counts[target[i]] = target_counts.get(target[i], 0) + 1

    # Second pass: identify letters present in other positions (Yellow)
    for i in range(5):
        if result[i] != TILE_CORRECT:
            letter = guess[i]
            if target_counts.get(letter, 0) > 0:
                result[i] = TILE_PRESENT
                target_counts[letter] -= 1

    return result


class WordleModal(discord.ui.Modal, title="Wordle: Enter Your Guess"):
    """Discord popup modal accepting a 5-letter word input."""

    guess_input = discord.ui.TextInput(
        label="5-Letter Word",
        placeholder="e.g. FOCUS, CHILL, MUSIC",
        min_length=5,
        max_length=5,
        required=True,
    )

    def __init__(self, game_view: "WordleGameView") -> None:
        super().__init__()
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guess = str(self.guess_input.value).strip().upper()
        if not guess.isalpha() or len(guess) != 5:
            await interaction.response.send_message(
                "❌ Please enter a valid 5-letter alphabetic word.",
                ephemeral=True,
            )
            return

        await self.game_view.process_guess(interaction, guess)


class WordleGameView(discord.ui.View):
    """Interactive Discord UI View managing the 6-attempt Wordle session."""

    def __init__(self, author: discord.User | discord.Member, target_word: str, timeout: float = 300.0) -> None:
        super().__init__(timeout=timeout)
        self.author = author
        self.target_word = target_word.upper()
        self.guesses: List[str] = []
        self.evaluations: List[List[str]] = []
        self.is_over: bool = False
        self.won: bool = False

        # Letter tracker sets
        self.correct_letters: Set[str] = set()
        self.present_letters: Set[str] = set()
        self.absent_letters: Set[str] = set()

        self._build_buttons()

    def _build_buttons(self) -> None:
        self.clear_items()
        if not self.is_over:
            guess_btn = discord.ui.Button(
                label=f"Guess ({len(self.guesses)}/6)",
                style=discord.ButtonStyle.primary,
                emoji="📝",
                custom_id="wordle_guess_btn",
            )
            guess_btn.callback = self._on_guess_clicked
            self.add_item(guess_btn)
        else:
            play_again_btn = discord.ui.Button(
                label="Play Again (/wordle)",
                style=discord.ButtonStyle.secondary,
                emoji="🔄",
                custom_id="wordle_restart_btn",
            )
            play_again_btn.callback = self._on_restart_clicked
            self.add_item(play_again_btn)

    async def _on_guess_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This Wordle game was started by someone else. Type `/wordle` to start your own!",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(WordleModal(self))

    async def _on_restart_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Start your own game with `/wordle`!", ephemeral=True)
            return

        from cogs.wordle_cog import get_random_word
        new_target = get_random_word()
        new_game = WordleGameView(author=self.author, target_word=new_target)
        embed = new_game.render_embed()
        await interaction.response.send_message(embed=embed, view=new_game)

    async def process_guess(self, interaction: discord.Interaction, guess: str) -> None:
        """Processes a validated guess, computes tile states, and checks game end."""
        self.guesses.append(guess)
        tiles = evaluate_guess(guess, self.target_word)
        self.evaluations.append(tiles)

        # Update keyboard letter trackers
        for i, letter in enumerate(guess):
            tile = tiles[i]
            if tile == TILE_CORRECT:
                self.correct_letters.add(letter)
                self.present_letters.discard(letter)
            elif tile == TILE_PRESENT:
                if letter not in self.correct_letters:
                    self.present_letters.add(letter)
            else:
                if letter not in self.correct_letters and letter not in self.present_letters:
                    self.absent_letters.add(letter)

        # Check win or loss conditions
        xp_msg = ""
        if guess == self.target_word:
            self.is_over = True
            self.won = True
            xp_earned, leveled_up, new_level = xp_service.record_wordle_game(
                user_id=self.author.id,
                won=True,
                attempts=len(self.guesses),
            )
            xp_msg = f"\n\n🎉 **You earned +{xp_earned} XP!**"
            if leveled_up:
                xp_msg += f" 🌟 **LEVEL UP! You are now Level {new_level}!**"
        elif len(self.guesses) >= 6:
            self.is_over = True
            self.won = False
            xp_service.record_wordle_game(user_id=self.author.id, won=False, attempts=6)

        self._build_buttons()
        embed = self.render_embed(extra_footer=xp_msg)
        await interaction.response.edit_message(embed=embed, view=self)

    def render_embed(self, extra_footer: str = "") -> discord.Embed:
        """Constructs the Wordle game board embed with emojis and letter tracking."""
        grid_lines = []
        for i in range(6):
            if i < len(self.guesses):
                tile_row = " ".join(self.evaluations[i])
                word_spaced = " ".join(list(self.guesses[i]))
                grid_lines.append(f"{tile_row}   `{word_spaced}`")
            else:
                grid_lines.append(f"{TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY}")

        board_str = "\n".join(grid_lines)

        # Keyboard status breakdown
        correct_str = " ".join(sorted(self.correct_letters)) or "None"
        present_str = " ".join(sorted(self.present_letters)) or "None"
        absent_str = " ".join(sorted(self.absent_letters)) or "None"

        description = (
            f"**Player:** {self.author.mention}\n\n"
            f"{board_str}\n\n"
            f"🟩 **Correct:** `{correct_str}`\n"
            f"🟨 **In Word:** `{present_str}`\n"
            f"⬛ **Missed:** `{absent_str}`"
        )

        if self.is_over:
            if self.won:
                title = f"🏆 Wordle Solved in {len(self.guesses)}/6!"
                color = discord.Color.green()
                description += f"\n\n✨ Awesome job! The word was **{self.target_word}**!{extra_footer}"
            else:
                title = "💀 Game Over!"
                color = discord.Color.red()
                description += f"\n\nBetter luck next time! The word was **{self.target_word}**."
        else:
            title = f"🎯 Wordle • Attempt {len(self.guesses) + 1} of 6"
            color = discord.Color(0xBAE1FF)  # Soft pastel blue

        embed = create_styled_embed(
            title=title,
            description=description,
            color=color,
            author=self.author,
            footer_text="AuraTunes • Wordle Mini-Game",
        )
        return embed

    async def on_timeout(self) -> None:
        """Disables buttons upon timeout."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
