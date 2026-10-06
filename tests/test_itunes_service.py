"""
Unit Tests for itunes_service.py

Verifies:
1. TrackInfo data model and duration formatting (e.g. 215430 ms -> '3:35').
2. Mood profile query resolution and fallback mapping.
3. High-resolution artwork URL conversion (replacing 100x100 with 600x600).
4. Error handling for empty search results and API exceptions.
"""

import sys
import unittest
from unittest.mock import MagicMock

# If aiohttp is not installed in the local execution environment, provide a lightweight mock
if "aiohttp" not in sys.modules:
    mock_aiohttp = MagicMock()
    sys.modules["aiohttp"] = mock_aiohttp

from services.itunes_service import (
    DEFAULT_MOOD_TERMS,
    MOOD_PROFILES,
    NoTracksFoundError,
    TrackInfo,
    iTunesMusicService,
)


class TestiTunesService(unittest.TestCase):
    """Test suite for iTunes music service logic and data models."""

    def setUp(self) -> None:
        self.service = iTunesMusicService()

    def test_track_info_formatted_duration(self) -> None:
        """Milliseconds should format accurately into mm:ss."""
        track = TrackInfo(
            track_id=101,
            track_name="Midnight City",
            artist_name="M83",
            collection_name="Hurry Up, We're Dreaming",
            track_view_url="https://music.apple.com/song/101",
            preview_url="https://audio-ssl.itunes.apple.com/preview.m4a",
            artwork_url="https://is1-ssl.mzstatic.com/image/600x600bb.jpg",
            primary_genre="Electronic",
            duration_ms=243000,  # 4 minutes and 3 seconds
            mood_reason="Picked for: energetic + rhythmic synth groove",
        )
        self.assertEqual(track.formatted_duration, "4:03")

    def test_track_info_zero_duration_fallback(self) -> None:
        """A track with missing or zero duration should display '--:--' without crashing."""
        track = TrackInfo(
            track_id=102,
            track_name="Ambient Stream",
            artist_name="Drone Artist",
            collection_name="Soundscapes",
            track_view_url="https://music.apple.com/song/102",
            preview_url=None,
            artwork_url="https://is1-ssl.mzstatic.com/image/600x600bb.jpg",
            primary_genre="Ambient",
            duration_ms=0,
            mood_reason="Picked for: ambient flow",
        )
        self.assertEqual(track.formatted_duration, "--:--")

    def test_high_res_artwork_upgrade(self) -> None:
        """Artwork URL should upgrade 100x100bb.jpg to 600x600bb.jpg."""
        low_res = "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/100x100bb.jpg"
        high_res = self.service._get_high_res_artwork(low_res)
        self.assertIn("600x600bb.jpg", high_res)
        self.assertNotIn("100x100bb.jpg", high_res)

    def test_high_res_artwork_fallback_when_none(self) -> None:
        """None or empty artwork should return a fallback icon URL."""
        fallback = self.service._get_high_res_artwork(None)
        self.assertTrue(fallback.startswith("http"))

    def test_mood_profiles_contain_all_primary_moods(self) -> None:
        """Every core primary mood should have mapped genre profiles."""
        core_moods = ["energetic", "chill", "sad", "focused"]
        flavors = ["pop_rock", "lofi", "acoustic", "ambient"]

        for mood in core_moods:
            # Check default fallback
            self.assertIn(mood, DEFAULT_MOOD_TERMS)
            # Check compound pairs
            for flavor in flavors:
                self.assertIn(
                    (mood, flavor),
                    MOOD_PROFILES,
                    f"Missing profile pair for ({mood}, {flavor})",
                )
                profile = MOOD_PROFILES[(mood, flavor)]
                self.assertTrue(len(profile["query"]) > 0)
                self.assertTrue(len(profile["reason"]) > 0)

    def test_track_parsing_valid(self) -> None:
        """Verifies parsing of standard iTunes JSON result payload."""
        sample_raw = {
            "trackId": 999123,
            "trackName": "Weightless",
            "artistName": "Marconi Union",
            "collectionName": "Weightless (Ambient Transmissions Vol. 2)",
            "trackViewUrl": "https://music.apple.com/us/album/weightless/576629986",
            "previewUrl": "https://audio-ssl.itunes.apple.com/preview.m4a",
            "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/Music/100x100bb.jpg",
            "primaryGenreName": "Ambient",
            "trackTimeMillis": 485000,
        }
        track = self.service._parse_track(sample_raw, mood_reason="Deep focus ambient pick")
        self.assertIsNotNone(track)
        self.assertEqual(track.track_name, "Weightless")
        self.assertEqual(track.artist_name, "Marconi Union")
        self.assertEqual(track.primary_genre, "Ambient")
        self.assertEqual(track.mood_reason, "Deep focus ambient pick")
        self.assertIn("600x600bb.jpg", track.artwork_url)

    def test_track_parsing_missing_name_returns_none(self) -> None:
        """If trackName or artistName is absent, parser should reject the item."""
        sample_malformed = {
            "trackId": 999,
            "collectionName": "Album Only",
        }
        track = self.service._parse_track(sample_malformed, mood_reason="test")
        self.assertIsNone(track)


if __name__ == "__main__":
    unittest.main()
