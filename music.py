"""
Music Module Wrapper (music.py)

Exposes the MusicCog and setup hooks from cogs/music_cog.py at the project root
for convenient direct inspection and imports.
"""

from cogs.music_cog import (
    GENRE_CHOICES,
    MOOD_CHOICES,
    MusicCog,
    setup,
)

__all__ = ["MusicCog", "setup", "MOOD_CHOICES", "GENRE_CHOICES"]
