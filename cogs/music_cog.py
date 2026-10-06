"""
Music Playback & Recommendations Cog (music_cog.py)

This Cog provides rich slash commands for music playback and mood-based recommendations:
1. `/recommend`: Recommends and streams music tailored to a selected mood into Discord Voice.
2. `/play_mood`: Quick-play command that joins voice and plays mood music immediately.
3. `/play`: Searches iTunes for a specific song/artist and streams it directly in voice.
4. `/pause` & `/resume`: Controls active voice playback.
5. `/stop`: Halts music playback.
6. `/join` & `/leave`: Manages bot voice channel presence.

Academic & Technical Features:
- Direct Voice Streaming: Pipes iTunes preview AAC streams through FFmpeg into Discord Voice.
- Dynamic Fallback: If the user is not in a voice channel, still provides interactive embeds with
  an inline "Play in Voice" button when they join.
- Native Opus Support: Pre-loads libopus for high-performance audio encoding on macOS and Linux.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from services.audio_player import audio_player
from services.itunes_service import (
    MusicServiceException,
    itunes_service,
)
from ui.playback_view import PlaybackView, create_track_embed
from utils.quiz_style import (
    create_error_embed,
    create_styled_embed,
    get_mood_color,
)

logger = logging.getLogger(__name__)

MOOD_CHOICES = [
    app_commands.Choice(name="⚡ Energetic (High BPM, Dance, Upbeat)", value="energetic"),
    app_commands.Choice(name="🌿 Chill (Mellow, Relaxed, Easygoing)", value="chill"),
    app_commands.Choice(name="🌧️ Sad (Emotional, Acoustic, Reflective)", value="sad"),
    app_commands.Choice(name="🧠 Focused (Study, Ambient, Flow)", value="focused"),
]

GENRE_CHOICES = [
    app_commands.Choice(name="🎸 Pop & Rock", value="pop_rock"),
    app_commands.Choice(name="☕ Lo-fi Beats", value="lofi"),
    app_commands.Choice(name="🎻 Acoustic & Indie", value="acoustic"),
    app_commands.Choice(name="🌌 Ambient & Synth", value="ambient"),
]


class MusicCog(commands.Cog, name="Music Commands"):
    """Handles direct recommendation queries, voice streaming, and playback controls."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="recommend",
        description="Get music tailored to your mood and stream it in your voice channel.",
    )
    @app_commands.describe(
        mood="Select your desired listening mood",
        genre="Optional style or genre flavor",
    )
    @app_commands.choices(mood=MOOD_CHOICES, genre=GENRE_CHOICES)
    async def recommend(
        self,
        interaction: discord.Interaction,
        mood: app_commands.Choice[str],
        genre: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Queries iTunes for the specified mood and automatically plays in voice if connected."""
        await interaction.response.defer()

        flavor_value = genre.value if genre else None

        try:
            tracks = await itunes_service.get_recommendations_for_mood(
                primary_mood=mood.value,
                flavor_genre=flavor_value,
                limit=15,
            )

            # Auto-connect to voice channel if user is currently in one
            voice_channel_name = None
            if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
                vc, err = await audio_player.join_user_voice(interaction)
                if vc and not err:
                    await audio_player.play_track_async(
                        vc,
                        tracks[0],
                        track_queue=tracks,
                        queue_index=0,
                        loop=asyncio.get_event_loop(),
                    )
                    voice_channel_name = vc.channel.name

            playback_view = PlaybackView(
                tracks=tracks,
                author_id=interaction.user.id,
                mood_name=mood.value,
                current_index=0,
                voice_channel_name=voice_channel_name,
            )

            embed = create_track_embed(
                track=tracks[0],
                current_index=0,
                total_tracks=len(tracks),
                mood_name=mood.value,
                voice_channel_name=voice_channel_name,
            )

            await interaction.followup.send(embed=embed, view=playback_view)

        except MusicServiceException as exc:
            error_embed = create_error_embed(
                title="Recommendation Error",
                message=exc.message,
                suggestion=exc.suggestion,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(
        name="play_mood",
        description="Quickly join your voice channel and start streaming music for a mood.",
    )
    @app_commands.describe(mood="The mood you want to listen to")
    @app_commands.choices(mood=MOOD_CHOICES)
    async def play_mood(
        self,
        interaction: discord.Interaction,
        mood: app_commands.Choice[str],
    ) -> None:
        """Shortcut command ensuring voice channel connection and immediate playback."""
        await interaction.response.defer()

        # Verify user is in voice channel
        vc, err = await audio_player.join_user_voice(interaction)
        if err or not vc:
            await interaction.followup.send(f"❌ {err}", ephemeral=True)
            return

        try:
            tracks = await itunes_service.get_recommendations_for_mood(
                primary_mood=mood.value,
                limit=15,
            )

            await audio_player.play_track_async(
                vc,
                tracks[0],
                track_queue=tracks,
                queue_index=0,
                loop=asyncio.get_event_loop(),
            )

            playback_view = PlaybackView(
                tracks=tracks,
                author_id=interaction.user.id,
                mood_name=mood.value,
                current_index=0,
                voice_channel_name=vc.channel.name,
            )

            embed = create_track_embed(
                track=tracks[0],
                current_index=0,
                total_tracks=len(tracks),
                mood_name=mood.value,
                voice_channel_name=vc.channel.name,
            )

            await interaction.followup.send(embed=embed, view=playback_view)

        except MusicServiceException as exc:
            error_embed = create_error_embed(
                title="Playback Error",
                message=exc.message,
                suggestion=exc.suggestion,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(
        name="play",
        description="Search for any song or artist on iTunes and play it in your voice channel.",
    )
    @app_commands.describe(query="Song title, artist name, or keywords")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """Searches iTunes and streams the matched song in voice."""
        await interaction.response.defer()

        clean_query = query.strip()
        if not clean_query:
            await interaction.followup.send("❌ Please provide a song or artist name.", ephemeral=True)
            return

        try:
            tracks = await itunes_service.fetch_tracks_by_query(
                query=clean_query,
                reason=f"Matched query: '{clean_query}'",
                limit=10,
            )

            voice_channel_name = None
            if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
                vc, err = await audio_player.join_user_voice(interaction)
                if vc and not err:
                    audio_player.play_track(vc, tracks[0])
                    voice_channel_name = vc.channel.name

            playback_view = PlaybackView(
                tracks=tracks,
                author_id=interaction.user.id,
                mood_name="search",
                current_index=0,
                voice_channel_name=voice_channel_name,
            )

            embed = create_track_embed(
                track=tracks[0],
                current_index=0,
                total_tracks=len(tracks),
                mood_name="search",
                voice_channel_name=voice_channel_name,
            )

            await interaction.followup.send(embed=embed, view=playback_view)

        except MusicServiceException as exc:
            error_embed = create_error_embed(
                title="Song Not Found",
                message=exc.message,
                suggestion=exc.suggestion,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(
        name="pause",
        description="Pause the currently playing music in your voice channel.",
    )
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pauses active voice stream."""
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        if audio_player.pause_playback(vc):
            await interaction.response.send_message("⏸️ Music paused. Use `/resume` to continue.")
        else:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

    @app_commands.command(
        name="resume",
        description="Resume paused music playback.",
    )
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resumes paused voice stream."""
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        if audio_player.resume_playback(vc):
            await interaction.response.send_message("▶️ Resumed music playback!")
        else:
            await interaction.response.send_message("❌ Music is not paused.", ephemeral=True)

    @app_commands.command(
        name="stop",
        description="Stop music playback in the voice channel.",
    )
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stops voice stream."""
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        if audio_player.stop_playback(vc):
            await interaction.response.send_message("⏹️ Stopped music playback.")
        else:
            await interaction.response.send_message("❌ No music is currently playing.", ephemeral=True)

    @app_commands.command(
        name="join",
        description="Summon the bot to your current voice channel.",
    )
    async def join(self, interaction: discord.Interaction) -> None:
        """Connects to the member's voice channel."""
        vc, err = await audio_player.join_user_voice(interaction)
        if err or not vc:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        else:
            await interaction.response.send_message(f"🔊 Joined **#{vc.channel.name}**! Ready to play music.")

    @app_commands.command(
        name="leave",
        description="Disconnect the bot from the voice channel.",
    )
    async def leave(self, interaction: discord.Interaction) -> None:
        """Disconnects from the voice channel."""
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        if vc and await audio_player.disconnect(vc):
            await interaction.response.send_message("👋 Disconnected from voice channel.")
        else:
            await interaction.response.send_message("❌ I am not connected to any voice channel.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Standard extension setup function required by discord.py."""
    await bot.add_cog(MusicCog(bot))
