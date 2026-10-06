"""
Mood Interaction Cog (mood_cog.py)

This Cog manages mood-related slash commands for the Discord bot:
1. `/mood`: Launches the interactive button-based MCQ to determine the user's
   current emotional state and returns curated song recommendations.
2. `/moods`: Displays a reference catalog explaining each supported mood profile
   and its musical pairings.

In discord.py, Cogs group related commands, listeners, and state into modular classes.
This promotes the Open/Closed Principle (OCP), allowing features to be extended
without mutating core bot client logic.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ui.mood_quiz_view import MoodQuizView
from utils.quiz_style import create_styled_embed, get_next_pastel_color


class MoodCog(commands.Cog, name="Mood Questionnaire"):
    """Handles mood assessment commands and interactive quiz sessions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="mood",
        description="Take a quick 2-step button quiz to get music tailored to your vibe.",
    )
    async def mood(self, interaction: discord.Interaction) -> None:
        """
        Launches the interactive button questionnaire.
        Presents Step 1 of the quiz with live progress tracking.
        """
        quiz_view = MoodQuizView(author=interaction.user)
        initial_embed = quiz_view.render_step_embed()

        # Send initial quiz message with interactive buttons attached
        await interaction.response.send_message(embed=initial_embed, view=quiz_view)

    @app_commands.command(
        name="moods",
        description="View all supported mood archetypes and their musical profiles.",
    )
    async def moods_catalog(self, interaction: discord.Interaction) -> None:
        """
        Displays educational metadata on the mood-to-music heuristic mapping.
        """
        description = (
            "AuraTunes pairs emotional states with specific musical attributes:\n\n"
            "⚡ **Energetic**\n"
            "> *Genres:* Dance Pop, Electronic, Upbeat Rock, Synthwave\n"
            "> *Vibe:* High-BPM rhythms, driving percussion, uplifting hooks\n\n"
            "🌿 **Chill & Relaxed**\n"
            "> *Genres:* Lo-fi Hip Hop, Downtempo, Acoustic Fingerstyle, Coffeehouse\n"
            "> *Vibe:* Warm tones, mellow basslines, soothing organic instruments\n\n"
            "🌧️ **Sad & Reflective**\n"
            "> *Genres:* Melancholic Ballads, Soft Piano, Rainy Lo-fi, Indie Folk\n"
            "> *Vibe:* Emotional chord progressions, gentle vocals, introspective pacing\n\n"
            "🧠 **Deep Focus**\n"
            "> *Genres:* Ambient Drone, Binaural Soundscapes, Classical Guitar, Instrumental Post-Rock\n"
            "> *Vibe:* Low-distraction flow, steady pulse, minimal lyrical intrusion"
        )

        embed = create_styled_embed(
            title="📖 Supported Mood Archetypes",
            description=description,
            color=get_next_pastel_color(),
            footer_text="AuraTunes • Mood Heuristics Catalog",
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="commands",
        description="Shows all available bot commands grouped by category.",
    )
    async def commands_list(self, interaction: discord.Interaction) -> None:
        """
        Dynamically fetches all registered slash commands from the bot's command tree,
        groups them by their parent Cog category, and displays a formatted embed
        with the total command count.
        """
        # Category icons keyed by Cog name
        CATEGORY_ICONS: dict[str, str] = {
            "Mood Questionnaire": "🎭",
            "Music": "🎵",
            "Focus & XP": "🧠",
            "Wordle": "🟩",
        }

        # Build a mapping of category -> list of (name, description) pairs
        categories: dict[str, list[tuple[str, str]]] = {}
        total_count = 0

        for cog_name, cog in self.bot.cogs.items():
            cog_commands = [
                cmd for cmd in self.bot.tree.get_commands()
                if isinstance(cmd, app_commands.Command) and cmd.binding is cog
            ]
            if cog_commands:
                categories[cog_name] = [
                    (cmd.name, cmd.description) for cmd in cog_commands
                ]
                total_count += len(cog_commands)

        # Build embed description
        lines: list[str] = [
            f"AuraTunes has **{total_count} slash commands** ready to use!\n"
        ]

        for cog_name, cmds in categories.items():
            icon = CATEGORY_ICONS.get(cog_name, "📌")
            lines.append(f"{icon} **{cog_name}**")
            for cmd_name, cmd_desc in cmds:
                lines.append(f"> `/{cmd_name}` — {cmd_desc}")
            lines.append("")  # Blank spacer between categories

        description = "\n".join(lines).strip()

        embed = create_styled_embed(
            title="📋 All Available Commands",
            description=description,
            color=get_next_pastel_color(),
            footer_text=f"AuraTunes • {total_count} commands total",
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Standard extension setup function required by discord.py."""
    await bot.add_cog(MoodCog(bot))
