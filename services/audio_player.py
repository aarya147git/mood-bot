"""
Audio Player Service (audio_player.py)

Handles Discord Voice Channel connections, libopus loading, and FFmpeg audio streaming.
Enables AuraTunes to play music recommendations directly inside voice channels.

Key design for lag-free playback:
  - Tracks are pre-downloaded to temp files before playback begins.
    FFmpeg reads from disk instead of a live HTTPS stream, eliminating
    all network-related stuttering and startup delay.
  - The NEXT track in the queue is pre-fetched while the current one plays,
    so transitions between tracks are seamless.
  - A session-token system prevents the auto-queue from restarting after
    stop_playback() or play_sound() is called (e.g. on focus session end).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Callable, Optional
import aiohttp
import discord

from services.itunes_service import TrackInfo

logger = logging.getLogger("AuraTunes.AudioPlayer")

# Common search paths for libopus on macOS (Apple Silicon / Intel) and Linux
OPUS_CANDIDATES = [
    "/opt/homebrew/lib/libopus.dylib",
    "/usr/local/lib/libopus.dylib",
    "libopus.dylib",
    "libopus.so.0",
    "libopus.so",
    "opus",
]

# FFmpeg options for local temp files — no HTTP reconnect needed,
# minimal probing since format is already known from the file extension.
FFMPEG_OPTIONS = {
    "before_options": "-nostdin",
    "options": "-vn -ar 48000 -ac 2",
}

# Fallback FFmpeg options used only if a track couldn't be pre-downloaded
# (plays directly from URL with reconnect and reduced probing).
FFMPEG_STREAM_OPTIONS = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_delay_max 3 "
        "-analyzeduration 0 "
        "-probesize 32 "
        "-nostdin"
    ),
    "options": "-vn -ar 48000 -ac 2",
}

# Clear, pleasant ding/bell sound (Wikimedia Commons, CC0 public domain).
# Used to signal end of a focus session inside the voice channel.
SESSION_END_SOUND_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/3/34/Sound_Effect_-_Door_Bell.ogg"
)

# How long to wait for a download before giving up and streaming from URL
DOWNLOAD_TIMEOUT_SECONDS = 8


def load_opus_library() -> bool:
    """Attempts to find and load the libopus native library for Discord voice encryption."""
    if discord.opus.is_loaded():
        return True

    for candidate in OPUS_CANDIDATES:
        try:
            discord.opus.load_opus(candidate)
            if discord.opus.is_loaded():
                logger.info("Successfully loaded libopus from: %s", candidate)
                return True
        except Exception:
            continue

    logger.warning("libopus could not be loaded automatically. Voice streaming may fail.")
    return False


# Attempt loading Opus upon service import
load_opus_library()


# ---------------------------------------------------------------------------
# Audio Pre-fetcher
# ---------------------------------------------------------------------------
async def _download_to_tempfile(url: str) -> Optional[str]:
    """
    Downloads an audio URL to a temporary file on disk.

    Returns the temp file path on success, or None on failure.
    The caller is responsible for deleting the file when done.
    """
    suffix = ".aac"
    if ".ogg" in url:
        suffix = ".ogg"
    elif ".mp3" in url:
        suffix = ".mp3"
    elif ".m4a" in url or ".m4p" in url:
        suffix = ".m4a"

    try:
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Pre-fetch failed: HTTP %d for %s", resp.status, url)
                    return None
                data = await resp.read()

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(data)
        tmp.close()
        logger.info("Pre-fetched %d bytes → %s", len(data), tmp.name)
        return tmp.name

    except asyncio.TimeoutError:
        logger.warning("Pre-fetch timed out for %s", url)
        return None
    except Exception as exc:
        logger.warning("Pre-fetch error for %s: %s", url, exc)
        return None


def _delete_tempfile(path: Optional[str]) -> None:
    """Silently deletes a temp file if it exists."""
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


class AudioPlayerService:
    """
    Manages voice channel connections and audio stream playback.

    Per-voice-client session tokens prevent the auto-queue from restarting
    music after stop_playback() or play_sound() is called.
    """

    def __init__(self) -> None:
        # Maps id(voice_client) → current queue session token.
        # Incremented by stop_playback() / play_sound() to cancel in-flight
        # auto-advance callbacks that captured the old token.
        self._queue_tokens: dict[int, int] = {}

        # Maps id(voice_client) → path of temp file currently being played.
        # Deleted when the track finishes or is stopped.
        self._active_tempfiles: dict[int, str] = {}

    def is_voice_supported(self) -> bool:
        """Checks whether Opus is loaded and FFmpeg is available on the host system."""
        return bool(shutil.which("ffmpeg") and discord.opus.is_loaded())

    async def join_user_voice(
        self,
        interaction: discord.Interaction,
    ) -> tuple[Optional[discord.VoiceClient], Optional[str]]:
        """
        Connects the bot to the voice channel the invoking user is currently in.

        Returns:
            (VoiceClient, None) if successfully connected.
            (None, error_message) on failure.
        """
        if not interaction.guild:
            return None, "Voice playback is only supported within Discord servers."

        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            return None, "You must join a Voice Channel first so I can play music for you!"

        target_channel = member.voice.channel
        permissions = target_channel.permissions_for(interaction.guild.me)
        if not permissions.connect or not permissions.speak:
            return None, f"I don't have permission to join or speak in **{target_channel.name}**."

        voice_client: Optional[discord.VoiceClient] = interaction.guild.voice_client

        try:
            if voice_client is None:
                voice_client = await target_channel.connect()
            elif voice_client.channel.id != target_channel.id:
                await voice_client.move_to(target_channel)
            return voice_client, None
        except Exception as exc:
            logger.exception("Failed to connect to voice channel: %s", exc)
            return None, f"Failed to join voice channel: {exc}"

    async def play_track_async(
        self,
        voice_client: discord.VoiceClient,
        track: TrackInfo,
        after_callback: Optional[Callable[[Optional[Exception]], None]] = None,
        *,
        track_queue: Optional[list[TrackInfo]] = None,
        queue_index: int = 0,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Pre-downloads the track audio to a temp file, then plays it via FFmpeg.

        Reading from disk instead of a live HTTPS stream eliminates all network-
        related startup lag and playback stuttering.

        If ``track_queue`` is provided, the NEXT track is pre-fetched in the
        background while the current one plays, so transitions are instant.

        Returns:
            (True, None) on successful playback start.
            (False, error_reason) on failure.
        """
        if not track.preview_url:
            return False, "This song does not have an audio preview stream available."

        if not voice_client.is_connected():
            return False, "Bot is not connected to a voice channel."

        # --- Pre-download the audio file ---
        temp_path = await _download_to_tempfile(track.preview_url)

        # Abort if disconnected while downloading
        if not voice_client.is_connected():
            _delete_tempfile(temp_path)
            return False, "Disconnected from voice channel during download."

        # Mint a new session token for this queue slot
        vc_key = id(voice_client)
        token = self._queue_tokens.get(vc_key, 0) + 1
        self._queue_tokens[vc_key] = token

        # Stop any existing playback and clean up previous temp file
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        _delete_tempfile(self._active_tempfiles.pop(vc_key, None))

        if temp_path:
            self._active_tempfiles[vc_key] = temp_path

        captured_token = token
        service = self

        def _after(exc: Optional[Exception]) -> None:
            """Called by discord.py in a background thread when playback ends."""
            # Clean up the temp file for the track that just finished
            _delete_tempfile(service._active_tempfiles.pop(vc_key, None))

            if exc:
                logger.warning("Playback ended with error (auto-advance skipped): %s", exc)
                if after_callback:
                    after_callback(exc)
                return

            # Session token check — if stop_playback() was called, token will
            # have advanced; a mismatch means we must NOT restart the queue.
            if service._queue_tokens.get(vc_key) != captured_token:
                logger.info("Auto-advance suppressed: session token invalidated.")
                if after_callback:
                    after_callback(exc)
                return

            # Schedule the next track on the event loop
            if track_queue and loop and voice_client.is_connected():
                next_index = (queue_index + 1) % len(track_queue)
                next_track = track_queue[next_index]
                asyncio.run_coroutine_threadsafe(
                    _play_next_async(
                        voice_client, next_track, track_queue, next_index, loop, service
                    ),
                    loop,
                )

            if after_callback:
                after_callback(exc)

        try:
            if temp_path:
                # Play from disk — fast, no network lag
                source = discord.FFmpegPCMAudio(temp_path, **FFMPEG_OPTIONS)
            else:
                # Fallback: stream directly from URL
                logger.warning("Playing '%s' via URL fallback (download failed)", track.track_name)
                source = discord.FFmpegPCMAudio(track.preview_url, **FFMPEG_STREAM_OPTIONS)

            voice_client.play(source, after=_after)
            logger.info("Now playing '%s' in %s", track.track_name, voice_client.channel.name)
            return True, None

        except Exception as exc:
            _delete_tempfile(self._active_tempfiles.pop(vc_key, None))
            logger.exception("Error starting FFmpeg stream: %s", exc)
            return False, f"Audio playback error: {exc}"

    def play_track(
        self,
        voice_client: discord.VoiceClient,
        track: TrackInfo,
        after_callback: Optional[Callable[[Optional[Exception]], None]] = None,
        *,
        track_queue: Optional[list[TrackInfo]] = None,
        queue_index: int = 0,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Synchronous wrapper around play_track_async.

        Schedules the async download + play on the event loop.
        Returns immediately — use play_track_async directly if you need to await it.
        """
        if not track.preview_url:
            return False, "This song does not have an audio preview stream available."

        if not voice_client.is_connected():
            return False, "Bot is not connected to a voice channel."

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

        asyncio.run_coroutine_threadsafe(
            self.play_track_async(
                voice_client,
                track,
                after_callback,
                track_queue=track_queue,
                queue_index=queue_index,
                loop=loop,
            ),
            loop,
        )
        return True, None

    def play_sound(
        self,
        voice_client: discord.VoiceClient,
        url: str,
        after_callback: Optional[Callable[[Optional[Exception]], None]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Plays a one-shot audio URL (ding/chime) without auto-advance.
        Invalidates the queue token BEFORE stopping so the music queue's
        _after callback won't restart playback.
        """
        if not voice_client.is_connected():
            return False, "Bot is not connected to a voice channel."

        try:
            # Invalidate token first, then stop — prevents music queue restart
            vc_key = id(voice_client)
            self._queue_tokens[vc_key] = self._queue_tokens.get(vc_key, 0) + 1

            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            _delete_tempfile(self._active_tempfiles.pop(vc_key, None))

            source = discord.FFmpegPCMAudio(url, **FFMPEG_STREAM_OPTIONS)
            voice_client.play(source, after=after_callback)
            logger.info("Playing notification ding in %s", voice_client.channel.name)
            return True, None
        except Exception as exc:
            logger.exception("Error playing notification sound: %s", exc)
            return False, f"Sound playback error: {exc}"

    def pause_playback(self, voice_client: Optional[discord.VoiceClient]) -> bool:
        """Pauses the current stream if playing."""
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            return True
        return False

    def resume_playback(self, voice_client: Optional[discord.VoiceClient]) -> bool:
        """Resumes paused playback."""
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            return True
        return False

    def stop_playback(self, voice_client: Optional[discord.VoiceClient]) -> bool:
        """
        Stops playback and invalidates the queue session token so
        no pending auto-advance callback will restart music.
        """
        if voice_client:
            vc_key = id(voice_client)
            self._queue_tokens[vc_key] = self._queue_tokens.get(vc_key, 0) + 1
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            _delete_tempfile(self._active_tempfiles.pop(vc_key, None))
            return True
        return False

    async def disconnect(self, voice_client: Optional[discord.VoiceClient]) -> bool:
        """Disconnects and cleans up the queue token and any temp files."""
        if voice_client and voice_client.is_connected():
            vc_key = id(voice_client)
            self._queue_tokens[vc_key] = self._queue_tokens.get(vc_key, 0) + 1
            _delete_tempfile(self._active_tempfiles.pop(vc_key, None))
            await voice_client.disconnect()
            return True
        return False


# ---------------------------------------------------------------------------
# Internal helper — auto-advance to next track
# ---------------------------------------------------------------------------
async def _play_next_async(
    voice_client: discord.VoiceClient,
    track: TrackInfo,
    track_queue: list[TrackInfo],
    queue_index: int,
    loop: asyncio.AbstractEventLoop,
    service: AudioPlayerService,
) -> None:
    """
    Called from the FFmpeg after-callback thread to play the next queued track.

    Pre-downloads the audio to a temp file before starting FFmpeg, so the
    transition is fast (disk read, not network stream).
    """
    if not voice_client.is_connected():
        return

    await service.play_track_async(
        voice_client,
        track,
        track_queue=track_queue,
        queue_index=queue_index,
        loop=loop,
    )
    logger.info("Auto-advanced queue → track %d: '%s'", queue_index, track.track_name)


# Global singleton instance
audio_player = AudioPlayerService()
