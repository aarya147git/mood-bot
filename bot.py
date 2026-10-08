"""
Main Application Entry Point (bot.py)

This module initializes the Discord Client, configures Gateway Intents,
dynamically loads modular Cogs, synchronizes application slash commands,
and establishes global error boundaries.

Academic Design Highlights:
- Object-Oriented Client: Subclasses `commands.Bot` rather than using a global instance,
  encapsulating lifecycle hooks and extension loading cleanly.
- Least-Privilege Gateway Intents: Only requests standard intents (`guilds`),
  avoiding unnecessary privileged intents (e.g. Message Content or Server Members)
  since slash commands and button interactions operate via Discord interaction webhooks.
- Dynamic Extension Loader: Iterates over the `cogs/` package, supporting plug-and-play modularity.
- Two-Tier Command Synchronization:
  Supports immediate guild-level syncing for rapid local development,
  alongside standard global registration for production deployments.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root directory is present in sys.path for robust execution from any CWD
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.quiz_style import create_error_embed

# Configure standard logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AuraTunes")

# List of Cog extensions to load at startup
INITIAL_EXTENSIONS: list[str] = [
    "cogs.mood_cog",
    "cogs.music_cog",
    "cogs.focus_cog",
    "cogs.wordle_cog",
]


class AuraTunesBot(commands.Bot):
    """Custom Discord Bot client managing lifecycle hooks and slash commands."""

    def __init__(self) -> None:
        # Gateway intents: slash commands, guild presence, and voice state tracking
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True  # Required for voice channel music streaming
        intents.message_content = True  # Required for capturing in-chat Wordle guesses

        super().__init__(
            command_prefix=commands.when_mentioned,  # Primarily uses slash commands
            intents=intents,
            help_command=None,  # Disabled in favor of interactive /help or /moods
        )

    async def setup_hook(self) -> None:
        """
        Asynchronous initialization hook invoked before the bot connects to the Gateway.
        Ideal for loading extensions and syncing application command trees.
        """
        logger.info("Initializing bot extensions...")
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info("Successfully loaded extension: %s", extension)
            except Exception as exc:
                logger.exception("Failed to load extension %s: %s", extension, exc)

        # Synchronize slash commands
        try:
            if config.GUILD_ID:
                # Fast sync for a specific development guild (instant propagation)
                guild_obj = discord.Object(id=config.GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info("Synced %d slash commands to Dev Guild (ID: %d)", len(synced), config.GUILD_ID)
            else:
                # Global sync across all Discord servers (may take up to 1 hour to propagate)
                synced = await self.tree.sync()
                logger.info("Synced %d slash commands globally", len(synced))
        except Exception as exc:
            logger.error("Failed to sync slash commands with Discord: %s", exc)

    async def on_ready(self) -> None:
        """Lifecycle event triggered when the bot is fully connected and ready."""
        logger.info("=" * 60)
        logger.info("%s v%s is ONLINE!", config.BOT_NAME, config.BOT_VERSION)
        logger.info("Logged in as: %s (ID: %s)", self.user, self.user.id if self.user else "Unknown")
        logger.info("Connected to %d guild(s)", len(self.guilds))
        logger.info("=" * 60)

        # Set rich presence status
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="/mood • Music recommendations",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)


# ---------------------------------------------------------------------------
# Global Application Command Error Handler
# ---------------------------------------------------------------------------
bot = AuraTunesBot()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """
    Global error boundary for unhandled exceptions in slash commands.
    Ensures the user receives an informative response rather than an unresponsive interaction.
    """
    logger.error("Unhandled slash command error on %s: %s", interaction.command, error, exc_info=error)

    error_embed = create_error_embed(
        title="Command Error",
        message="An unexpected error occurred while executing this command.",
        suggestion="If the problem persists, please notify the bot administrator.",
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
    except Exception as send_err:
        logger.error("Failed to send error notification to Discord: %s", send_err)


# ---------------------------------------------------------------------------
# Main Execution Guard
# ---------------------------------------------------------------------------
def main() -> None:
    """Validates configuration and launches the bot process."""
    config.validate_config()
    logger.info("Starting %s...", config.BOT_NAME)
    try:
        bot.run(config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user. Shutting down cleanly...")
    except discord.LoginFailure:
        logger.critical(
            "Authentication failed! Invalid Discord token provided.\n"
            "Please check DISCORD_TOKEN in your .env file."
        )
        sys.exit(1)
    except Exception as exc:
        logger.critical("Fatal error running bot: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
