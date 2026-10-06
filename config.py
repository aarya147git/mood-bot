"""
Configuration Module for Mood-Based Music Recommendation Bot.

This module is responsible for loading, validating, and exposing environment
variables and bot constants. Centralizing configuration here adheres to the
Single Responsibility Principle (SRP) and ensures environment secrets are
not hardcoded across multiple files.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Explicitly resolve path to .env file relative to this module
ENV_FILE_PATH = Path(__file__).resolve().parent / ".env"
try:
    from dotenv import load_dotenv
    if ENV_FILE_PATH.exists():
        load_dotenv(dotenv_path=ENV_FILE_PATH)
    else:
        load_dotenv()
except ImportError:
    pass

# Discord Bot Authentication Token
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()

# Optional Guild ID for rapid development syncing of slash commands
_raw_guild_id = os.getenv("GUILD_ID", "").strip()
GUILD_ID: int | None = int(_raw_guild_id) if _raw_guild_id.isdigit() else None

# Bot Metadata & Defaults
BOT_NAME: str = "AuraTunes"
BOT_DESCRIPTION: str = "Personalized mood-based music recommendations powered by iTunes Search API."
BOT_VERSION: str = "1.0.0"

# External API Configuration
ITUNES_API_BASE_URL: str = "https://itunes.apple.com/search"
ITUNES_REQUEST_TIMEOUT: int = 10  # Seconds before timing out network calls


def validate_config() -> None:
    """
    Validates essential configuration parameters.

    Exits the process with an informative error message if the bot token
    is missing or still set to the default placeholder.
    """
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        sys.stderr.write(
            "\n[CONFIG ERROR] DISCORD_TOKEN is missing or not configured!\n"
            "Please create a .env file from .env.example and provide a valid Discord bot token.\n"
            "Refer to the README.md for instructions on obtaining a token from the Discord Developer Portal.\n\n"
        )
        sys.exit(1)
