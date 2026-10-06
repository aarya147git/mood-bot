"""
Interactive Playback Controls View (playback_view.py)

This module implements the Discord UI View displayed alongside music recommendations.
Key Features:
- Direct Voice Playback: Streams the recommended audio into the user's Discord Voice Channel.
- "Play / Pause in Voice": Starts or toggles playback in the voice channel.
- "Next Track / Skip": Cycles through candidate songs and streams the next track.
- "Stop Voice": Stops playback in the voice channel.
- "Audio Preview": Direct external link button to the 30-second AAC audio snippet.
- "Change Mood": Allows the user to discard the current recommendation and restart the quiz.
- "Apple Music": External link button to the official Apple Music track page.
- Interaction Authorization: Ensures only the user who triggered the command can control playback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord

from services.audio_player import audio_player
from services.itunes_service import TrackInfo
from utils.quiz_style import create_styled_embed, get_mood_color

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ui.mood_quiz_view import MoodQuizView


def create_track_embed(
    track: TrackInfo,
    current_index: int,
    total_tracks: int,
    mood_name: str,
    voice_channel_name: Optional[str] = None,
) -> discord.Embed:
    """
    Constructs an informative, aesthetically styled embed for a music recommendation.
    """
    mood_color = get_mood_color(mood_name)

    voice_info = (
        f"🔊 **Now playing in voice:** `#{voice_channel_name}`\n"
        if voice_channel_name
        else "💡 *Join a voice channel and press **Play in Voice** to hear this track live!*\n"
    )

    description = (
        f"### 🎵 [{track.track_name}]({track.track_view_url})\n"
        f"**Artist:** {track.artist_name}\n"
        f"**Album:** {track.collection_name}\n\n"
        f"{voice_info}\n"
        f"✨ **Why this song?**\n"
        f"> *{track.mood_reason}*\n"
    )

    fields = [
        ("Genre", f"`{track.primary_genre}`", True),
        ("Duration", f"`{track.formatted_duration}`", True),
        ("Catalog", f"`Track {current_index + 1} of {total_tracks}`", True),
    ]

    embed = create_styled_embed(
        title="🎧 Your Mood Music Recommendation",
        description=description,
        color=mood_color,
        fields=fields,
        image_url=track.artwork_url,
        footer_text=f"AuraTunes • Mood: {mood_name.capitalize()} • Powered by iTunes API",
    )
    return embed


class PlaybackView(discord.ui.View):
    """
    Discord UI View managing interactive playback control buttons and voice streaming.
    """

    def __init__(
        self,
        tracks: list[TrackInfo],
        author_id: int,
        mood_name: str,
        current_index: int = 0,
        voice_channel_name: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.tracks = tracks
        self.author_id = author_id
        self.mood_name = mood_name
        self.current_index = current_index % max(len(tracks), 1)
        self.voice_channel_name = voice_channel_name

        self._build_controls()

    @property
    def current_track(self) -> TrackInfo:
        """Returns the currently active TrackInfo."""
        return self.tracks[self.current_index]

    def _build_controls(self) -> None:
        """Dynamically populates the view with buttons based on the active track."""
        self.clear_items()

        # 1. Play / Pause in Voice Button
        voice_btn = discord.ui.Button(
            label="Play in Voice" if not self.voice_channel_name else "Pause / Resume",
            style=discord.ButtonStyle.success if not self.voice_channel_name else discord.ButtonStyle.primary,
            emoji="▶️" if not self.voice_channel_name else "⏯️",
            custom_id="playback_voice_toggle",
        )
        voice_btn.callback = self._on_voice_toggle_clicked
        self.add_item(voice_btn)

        # 2. Skip / Next Track Button
        skip_button = discord.ui.Button(
            label="Next Track",
            style=discord.ButtonStyle.primary,
            emoji="⏭️",
            custom_id="playback_skip",
        )
        skip_button.callback = self._on_skip_clicked
        self.add_item(skip_button)

        # 3. Stop Voice Playback Button
        if self.voice_channel_name:
            stop_button = discord.ui.Button(
                label="Stop Voice",
                style=discord.ButtonStyle.danger,
                emoji="⏹️",
                custom_id="playback_stop",
            )
            stop_button.callback = self._on_stop_clicked
            self.add_item(stop_button)

        # 4. Change Mood Button (Restarts quiz)
        change_mood_button = discord.ui.Button(
            label="Change Mood",
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            custom_id="playback_change_mood",
        )
        change_mood_button.callback = self._on_change_mood_clicked
        self.add_item(change_mood_button)

        # 5. Audio Preview (30-second AAC stream) Link Button
        if self.current_track.preview_url:
            self.add_item(
                discord.ui.Button(
                    label="Audio Preview (30s)",
                    style=discord.ButtonStyle.link,
                    url=self.current_track.preview_url,
                    emoji="🎧",
                )
            )

        # 6. Official Apple Music URL Link Button
        self.add_item(
            discord.ui.Button(
                label="Apple Music",
                style=discord.ButtonStyle.link,
                url=self.current_track.track_view_url,
                emoji="🔗",
            )
        )

    async def _verify_author(self, interaction: discord.Interaction) -> bool:
        """Guards against interaction hijacking by other server members."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ This music session belongs to someone else. "
                "Use `/mood` or `/recommend` to start your own session!",
                ephemeral=True,
            )
            return False
        return True

    async def _on_voice_toggle_clicked(self, interaction: discord.Interaction) -> None:
        """Handles joining voice and toggling playback."""
        if not await self._verify_author(interaction):
            return

        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None

        if vc and vc.is_playing():
            audio_player.pause_playback(vc)
            await interaction.response.send_message("⏸️ Paused playback in voice channel.", ephemeral=True)
            return
        elif vc and vc.is_paused():
            audio_player.resume_playback(vc)
            await interaction.response.send_message("▶️ Resumed playback in voice channel.", ephemeral=True)
            return

        # Not yet connected or stopped: connect and stream
        await interaction.response.defer()

        voice_client, err = await audio_player.join_user_voice(interaction)
        if err or not voice_client:
            await interaction.followup.send(f"❌ {err}", ephemeral=True)
            return

        success, play_err = await audio_player.play_track_async(
            voice_client,
            self.current_track,
            track_queue=self.tracks,
            queue_index=self.current_index,
            loop=asyncio.get_event_loop(),
        )
        if not success:
            await interaction.followup.send(f"❌ Could not play track: {play_err}", ephemeral=True)
            return

        self.voice_channel_name = voice_client.channel.name
        self._build_controls()

        new_embed = create_track_embed(
            track=self.current_track,
            current_index=self.current_index,
            total_tracks=len(self.tracks),
            mood_name=self.mood_name,
            voice_channel_name=self.voice_channel_name,
        )
        await interaction.edit_original_response(embed=new_embed, view=self)

    async def _on_skip_clicked(self, interaction: discord.Interaction) -> None:
        """Advances to the next track in the retrieved playlist and streams it if connected."""
        if not await self._verify_author(interaction):
            return

        # Advance track index in a circular fashion
        self.current_index = (self.current_index + 1) % len(self.tracks)

        # Stream new track in voice if connected
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.is_connected():
            await audio_player.play_track_async(
                vc,
                self.current_track,
                track_queue=self.tracks,
                queue_index=self.current_index,
                loop=asyncio.get_event_loop(),
            )
            self.voice_channel_name = vc.channel.name

        self._build_controls()

        new_embed = create_track_embed(
            track=self.current_track,
            current_index=self.current_index,
            total_tracks=len(self.tracks),
            mood_name=self.mood_name,
            voice_channel_name=self.voice_channel_name,
        )

        await interaction.response.edit_message(embed=new_embed, view=self)

    async def _on_stop_clicked(self, interaction: discord.Interaction) -> None:
        """Stops playback in voice channel."""
        if not await self._verify_author(interaction):
            return

        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        audio_player.stop_playback(vc)
        self.voice_channel_name = None
        self._build_controls()

        new_embed = create_track_embed(
            track=self.current_track,
            current_index=self.current_index,
            total_tracks=len(self.tracks),
            mood_name=self.mood_name,
            voice_channel_name=None,
        )
        await interaction.response.edit_message(embed=new_embed, view=self)

    async def _on_change_mood_clicked(self, interaction: discord.Interaction) -> None:
        """Discards the playlist and re-triggers the Mood MCQ quiz."""
        if not await self._verify_author(interaction):
            return

        # Stop voice playback when changing mood
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        audio_player.stop_playback(vc)

        from ui.mood_quiz_view import MoodQuizView

        quiz_view = MoodQuizView(author=interaction.user)
        initial_embed = quiz_view.render_step_embed()

        await interaction.response.edit_message(embed=initial_embed, view=quiz_view)

    async def on_timeout(self) -> None:
        """Disables interactive buttons when the view expires to prevent stale clicks."""
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.style != discord.ButtonStyle.link:
                item.disabled = True
