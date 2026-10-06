"""
iTunes Music Search Service (itunes_service.py)

This module handles communication with the Apple iTunes Search API.
Key Characteristics:
- 100% Free: Requires no API key, authentication tokens, or credit cards.
- Asynchronous: Uses aiohttp for non-blocking network I/O, preserving the Discord bot event loop.
- Graceful Degradation: Implements custom domain exceptions for timeouts, API errors, and zero-match cases.
- Curated Mood Mapping: Transforms abstract emotional inputs into targeted musical search terms.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any
import aiohttp

from config import ITUNES_API_BASE_URL, ITUNES_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------
class MusicServiceException(Exception):
    """Base exception for all music service-related failures."""

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion or "Please try again in a moment."


class NoTracksFoundError(MusicServiceException):
    """Raised when the iTunes API returns zero matching tracks."""
    pass


class MusicAPIError(MusicServiceException):
    """Raised when the iTunes API returns an HTTP error or malformed response."""
    pass


class MusicTimeoutError(MusicServiceException):
    """Raised when the network connection to the iTunes API times out."""
    pass


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class TrackInfo:
    """
    Represents a normalized music track returned from the iTunes Search API.
    Decouples raw API payloads from Discord presentation logic.
    """
    track_id: int
    track_name: str
    artist_name: str
    collection_name: str
    track_view_url: str
    preview_url: str | None
    artwork_url: str
    primary_genre: str
    duration_ms: int
    mood_reason: str

    @property
    def formatted_duration(self) -> str:
        """Converts track duration from milliseconds to mm:ss format."""
        if not self.duration_ms or self.duration_ms <= 0:
            return "--:--"
        total_seconds = int(self.duration_ms / 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"


# ---------------------------------------------------------------------------
# Mood Profile Definitions & Query Mapping
# ---------------------------------------------------------------------------
# Maps combinations of (primary_mood, flavor_genre) to optimized search terms
# and pedagogical rationale strings explaining the pick to the user.
MOOD_PROFILES: dict[tuple[str, str], dict[str, str]] = {
    ("energetic", "pop_rock"): {
        "query": "high energy dance pop upbeat rock",
        "reason": "Picked for: energetic + upbeat rock & pop vibes",
    },
    ("energetic", "lofi"): {
        "query": "electro swing upbeat beat electronic synth",
        "reason": "Picked for: energetic + rhythmic synth groove",
    },
    ("energetic", "acoustic"): {
        "query": "fast acoustic guitar energetic folk indie",
        "reason": "Picked for: energetic + spirited acoustic rhythms",
    },
    ("energetic", "ambient"): {
        "query": "synthwave driving electronic cyberpunk",
        "reason": "Picked for: energetic + pulsating electronic drive",
    },

    ("chill", "pop_rock"): {
        "query": "mellow indie pop relaxed rock acoustic",
        "reason": "Picked for: chill + easygoing indie pop",
    },
    ("chill", "lofi"): {
        "query": "lofi hip hop chill beats relaxed study instrumental",
        "reason": "Picked for: chill + soothing lo-fi beats",
    },
    ("chill", "acoustic"): {
        "query": "gentle acoustic fingerstyle guitar coffeehouse",
        "reason": "Picked for: chill + calm acoustic warmth",
    },
    ("chill", "ambient"): {
        "query": "ambient atmospheric soundscape downtempo",
        "reason": "Picked for: chill + serene ambient textures",
    },

    ("sad", "pop_rock"): {
        "query": "melancholy indie alternative emotional rock ballad",
        "reason": "Picked for: sad + heartfelt indie emotion",
    },
    ("sad", "lofi"): {
        "query": "sad lofi beats rainy late night melancholy",
        "reason": "Picked for: sad + rainy lofi reflection",
    },
    ("sad", "acoustic"): {
        "query": "sad acoustic guitar emotional ballad soft piano",
        "reason": "Picked for: sad + tender acoustic heartache",
    },
    ("sad", "ambient"): {
        "query": "ambient cinematic melancholy emotional neoclassical",
        "reason": "Picked for: sad + contemplative ambient soundscapes",
    },

    ("focused", "pop_rock"): {
        "query": "instrumental rock progressive guitar concentration",
        "reason": "Picked for: focused + motivating instrumental rhythm",
    },
    ("focused", "lofi"): {
        "query": "lofi study beats deep focus instrumental work",
        "reason": "Picked for: focused + distraction-free lofi flow",
    },
    ("focused", "acoustic"): {
        "query": "classical guitar instrumental piano study",
        "reason": "Picked for: focused + peaceful classical clarity",
    },
    ("focused", "ambient"): {
        "query": "binaural ambient drone focus deep work study",
        "reason": "Picked for: focused + uninterrupted flow state",
    },
}

# Fallback profile for single-keyword requests
DEFAULT_MOOD_TERMS: dict[str, dict[str, str]] = {
    "energetic": {
        "query": "upbeat workout dance energetic pop",
        "reason": "Picked for: high energy & fast-paced tempo",
    },
    "chill": {
        "query": "chillout relaxed lounge peaceful",
        "reason": "Picked for: relaxed & easygoing mood",
    },
    "sad": {
        "query": "melancholy sad acoustic piano emotional",
        "reason": "Picked for: quiet reflection & poignant melodies",
    },
    "focused": {
        "query": "ambient study deep focus instrumental",
        "reason": "Picked for: deep focus & concentration",
    },
}


# ---------------------------------------------------------------------------
# iTunes Search Service
# ---------------------------------------------------------------------------
class iTunesMusicService:
    """
    Service client for interacting with the public Apple iTunes Search API.
    Designed as a singleton or reusable async service.
    """

    def __init__(self, timeout_seconds: int = ITUNES_REQUEST_TIMEOUT) -> None:
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def _get_high_res_artwork(self, raw_url: str | None) -> str:
        """
        iTunes returns low-res artwork by default (e.g. 100x100bb.jpg).
        This helper modifies the URL path to request crisp 600x600 artwork.
        """
        if not raw_url:
            return "https://music.apple.com/assets/favicon/favicon-180.png"
        return raw_url.replace("100x100bb.jpg", "600x600bb.jpg")

    def _parse_track(self, raw_item: dict[str, Any], mood_reason: str) -> TrackInfo | None:
        """Parses an individual track object from the iTunes API response."""
        track_name = raw_item.get("trackName")
        artist_name = raw_item.get("artistName")
        if not track_name or not artist_name:
            return None

        return TrackInfo(
            track_id=raw_item.get("trackId", 0),
            track_name=track_name,
            artist_name=artist_name,
            collection_name=raw_item.get("collectionName", "Single / Unknown Album"),
            track_view_url=raw_item.get("trackViewUrl", "https://music.apple.com"),
            preview_url=raw_item.get("previewUrl"),
            artwork_url=self._get_high_res_artwork(raw_item.get("artworkUrl100")),
            primary_genre=raw_item.get("primaryGenreName", "Music"),
            duration_ms=raw_item.get("trackTimeMillis", 0),
            mood_reason=mood_reason,
        )

    async def fetch_tracks_by_query(
        self,
        query: str,
        reason: str,
        limit: int = 15,
    ) -> list[TrackInfo]:
        """
        Sends an asynchronous GET request to the iTunes Search API.

        Args:
            query: The search term passed to iTunes.
            reason: The explanation string for why this track matches.
            limit: Maximum number of tracks to fetch (default: 15).

        Returns:
            A list of validated TrackInfo objects.

        Raises:
            MusicTimeoutError: If the request exceeds the configured timeout.
            MusicAPIError: If the server responds with a non-200 status code.
            NoTracksFoundError: If zero tracks were returned for the search term.
        """
        params = {
            "term": query,
            "media": "music",
            "entity": "song",
            "limit": str(limit),
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(ITUNES_API_BASE_URL, params=params) as response:
                    if response.status != 200:
                        raise MusicAPIError(
                            f"iTunes API returned HTTP status {response.status}.",
                            suggestion="Apple's music servers may be temporarily busy. Please try again shortly.",
                        )
                    data = await response.json(content_type=None)

        except asyncio.TimeoutError as exc:
            logger.error("Timeout while querying iTunes API: %s", exc)
            raise MusicTimeoutError(
                "Network request to iTunes timed out.",
                suggestion="Check your internet connection or try again in a few seconds.",
            ) from exc
        except aiohttp.ClientError as exc:
            logger.error("Client connection error while querying iTunes API: %s", exc)
            raise MusicAPIError(
                "Failed to communicate with iTunes music service.",
                suggestion="Please verify network availability or try again shortly.",
            ) from exc

        raw_results = data.get("results", [])
        if not raw_results:
            raise NoTracksFoundError(
                f"No songs found matching query: '{query}'.",
                suggestion="Try choosing a different mood or genre combination!",
            )

        tracks: list[TrackInfo] = []
        for item in raw_results:
            parsed = self._parse_track(item, reason)
            if parsed is not None:
                tracks.append(parsed)

        if not tracks:
            raise NoTracksFoundError(
                "No valid music tracks could be parsed from the search results.",
                suggestion="Try picking an alternative mood combination.",
            )

        return tracks

    async def get_recommendations_for_mood(
        self,
        primary_mood: str,
        flavor_genre: str | None = None,
        limit: int = 15,
    ) -> list[TrackInfo]:
        """
        Resolves mood selections to targeted search queries and retrieves recommendations.

        Args:
            primary_mood: Main emotional state (e.g. 'energetic', 'chill', 'sad', 'focused').
            flavor_genre: Optional genre preference (e.g. 'pop_rock', 'lofi', 'acoustic', 'ambient').
            limit: Number of candidate tracks to fetch.

        Returns:
            List of TrackInfo candidate recommendations.
        """
        primary = primary_mood.strip().lower()
        flavor = (flavor_genre or "").strip().lower()

        # Check compound mood profile
        profile = MOOD_PROFILES.get((primary, flavor))

        # Fallback to single mood profile if compound not found
        if not profile:
            profile = DEFAULT_MOOD_TERMS.get(
                primary,
                {
                    "query": f"{primary} {flavor} music",
                    "reason": f"Picked for: {primary} vibe",
                },
            )

        return await self.fetch_tracks_by_query(
            query=profile["query"],
            reason=profile["reason"],
            limit=limit,
        )


# Global reusable instance
itunes_service = iTunesMusicService()
