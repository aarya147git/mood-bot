"""
Focus & XP Module (focus_xp.py)

Exposes the Focus & XP Gamification engine and commands at the project root.
"""

from cogs.focus_cog import ActiveSession, FocusCog, setup
from services.xp_service import calculate_level, xp_for_level, xp_service

__all__ = [
    "FocusCog",
    "ActiveSession",
    "xp_service",
    "calculate_level",
    "xp_for_level",
    "setup",
]
