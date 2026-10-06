"""
Wordle Mini-Game Cog (wordle_cog.py)

Provides slash commands for playing Wordle inside Discord:
- `/wordle`: Launches an interactive 5-letter word guessing game.
- `/wordle_stats`: Displays player's Wordle stats and win records.
"""

from __future__ import annotations

import logging
import random
import discord
from discord import app_commands
from discord.ext import commands

from services.xp_service import xp_service
from ui.wordle_view import WordleGameView
from utils.quiz_style import create_styled_embed

logger = logging.getLogger(__name__)

# Curated list of engaging 5-letter words
WORD_BANK = [
    "FOCUS", "CHILL", "MUSIC", "PIANO", "VIBES", "TRACK", "SOUND", "BEATS",
    "ALBUM", "TEMPO", "LYRIC", "DANCE", "RADIO", "AUDIO", "DREAM", "LIGHT",
    "SHINE", "PEACE", "BRAVE", "SMART", "HEART", "OCEAN", "STORM", "EARTH",
    "FLAME", "CLOUD", "NIGHT", "MAGIC", "POWER", "SOLAR", "LUNAR", "WATER",
    "CRANE", "SLATE", "ROBOT", "GREEN", "STUDY", "LEARN", "QUEST", "LAUGH",
    "SWEET", "BLOOM", "FRESH", "GLOWS", "SPARK", "VIVID", "ZENITH", "NOBLE",
]


def get_random_word() -> str:
    """Returns a randomly selected 5-letter target word."""
    return random.choice(WORD_BANK).upper()


class WordleCog(commands.Cog, name="Wordle Mini-Game"):
    """Interactive Wordle puzzle game and stats tracking."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="wordle",
        description="Play a 5-letter Wordle puzzle and earn XP for your profile!",
    )
    async def wordle(self, interaction: discord.Interaction) -> None:
        """Starts a fresh 6-guess Wordle game session."""
        target_word = get_random_word()
        game_view = WordleGameView(author=interaction.user, target_word=target_word)
        embed = game_view.render_embed()

        await interaction.response.send_message(embed=embed, view=game_view)

    @app_commands.command(
        name="wordle_stats",
        description="View your Wordle win rate, games played, and puzzle statistics.",
    )
    async def wordle_stats(self, interaction: discord.Interaction) -> None:
        """Displays user's Wordle performance."""
        profile = xp_service.get_user_profile(interaction.user.id)
        played = profile["wordle_played"]
        wins = profile["wordle_wins"]
        win_rate = int((wins / max(1, played)) * 100) if played > 0 else 0

        description = (
            f"**Player:** {interaction.user.mention}\n\n"
            f"🎮 **Games Played:** `{played}`\n"
            f"🏆 **Games Won:** `{wins}`\n"
            f"📈 **Win Rate:** `{win_rate}%`\n"
            f"⭐ **Current Level:** `Level {profile['level']}`"
        )

        embed = create_styled_embed(
            title="📊 Wordle Player Statistics",
            description=description,
            color=discord.Color.gold(),
            author=interaction.user,
            footer_text="AuraTunes • Wordle Gamification",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Standard extension setup hook required by discord.py."""
    await bot.add_cog(WordleCog(bot))
