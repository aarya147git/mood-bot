"""
Interactive Mood MCQ Quiz View (mood_quiz_view.py)

This module handles the multi-step, button-based questionnaire that infers a user's
emotional state and musical taste without requiring manual text typing.

Pedagogical & Architectural Highlights:
1. Finite State Machine (FSM):
   Transitions through discrete quiz stages (Step 1: Mood -> Step 2: Genre/Flavor).
2. Asynchronous Event-Driven UI:
   All button clicks trigger asynchronous callbacks that update the Discord message
   in-place, eliminating channel spam.
3. Strict User Authorization:
   Verifies `interaction.user.id == author.id` on every step to prevent other users
   from answering or interfering with the quiz.
4. Elegant Progress & Style Integration:
   Leverages `utils.quiz_style` for dynamic Unicode progress bars and soft pastel colors.
"""

from __future__ import annotations

import logging
from typing import Sequence
import discord

from services.itunes_service import (
    MusicServiceException,
    itunes_service,
)
from ui.playback_view import PlaybackView, create_track_embed
from utils.quiz_style import (
    create_error_embed,
    create_progress_bar,
    create_styled_embed,
    get_mood_color,
    get_next_pastel_color,
)

logger = logging.getLogger(__name__)

# Question 1: Emotional State options
MOOD_CHOICES: list[tuple[str, str, str]] = [
    ("energetic", "Energetic", "⚡"),
    ("chill", "Chill & Relaxed", "🌿"),
    ("sad", "Sad & Reflective", "🌧️"),
    ("focused", "Deep Focus", "🧠"),
]

# Question 2: Sonic Flavor / Genre options
FLAVOR_CHOICES: list[tuple[str, str, str]] = [
    ("pop_rock", "Pop & Rock", "🎸"),
    ("lofi", "Lo-fi Beats", "☕"),
    ("acoustic", "Acoustic & Indie", "🎻"),
    ("ambient", "Ambient & Synth", "🌌"),
]


class MoodQuizView(discord.ui.View):
    """
    Two-step interactive button questionnaire for inferring user mood and genre preference.
    """

    def __init__(
        self,
        author: discord.User | discord.Member,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author = author
        self.current_step: int = 1
        self.total_steps: int = 2

        # State stored across steps
        self.selected_mood: str | None = None
        self.selected_flavor: str | None = None

        self._load_current_step_buttons()

    def _load_current_step_buttons(self) -> None:
        """Dynamically configures buttons based on the active step."""
        self.clear_items()

        if self.current_step == 1:
            for mood_key, label, emoji in MOOD_CHOICES:
                button = discord.ui.Button(
                    label=label,
                    emoji=emoji,
                    style=discord.ButtonStyle.primary,
                    custom_id=f"mood_{mood_key}",
                )
                button.callback = self._create_step1_callback(mood_key)
                self.add_item(button)

        elif self.current_step == 2:
            for flavor_key, label, emoji in FLAVOR_CHOICES:
                button = discord.ui.Button(
                    label=label,
                    emoji=emoji,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"flavor_{flavor_key}",
                )
                button.callback = self._create_step2_callback(flavor_key)
                self.add_item(button)

    def render_step_embed(self) -> discord.Embed:
        """
        Builds the Discord embed corresponding to the active questionnaire step,
        including rotating pastel theme and progress bar.
        """
        progress_bar = create_progress_bar(self.current_step, self.total_steps)

        if self.current_step == 1:
            title = "✨ How are you feeling right now?"
            description = (
                f"{progress_bar}\n\n"
                "Select the option that best reflects your current energy or emotional state:\n\n"
                "⚡ **Energetic**: Need high energy, pump-up beats, or motivation\n"
                "🌿 **Chill**: Looking to unwind, relax, or keep it mellow\n"
                "🌧️ **Sad**: In a melancholy, introspective, or emotional space\n"
                "🧠 **Deep Focus**: Studying, working, or entering a flow state"
            )
            color = get_next_pastel_color()

        else:  # Step 2
            mood_display = (self.selected_mood or "").capitalize()
            title = f"🎧 What musical flavor suits your {mood_display} mood?"
            description = (
                f"{progress_bar}\n\n"
                f"Great! We'll find something **{mood_display}** for you.\n"
                "Now choose the sonic style you'd prefer to hear right now:"
            )
            color = get_mood_color(self.selected_mood or "chill")

        return create_styled_embed(
            title=title,
            description=description,
            color=color,
            author=self.author,
            footer_text="AuraTunes • Interactive Mood Selector",
        )

    async def _verify_user(self, interaction: discord.Interaction) -> bool:
        """Prevents interaction from anyone other than the quiz initiator."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This quiz was started by someone else. Type `/mood` to start your own!",
                ephemeral=True,
            )
            return False
        return True

    def _create_step1_callback(self, mood_key: str):
        """Higher-order function capturing the selected mood for Step 1."""
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._verify_user(interaction):
                return

            self.selected_mood = mood_key
            self.current_step = 2
            self._load_current_step_buttons()

            new_embed = self.render_step_embed()
            await interaction.response.edit_message(embed=new_embed, view=self)

        return callback

    def _create_step2_callback(self, flavor_key: str):
        """Higher-order function finalizing quiz selections and querying iTunes API."""
        async def callback(interaction: discord.Interaction) -> None:
            if not await self._verify_user(interaction):
                return

            self.selected_flavor = flavor_key

            # Acknowledge the interaction immediately while making the external network call
            await interaction.response.defer()

            try:
                # Query iTunes Search API asynchronously
                tracks = await itunes_service.get_recommendations_for_mood(
                    primary_mood=self.selected_mood or "chill",
                    flavor_genre=self.selected_flavor,
                    limit=15,
                )

                # Auto-connect and stream audio if user is in a voice channel
                voice_channel_name = None
                from services.audio_player import audio_player
                if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
                    vc, err = await audio_player.join_user_voice(interaction)
                    if vc and not err:
                        audio_player.play_track(vc, tracks[0])
                        voice_channel_name = vc.channel.name

                # Render recommendation player view with interactive playback controls
                playback_view = PlaybackView(
                    tracks=tracks,
                    author_id=self.author.id,
                    mood_name=self.selected_mood or "chill",
                    current_index=0,
                    voice_channel_name=voice_channel_name,
                )

                recommendation_embed = create_track_embed(
                    track=tracks[0],
                    current_index=0,
                    total_tracks=len(tracks),
                    mood_name=self.selected_mood or "chill",
                    voice_channel_name=voice_channel_name,
                )

                await interaction.edit_original_response(
                    embed=recommendation_embed,
                    view=playback_view,
                )

            except MusicServiceException as exc:
                # Handle anticipated domain errors (e.g. 0 tracks found, timeout, API error)
                error_embed = create_error_embed(
                    title="Could Not Fetch Music",
                    message=exc.message,
                    suggestion=exc.suggestion,
                )
                retry_view = RetryMoodView(author=self.author)
                await interaction.edit_original_response(embed=error_embed, view=retry_view)

            except Exception as exc:  # pylint: disable=broad-except
                # Safety net for unexpected runtime failures
                logger.exception("Unexpected error while fetching recommendations: %s", exc)
                error_embed = create_error_embed(
                    title="Unexpected Error",
                    message="Something went wrong while contacting the music service.",
                    suggestion="Please try running `/mood` again in a moment.",
                )
                retry_view = RetryMoodView(author=self.author)
                await interaction.edit_original_response(embed=error_embed, view=retry_view)

        return callback

    async def on_timeout(self) -> None:
        """Disables all quiz buttons when the session times out."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class RetryMoodView(discord.ui.View):
    """Fallback view shown when an error occurs, providing a quick retry button."""

    def __init__(self, author: discord.User | discord.Member, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.author = author

    @discord.ui.button(label="Try Different Mood", style=discord.ButtonStyle.primary, emoji="🔄")
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ You cannot restart someone else's quiz session.",
                ephemeral=True,
            )
            return

        new_quiz = MoodQuizView(author=self.author)
        await interaction.response.edit_message(
            embed=new_quiz.render_step_embed(),
            view=new_quiz,
        )
