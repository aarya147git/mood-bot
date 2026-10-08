"""
Multiplayer Wordle Mini-Game Cog (wordle_cog.py)

Provides slash commands and message listeners for playing multiplayer Wordle inside Discord:
- `/wordle`: Launches a multiplayer 5-letter word guessing game with optional player invites.
- `/wordle_stats`: Displays player's Wordle stats and win records.
- `on_message`: Captures valid 5-letter word guesses typed in chat by allowed turn-queue players.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Optional
import discord
from discord import app_commands
from discord.ext import commands

from services.xp_service import xp_service
from ui.wordle_view import MultiplayerWordleGame, WordleGameView
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
    """Interactive Multiplayer Wordle puzzle game with FIFO turn queue rotation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Dictionary mapping channel_id -> active MultiplayerWordleGame session
        self.active_games: Dict[int, MultiplayerWordleGame] = {}

    @app_commands.command(
        name="wordle",
        description="Launch a multiplayer Wordle game in this channel with up to 5 friends!",
    )
    @app_commands.describe(
        player1="Optional 2nd player to invite",
        player2="Optional 3rd player to invite",
        player3="Optional 4th player to invite",
        player4="Optional 5th player to invite",
        player5="Optional 6th player to invite",
    )
    async def wordle(
        self,
        interaction: discord.Interaction,
        player1: Optional[discord.User] = None,
        player2: Optional[discord.User] = None,
        player3: Optional[discord.User] = None,
        player4: Optional[discord.User] = None,
        player5: Optional[discord.User] = None,
    ) -> None:
        """Starts a fresh multiplayer Wordle game in the current text channel."""
        channel_id = interaction.channel_id
        if channel_id in self.active_games:
            active_game = self.active_games[channel_id]
            await interaction.response.send_message(
                f"❌ A Wordle game is already active in this channel! "
                f"Current turn: {active_game.current_player.mention}. Please finish it before starting a new one.",
                ephemeral=True,
            )
            return

        # Compile roster starting with the command author
        raw_invites = [interaction.user, player1, player2, player3, player4, player5]
        roster: list[discord.User | discord.Member] = []
        seen_ids: set[int] = set()

        for p in raw_invites:
            if p is not None and not p.bot and p.id not in seen_ids:
                roster.append(p)
                seen_ids.add(p.id)

        target_word = get_random_word()
        game = MultiplayerWordleGame(channel_id=channel_id, roster=roster, target_word=target_word)
        self.active_games[channel_id] = game

        view = WordleGameView(game=game, cog=self)
        embed = view.render_embed()

        await interaction.response.send_message(embed=embed, view=view)
        game.game_message = await interaction.original_response()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Message listener capturing 5-letter word guesses typed directly into text channels.
        Enforces roster restriction and FIFO turn queue order.
        """
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        if channel_id not in self.active_games:
            return

        game = self.active_games[channel_id]
        content = message.content.strip().upper()

        # Ignore if not a valid 5-letter alphabetic word
        if len(content) != 5 or not content.isalpha():
            return

        # Restrict interactions exclusively to players in the lobby roster
        if not game.is_player_in_roster(message.author.id):
            return

        # Enforce strict FIFO turn rotation system
        if not game.is_current_turn(message.author.id):
            return

        # Process valid guess
        await self.process_game_guess(message.channel, game, message.author, content, guess_message=message)

    async def process_game_guess(
        self,
        channel: discord.abc.Messageable,
        game: MultiplayerWordleGame,
        player: discord.User | discord.Member,
        guess: str,
        interaction: Optional[discord.Interaction] = None,
        guess_message: Optional[discord.Message] = None,
    ) -> None:
        """
        Evaluates a guess, advances turn queue, checks win/loss, distributes XP, and cleans up lifecycle.
        """
        tiles = game.process_guess(player, guess)

        extra_footer = ""
        if game.is_over:
            # Lifecycle cleanup: delete session from active_games dictionary
            self.active_games.pop(game.channel_id, None)

            # Record game results and distribute XP to participants
            for member in game.roster:
                xp_earned, leveled_up, new_level = xp_service.record_wordle_game(
                    user_id=member.id,
                    won=game.won,
                    attempts=len(game.guesses),
                )
                if game.won and member.id == player.id:
                    extra_footer += f"\n🎉 **{player.display_name}** earned +{xp_earned} XP!"
                    if leveled_up:
                        extra_footer += f" 🌟 **LEVEL UP! Level {new_level}!**"

        view = WordleGameView(game=game, cog=self)
        embed = view.render_embed(extra_footer=extra_footer)

        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=view)
        elif game.game_message:
            try:
                await game.game_message.edit(embed=embed, view=view)
            except discord.HTTPException:
                pass

        if guess_message:
            try:
                reaction = "🟩" if game.won else ("💀" if game.is_over else "🎯")
                await guess_message.add_reaction(reaction)
            except discord.HTTPException:
                pass

    @app_commands.command(
        name="wordle_stats",
        description="View your Wordle win rate, games played, and puzzle statistics.",
    )
    async def wordle_stats(self, interaction: discord.Interaction) -> None:
        """Displays user's Wordle performance statistics."""
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
