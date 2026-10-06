"""
Shared Style Helper Module (quiz_style.py)

This module provides reusable UI formatting utilities across the bot:
1. Rotating pastel color palette and mood-to-color mappings.
2. Visual Unicode progress bar generator for multi-step interactive quizzes.
3. Factory functions for building standardized, aesthetically pleasing Discord Embeds.

Separating styling from business logic promotes the DRY (Don't Repeat Yourself) principle
and guarantees a consistent, cohesive visual identity for all user-facing interactions.
"""

from __future__ import annotations

import datetime
from itertools import cycle
from typing import Sequence
import discord

# ---------------------------------------------------------------------------
# Pastel Color Palette
# ---------------------------------------------------------------------------
# Hex codes chosen for soft, modern, high-contrast readability in Discord's dark/light modes.
PASTEL_PALETTE_HEX: list[int] = [
    0xFFB3BA,  # Pastel Coral / Pink
    0xFFDFBA,  # Pastel Peach / Apricot
    0xFFFFBA,  # Pastel Buttercup / Soft Yellow
    0xBAFFC9,  # Pastel Mint / Seafoam
    0xBAE1FF,  # Pastel Sky Blue
    0xD4BBFF,  # Pastel Lavender / Periwinkle
    0xF2C6DE,  # Pastel Rose
    0xC1E1C1,  # Pastel Sage Green
]

# Infinite cyclic iterator over the pastel colors
_color_cycle = cycle(PASTEL_PALETTE_HEX)


def get_next_pastel_color() -> discord.Color:
    """
    Returns the next pastel color in the rotating sequence as a discord.Color.
    Thread-safe and deterministic across bot sessions.
    """
    return discord.Color(next(_color_cycle))


# Direct semantic mappings for mood archetypes
MOOD_COLOR_MAP: dict[str, int] = {
    "energetic": 0xFF9E80,   # Vibrant Pastel Orange
    "chill": 0x80DEEA,       # Soft Aquamarine
    "sad": 0x9FA8DA,         # Melancholic Lavender-Indigo
    "focused": 0xA5D6A7,     # Serene Sage Mint
    "romantic": 0xF48FB1,    # Blush Rose
    "adventurous": 0xFFE082, # Warm Sunlight
}


def get_mood_color(mood_key: str) -> discord.Color:
    """
    Returns a distinct pastel discord.Color associated with a given mood keyword.
    Falls back to a rotating pastel color if the mood key is not mapped.
    """
    normalized_key = mood_key.strip().lower()
    hex_code = MOOD_COLOR_MAP.get(normalized_key)
    if hex_code is not None:
        return discord.Color(hex_code)
    return get_next_pastel_color()


# ---------------------------------------------------------------------------
# Progress Bar Generator
# ---------------------------------------------------------------------------
def create_progress_bar(
    current_step: int,
    total_steps: int,
    bar_length: int = 10,
    filled_char: str = "▰",
    empty_char: str = "▱",
) -> str:
    """
    Generates a Unicode visual progress bar string for multi-step quizzes.

    Example output for step 1 of 2 (length 10):
        `[▰▰▰▰▰▱▱▱▱▱] Step 1 of 2 (50%)`

    Args:
        current_step: 1-indexed current step (e.g., 1 for first question).
        total_steps: Total number of steps in the questionnaire.
        bar_length: Total number of character blocks in the bar (default: 10).
        filled_char: Glyph representing completed progress.
        empty_char: Glyph representing remaining progress.

    Returns:
        Formatted string containing the bar, step counter, and percentage.
    """
    # Guard against invalid inputs (e.g. division by zero or negative values)
    if total_steps <= 0:
        total_steps = 1
    safe_step = max(0, min(current_step, total_steps))

    progress_fraction = safe_step / total_steps
    filled_count = round(progress_fraction * bar_length)
    empty_count = bar_length - filled_count

    bar = (filled_char * filled_count) + (empty_char * empty_count)
    percentage = int(progress_fraction * 100)

    return f"**`[{bar}]`** Step {safe_step} of {total_steps} ({percentage}%)"


# ---------------------------------------------------------------------------
# Standardized Embed Factory
# ---------------------------------------------------------------------------
def create_styled_embed(
    title: str,
    description: str,
    color: discord.Color | None = None,
    author: discord.User | discord.Member | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
    fields: Sequence[tuple[str, str, bool]] | None = None,
    footer_text: str = "AuraTunes • Music for your mood",
) -> discord.Embed:
    """
    Constructs a standardized Discord Embed with unified styling, timestamps,
    and metadata.

    Args:
        title: Title of the embed.
        description: Primary markdown content body.
        color: Discord Color instance; defaults to the next rotating pastel color.
        author: Optional Discord User/Member to show in the embed author header.
        thumbnail_url: Optional URL to display as a top-right thumbnail.
        image_url: Optional URL to display as the main embed image.
        fields: Optional list of (field_name, field_value, is_inline) tuples.
        footer_text: Custom footer string.

    Returns:
        A formatted discord.Embed object.
    """
    chosen_color = color or get_next_pastel_color()

    embed = discord.Embed(
        title=title,
        description=description,
        color=chosen_color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    if author is not None:
        avatar_url = author.display_avatar.url if hasattr(author, "display_avatar") else None
        embed.set_author(name=f"{author.display_name}'s Mood Quiz", icon_url=avatar_url)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if image_url:
        embed.set_image(url=image_url)

    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

    embed.set_footer(text=footer_text)
    return embed


def create_error_embed(
    title: str,
    message: str,
    suggestion: str | None = None,
) -> discord.Embed:
    """
    Constructs a user-friendly error/warning embed.
    Uses a soft salmon/rose tone to remain consistent with pastel aesthetics
    while signaling an issue clearly.
    """
    error_color = discord.Color(0xFF8A80)  # Soft Pastel Coral / Red
    description = f"{message}"
    if suggestion:
        description += f"\n\n💡 **Suggestion:** {suggestion}"

    embed = discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=error_color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text="AuraTunes • Error Handler")
    return embed
