"""
Interactive Multiplayer Wordle Game View (wordle_view.py)

Implements the Discord UI & Game State for Wordle:
- Multiplayer lobby support (up to 6 players per session).
- First-In, First-Out (FIFO) queue turn rotation system.
- Message listener and button Modal guess input methods.
- Unicode tile grid rendering (🟩 Green, 🟨 Yellow, ⬛ Gray, ⬜ Empty).
- Pastel color themes for active, victory, and game-over embeds.
- Letter tracker for used/available letters.
- XP reward distribution upon completion.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, List, Optional, Set
import discord

from services.xp_service import xp_service
from utils.quiz_style import create_styled_embed

if TYPE_CHECKING:
    from cogs.wordle_cog import WordleCog

logger = logging.getLogger(__name__)

# Emojis for Wordle tiles
TILE_CORRECT = "🟩"   # Letter in correct spot
TILE_PRESENT = "🟨"   # Letter in word but wrong spot
TILE_ABSENT = "⬛"    # Letter not in word
TILE_EMPTY = "⬜"     # Unguessed block

# Pastel Color Palette
COLOR_ACTIVE = discord.Color(0xBAE1FF)   # Pastel Blue
COLOR_VICTORY = discord.Color(0xB5EAD7)  # Pastel Soft Green
COLOR_GAMEOVER = discord.Color(0xFF9AA2) # Pastel Soft Red


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


class MultiplayerWordleGame:
    """
    In-memory state management for a multiplayer Wordle game in a single channel.
    Manages player roster, FIFO turn queue, board evaluations, and win/loss states.
    """

    def __init__(
        self,
        channel_id: int,
        roster: List[discord.User | discord.Member],
        target_word: str,
    ) -> None:
        self.channel_id = channel_id

        # Deduplicate roster while preserving initial order
        unique_roster: List[discord.User | discord.Member] = []
        seen_ids: set[int] = set()
        for p in roster:
            if p.id not in seen_ids:
                unique_roster.append(p)
                seen_ids.add(p.id)

        self.roster: List[discord.User | discord.Member] = unique_roster
        self.turn_queue: deque[discord.User | discord.Member] = deque(self.roster)
        self.target_word: str = target_word.upper()
        self.guesses: List[tuple[discord.User | discord.Member, str]] = []  # (player, guess)
        self.evaluations: List[List[str]] = []
        self.is_over: bool = False
        self.won: bool = False

        # Letter tracker sets
        self.correct_letters: Set[str] = set()
        self.present_letters: Set[str] = set()
        self.absent_letters: Set[str] = set()

        # Discord message reference for updating live board
        self.game_message: Optional[discord.Message] = None

    @property
    def current_player(self) -> discord.User | discord.Member:
        """Returns the player currently at the front of the FIFO turn queue."""
        return self.turn_queue[0]

    @property
    def next_player(self) -> discord.User | discord.Member:
        """Returns the player next in line in the FIFO turn queue."""
        if len(self.turn_queue) > 1:
            return self.turn_queue[1]
        return self.turn_queue[0]

    def is_player_in_roster(self, user_id: int) -> bool:
        """Checks if a user ID is part of the starting lobby roster."""
        return any(p.id == user_id for p in self.roster)

    def is_current_turn(self, user_id: int) -> bool:
        """Checks if the given user ID is currently at the front of the turn queue."""
        return self.current_player.id == user_id

    def advance_turn(self) -> None:
        """Rotates the FIFO turn queue to the next player in line."""
        if len(self.turn_queue) > 1:
            self.turn_queue.rotate(-1)

    def process_guess(self, player: discord.User | discord.Member, guess: str) -> List[str]:
        """
        Processes a guess, updates board evaluations, updates letter trackers, and returns tiles.
        """
        guess = guess.upper()
        tiles = evaluate_guess(guess, self.target_word)
        self.guesses.append((player, guess))
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

        # Check game end
        if guess == self.target_word:
            self.is_over = True
            self.won = True
        elif len(self.guesses) >= 6:
            self.is_over = True
            self.won = False
        else:
            self.advance_turn()

        return tiles


class WordleModal(discord.ui.Modal, title="Wordle: Submit Your Guess"):
    """Discord popup modal accepting a 5-letter word input for current turn player."""

    guess_input = discord.ui.TextInput(
        label="5-Letter Word",
        placeholder="e.g. FOCUS, CHILL, MUSIC",
        min_length=5,
        max_length=5,
        required=True,
    )

    def __init__(self, game_view: "WordleGameView", cog: "WordleCog") -> None:
        super().__init__()
        self.game_view = game_view
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guess = str(self.guess_input.value).strip().upper()
        if not guess.isalpha() or len(guess) != 5:
            await interaction.response.send_message(
                "❌ Please enter a valid 5-letter alphabetic word.",
                ephemeral=True,
            )
            return

        game = self.game_view.game
        if not game.is_current_turn(interaction.user.id):
            await interaction.response.send_message(
                f"❌ It is not your turn! Current turn: {game.current_player.mention}.",
                ephemeral=True,
            )
            return

        await self.cog.process_game_guess(
            interaction.channel,
            game,
            interaction.user,
            guess,
            interaction=interaction,
        )


class WordleGameView(discord.ui.View):
    """Interactive Discord UI View managing the Wordle session controls."""

    def __init__(self, game: MultiplayerWordleGame, cog: "WordleCog", timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.cog = cog
        self._build_buttons()

    def _build_buttons(self) -> None:
        self.clear_items()
        if not self.game.is_over:
            guess_btn = discord.ui.Button(
                label=f"Guess ({len(self.game.guesses)}/6)",
                style=discord.ButtonStyle.primary,
                emoji="📝",
                custom_id="wordle_guess_btn",
            )
            guess_btn.callback = self._on_guess_clicked
            self.add_item(guess_btn)
        else:
            play_again_btn = discord.ui.Button(
                label="New Game (/wordle)",
                style=discord.ButtonStyle.secondary,
                emoji="🔄",
                custom_id="wordle_restart_btn",
            )
            play_again_btn.callback = self._on_restart_clicked
            self.add_item(play_again_btn)

    async def _on_guess_clicked(self, interaction: discord.Interaction) -> None:
        if not self.game.is_player_in_roster(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are not in this game's player roster. Start a new game with `/wordle`!",
                ephemeral=True,
            )
            return

        if not self.game.is_current_turn(interaction.user.id):
            await interaction.response.send_message(
                f"❌ It's not your turn! Current turn: {self.game.current_player.mention} (Turn Order: FIFO Queue).",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(WordleModal(self, self.cog))

    async def _on_restart_clicked(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "🎮 Start a fresh Wordle game by using the `/wordle` slash command!",
            ephemeral=True,
        )

    def render_embed(self, extra_footer: str = "") -> discord.Embed:
        """Constructs the Wordle game board embed with emojis, letter tracking, and FIFO queue details."""
        grid_lines = []
        for i in range(6):
            if i < len(self.game.guesses):
                player, guess = self.game.guesses[i]
                tiles = self.game.evaluations[i]
                tile_row = " ".join(tiles)
                word_spaced = " ".join(list(guess))
                grid_lines.append(f"{tile_row}   `{word_spaced}`  — *{player.display_name}*")
            else:
                grid_lines.append(f"{TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY} {TILE_EMPTY}")

        board_str = "\n".join(grid_lines)

        # Keyboard status breakdown
        correct_str = " ".join(sorted(self.game.correct_letters)) or "None"
        present_str = " ".join(sorted(self.game.present_letters)) or "None"
        absent_str = " ".join(sorted(self.game.absent_letters)) or "None"

        # Roster and FIFO Queue Information
        roster_mentions = ", ".join(p.mention for p in self.game.roster)
        queue_list = list(self.game.turn_queue)
        current_p = self.game.current_player
        next_p = self.game.next_player

        queue_flow = " ➔ ".join(
            f"**{p.display_name}**" + (" *(Turn)*" if idx == 0 else "")
            for idx, p in enumerate(queue_list)
        )

        description = (
            f"👥 **Lobby Roster:** {roster_mentions}\n\n"
            f"{board_str}\n\n"
            f"🟩 **Correct:** `{correct_str}`\n"
            f"🟨 **In Word:** `{present_str}`\n"
            f"⬛ **Missed:** `{absent_str}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 **Turn Order Queue (First-In, First-Out):**\n"
            f"👉 **Current Turn:** {current_p.mention}\n"
            f"⏳ **Next in Line:** {next_p.mention}\n"
            f"📋 **Queue Order:** {queue_flow}"
        )

        if self.game.is_over:
            if self.game.won:
                title = f"🏆 Wordle Solved in {len(self.game.guesses)}/6 Attempts!"
                color = COLOR_VICTORY
                description += f"\n\n🎉 **Victory!** The target word was **{self.game.target_word}**!{extra_footer}"
            else:
                title = "💀 Game Over!"
                color = COLOR_GAMEOVER
                description += f"\n\nBetter luck next time! The target word was **{self.game.target_word}**.{extra_footer}"
        else:
            title = f"🎯 Wordle • Attempt {len(self.game.guesses) + 1} of 6"
            color = COLOR_ACTIVE

        embed = create_styled_embed(
            title=title,
            description=description,
            color=color,
            author=current_p,
            footer_text="AuraTunes • Wordle Multiplayer (FIFO Queue Turn Order)",
        )
        return embed

    async def on_timeout(self) -> None:
        """Cleans up active session upon timeout and disables buttons."""
        self.cog.active_games.pop(self.game.channel_id, None)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
