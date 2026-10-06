"""
Unit Tests for audio_player.py
"""

import unittest
from unittest.mock import MagicMock, patch
from services.audio_player import AudioPlayerService
from services.itunes_service import TrackInfo


class TestAudioPlayerService(unittest.TestCase):
    """Verifies audio player state management and error validation."""

    def setUp(self) -> None:
        self.player = AudioPlayerService()
        self.sample_track = TrackInfo(
            track_id=101,
            track_name="Test Song",
            artist_name="Test Artist",
            collection_name="Test Album",
            track_view_url="https://music.apple.com/song/101",
            preview_url="https://audio-ssl.itunes.apple.com/preview.m4a",
            artwork_url="https://is1-ssl.mzstatic.com/image/600x600bb.jpg",
            primary_genre="Pop",
            duration_ms=180000,
            mood_reason="Test mood",
        )

    def test_play_track_no_preview_url(self) -> None:
        """Tracks without a preview URL should fail gracefully."""
        track_without_preview = TrackInfo(
            track_id=102,
            track_name="No Preview",
            artist_name="Artist",
            collection_name="Album",
            track_view_url="https://music.apple.com/song/102",
            preview_url=None,
            artwork_url="https://is1-ssl.mzstatic.com/image/600x600bb.jpg",
            primary_genre="Ambient",
            duration_ms=120000,
            mood_reason="Test mood",
        )
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True

        success, err = self.player.play_track(mock_vc, track_without_preview)
        self.assertFalse(success)
        self.assertIn("does not have an audio preview stream", err)

    def test_pause_resume_stop_playback(self) -> None:
        """Verifies pause, resume, and stop delegations to voice_client."""
        mock_vc = MagicMock()

        # Pause test
        mock_vc.is_playing.return_value = True
        self.assertTrue(self.player.pause_playback(mock_vc))
        mock_vc.pause.assert_called_once()

        # Resume test
        mock_vc.is_paused.return_value = True
        self.assertTrue(self.player.resume_playback(mock_vc))
        mock_vc.resume.assert_called_once()

        # Stop test
        mock_vc.is_playing.return_value = True
        self.assertTrue(self.player.stop_playback(mock_vc))
        mock_vc.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
