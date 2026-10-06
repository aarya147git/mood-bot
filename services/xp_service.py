"""
XP & Gamification Service (xp_service.py)

Manages user progression, focus session tracking, Wordle win tallies, and local persistence.
Calculates levels, daily focus streaks, and server leaderboards.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AuraTunes.XPService")

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "user_stats.json"


def calculate_level(xp: int) -> int:
    """Calculates level based on quadratic scaling: Level N requires (N - 1)^2 * 100 XP."""
    if xp <= 0:
        return 1
    return int(math.sqrt(xp / 100)) + 1


def xp_for_level(level: int) -> int:
    """Returns the total XP required to reach a specific level."""
    if level <= 1:
        return 0
    return (level - 1) ** 2 * 100


class XPService:
    """Thread-safe persistent gamification engine."""

    def __init__(self, data_path: Path = DATA_FILE) -> None:
        self.data_path = data_path
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Loads user stats from disk if available."""
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as exc:
                logger.error("Failed to load user stats from %s: %s", self.data_path, exc)
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Atomically persists user stats to disk."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.data_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(temp_path, self.data_path)
        except Exception as exc:
            logger.error("Failed to persist user stats to %s: %s", self.data_path, exc)

    def _get_or_create(self, user_id: int) -> Dict[str, Any]:
        uid = str(user_id)
        if uid not in self._data:
            self._data[uid] = {
                "xp": 0,
                "focus_minutes": 0,
                "focus_sessions": 0,
                "focus_streak": 0,
                "last_focus_date": None,
                "wordle_wins": 0,
                "wordle_played": 0,
            }
        return self._data[uid]

    def add_xp(self, user_id: int, amount: int) -> Tuple[int, bool, int]:
        """
        Grants XP to a user.

        Returns:
            (new_xp, leveled_up, new_level)
        """
        user = self._get_or_create(user_id)
        old_level = calculate_level(user["xp"])
        user["xp"] = max(0, user["xp"] + amount)
        new_level = calculate_level(user["xp"])
        leveled_up = new_level > old_level
        self._save()
        return user["xp"], leveled_up, new_level

    def record_focus_session(self, user_id: int, minutes: int) -> Tuple[int, bool, int, int]:
        """
        Records a completed focus session, updates streak, and awards XP (10 XP per minute).

        Returns:
            (xp_earned, leveled_up, new_level, current_streak)
        """
        user = self._get_or_create(user_id)
        xp_earned = minutes * 10
        today_str = date.today().isoformat()
        last_date_str = user.get("last_focus_date")

        # Calculate daily streak
        if last_date_str:
            last_date = date.fromisoformat(last_date_str)
            if last_date == date.today():
                pass  # Already studied today, maintain streak
            elif last_date == date.today() - timedelta(days=1):
                user["focus_streak"] = user.get("focus_streak", 0) + 1
            else:
                user["focus_streak"] = 1
        else:
            user["focus_streak"] = 1

        user["last_focus_date"] = today_str
        user["focus_minutes"] = user.get("focus_minutes", 0) + minutes
        user["focus_sessions"] = user.get("focus_sessions", 0) + 1

        _, leveled_up, new_level = self.add_xp(user_id, xp_earned)
        return xp_earned, leveled_up, new_level, user["focus_streak"]

    def record_wordle_game(self, user_id: int, won: bool, attempts: int) -> Tuple[int, bool, int]:
        """
        Records a Wordle game result and awards bonus XP for winning.

        Returns:
            (xp_earned, leveled_up, new_level)
        """
        user = self._get_or_create(user_id)
        user["wordle_played"] = user.get("wordle_played", 0) + 1

        xp_earned = 0
        if won:
            user["wordle_wins"] = user.get("wordle_wins", 0) + 1
            # Attempts 1-6 award scaled XP: 150, 120, 100, 80, 60, 40
            xp_scale = {1: 150, 2: 120, 3: 100, 4: 80, 5: 60, 6: 40}
            xp_earned = xp_scale.get(attempts, 40)
            _, leveled_up, new_level = self.add_xp(user_id, xp_earned)
        else:
            leveled_up = False
            new_level = calculate_level(user["xp"])
            self._save()

        return xp_earned, leveled_up, new_level

    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Retrieves formatted statistics and level progress for a user."""
        user = self._get_or_create(user_id)
        xp = user["xp"]
        level = calculate_level(xp)
        current_level_base = xp_for_level(level)
        next_level_target = xp_for_level(level + 1)
        xp_in_level = xp - current_level_base
        xp_needed = next_level_target - current_level_base
        progress_pct = min(100, int((xp_in_level / max(1, xp_needed)) * 100))

        return {
            "user_id": user_id,
            "xp": xp,
            "level": level,
            "progress_pct": progress_pct,
            "xp_in_level": xp_in_level,
            "xp_needed": xp_needed,
            "focus_minutes": user.get("focus_minutes", 0),
            "focus_sessions": user.get("focus_sessions", 0),
            "focus_streak": user.get("focus_streak", 0),
            "wordle_wins": user.get("wordle_wins", 0),
            "wordle_played": user.get("wordle_played", 0),
        }

    def get_top_users(self, limit: int = 10) -> List[Tuple[int, Dict[str, Any]]]:
        """Returns the top users sorted by total XP."""
        sorted_users = sorted(
            self._data.items(),
            key=lambda item: item[1].get("xp", 0),
            reverse=True,
        )
        return [(int(uid), data) for uid, data in sorted_users[:limit]]


# Global singleton instance
xp_service = XPService()
