"""
Focus & XP Gamification Cog (focus_cog.py)

Manages:
- `/focus start [minutes] [stream_music]`: Pomodoro/study sessions with ambient voice music.
- `/focus stop`: Gracefully stops the active focus session and awards partial XP.
- `/focus status`: Checks remaining time on current study session.
- `/xp [user]`: Displays detailed stats, level progress bar, and focus streak.
- `/leaderboard`: Shows the server's top focus champions and XP leaders.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, Optional, Tuple
import discord
from discord import app_commands
from discord.ext import commands

from services.audio_player import audio_player
from services.itunes_service import itunes_service
from services.xp_service import xp_service
from utils.quiz_style import create_progress_bar, create_styled_embed

logger = logging.getLogger(__name__)


class ActiveSession:
    """Represents an ongoing focus session for a user."""

    def __init__(self, user_id: int, channel_id: int, total_minutes: int, task: asyncio.Task) -> None:
        self.user_id = user_id
        self.channel_id = channel_id
        self.total_minutes = total_minutes
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.task = task

    @property
    def elapsed_minutes(self) -> int:
        elapsed = datetime.datetime.now(datetime.timezone.utc) - self.start_time
        return max(1, int(elapsed.total_seconds() // 60))

    @property
    def remaining_seconds(self) -> int:
        total_sec = self.total_minutes * 60
        elapsed_sec = (datetime.datetime.now(datetime.timezone.utc) - self.start_time).total_seconds()
        return max(0, int(total_sec - elapsed_sec))


class FocusCog(commands.Cog, name="Focus & XP"):
    """Focus timer engine and gamified XP progression."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.active_sessions: Dict[int, ActiveSession] = {}

    @app_commands.command(
        name="focus",
        description="Manage your focus sessions: start, stop, or check status.",
    )
    @app_commands.describe(
        action="What would you like to do?",
        minutes="Duration in minutes (1 to 180, default: 25)",
        stream_music="Stream focus/ambient music in your voice channel?",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="▶️ Start Focus Session", value="start"),
            app_commands.Choice(name="⏹️ Stop Current Session", value="stop"),
            app_commands.Choice(name="⏱️ Check Session Status", value="status"),
        ]
    )
    async def focus(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        minutes: Optional[app_commands.Range[int, 1, 180]] = None,
        stream_music: Optional[bool] = True,
    ) -> None:
        """Central entry point for focus timer operations."""
        duration = minutes if (minutes is not None and minutes > 0) else 25
        should_stream = stream_music if stream_music is not None else True

        if action.value == "start":
            await self._handle_start(interaction, duration, should_stream)
        elif action.value == "stop":
            await self._handle_stop(interaction)
        elif action.value == "status":
            await self._handle_status(interaction)

    async def _handle_start(self, interaction: discord.Interaction, minutes: int, stream_music: bool) -> None:
        user_id = interaction.user.id
        if user_id in self.active_sessions:
            session = self.active_sessions[user_id]
            mins_left = max(1, session.remaining_seconds // 60)
            await interaction.response.send_message(
                f"⚠️ You already have an active focus session ({mins_left}m remaining)!\n"
                "Use `/focus action: ⏹️ Stop` if you wish to end it early.",
                ephemeral=True,
            )
            return

        if minutes < 1 or minutes > 180:
            await interaction.response.send_message("❌ Focus duration must be between 1 and 180 minutes.", ephemeral=True)
            return

        # Defer immediately to prevent Discord interaction timeout
        await interaction.response.defer()

        end_timestamp = int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)).timestamp())

        is_user_in_voice = (
            stream_music
            and isinstance(interaction.user, discord.Member)
            and interaction.user.voice
            and interaction.user.voice.channel is not None
        )

        music_note = "\n🎧 *Connecting to voice channel for study music...*" if is_user_in_voice else ""

        description = (
            f"🧠 **Focus session started for {minutes} minutes!**\n\n"
            f"⏳ **Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:t>)\n"
            f"⚡ **Reward:** `{minutes * 10} XP` on completion"
            f"{music_note}\n\n"
            "*Stay disciplined and eliminate distractions. I'll notify you when time is up!*"
        )

        embed = create_styled_embed(
            title="🎯 Focus Timer Activated",
            description=description,
            color=discord.Color(0xA5D6A7),  # Serene sage green
            author=interaction.user,
            footer_text="AuraTunes • Focus Engine",
        )

        # Create background timer task for XP & session completion
        task = asyncio.create_task(self._session_timer(user_id, interaction.channel_id, minutes))
        self.active_sessions[user_id] = ActiveSession(user_id, interaction.channel_id, minutes, task)

        # Send response message immediately so Discord never times out
        msg = await interaction.followup.send(embed=embed)

        # Connect to voice and start playing meditation/focus music in background
        if is_user_in_voice:
            asyncio.create_task(self._start_focus_music(interaction, msg, minutes, end_timestamp))

    async def _start_focus_music(
        self,
        interaction: discord.Interaction,
        message: discord.WebhookMessage,
        minutes: int,
        end_timestamp: int,
    ) -> None:
        """Helper to connect to voice and stream ambient focus music without blocking interaction response."""
        try:
            vc, err = await audio_player.join_user_voice(interaction)
            if vc and not err:
                focus_tracks = await itunes_service.get_recommendations_for_mood(
                    primary_mood="focused",
                    flavor_genre="ambient",
                    limit=5,
                )
                if focus_tracks:
                    await audio_player.play_track_async(
                        vc,
                        focus_tracks[0],
                        track_queue=focus_tracks,
                        queue_index=0,
                        loop=asyncio.get_running_loop(),
                    )
                    music_note = f"\n🎧 Streaming study music in **#{vc.channel.name}** (auto-looping)."
                    updated_desc = (
                        f"🧠 **Focus session started for {minutes} minutes!**\n\n"
                        f"⏳ **Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:t>)\n"
                        f"⚡ **Reward:** `{minutes * 10} XP` on completion"
                        f"{music_note}\n\n"
                        "*Stay disciplined and eliminate distractions. I'll notify you when time is up!*"
                    )
                    updated_embed = create_styled_embed(
                        title="🎯 Focus Timer Activated",
                        description=updated_desc,
                        color=discord.Color(0xA5D6A7),
                        author=interaction.user,
                        footer_text="AuraTunes • Focus Engine",
                    )
                    await message.edit(embed=updated_embed)
        except Exception as exc:
            logger.warning("Could not auto-start focus music: %s", exc)


    async def _handle_stop(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        if user_id not in self.active_sessions:
            await interaction.response.send_message("❌ You do not have an active focus session running.", ephemeral=True)
            return

        session = self.active_sessions.pop(user_id)
        session.task.cancel()

        # Award partial XP for elapsed minutes
        completed_mins = session.elapsed_minutes
        xp_earned, leveled_up, new_level, streak = xp_service.record_focus_session(user_id, completed_mins)

        # Stop voice music if active
        vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None
        audio_player.stop_playback(vc)

        level_str = f" 🌟 **LEVEL UP! Level {new_level}!**" if leveled_up else ""
        msg = (
            f"⏹️ **Focus session ended early.**\n\n"
            f"⏱️ **Time Focused:** `{completed_mins} minutes`\n"
            f"⚡ **Partial XP Awarded:** `+{xp_earned} XP`{level_str}\n"
            f"🔥 **Focus Streak:** `{streak} day(s)`"
        )
        embed = create_styled_embed(
            title="⏸️ Focus Session Concluded",
            description=msg,
            color=discord.Color.orange(),
            author=interaction.user,
            footer_text="AuraTunes • Focus Engine",
        )
        await interaction.response.send_message(embed=embed)

    async def _handle_status(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        if user_id not in self.active_sessions:
            await interaction.response.send_message("❌ No active focus session. Start one with `/focus action: ▶️ Start`!", ephemeral=True)
            return

        session = self.active_sessions[user_id]
        rem_sec = session.remaining_seconds
        rem_min = rem_sec // 60
        rem_sec_only = rem_sec % 60
        progress_bar = create_progress_bar(session.elapsed_minutes, session.total_minutes)

        msg = (
            f"⏱️ **Time Remaining:** `{rem_min:02d}:{rem_sec_only:02d}`\n"
            f"📊 **Progress:**\n{progress_bar}\n\n"
            f"⚡ **Expected XP:** `+{session.total_minutes * 10} XP`"
        )
        embed = create_styled_embed(
            title="⏳ Active Focus Session",
            description=msg,
            color=discord.Color(0x80DEEA),
            author=interaction.user,
            footer_text="AuraTunes • Focus Engine",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _session_timer(self, user_id: int, channel_id: int, minutes: int) -> None:
        """Asynchronously waits for session completion and triggers rewards."""
        try:
            await asyncio.sleep(minutes * 60)
            if user_id in self.active_sessions:
                self.active_sessions.pop(user_id)

            xp_earned, leveled_up, new_level, streak = xp_service.record_focus_session(user_id, minutes)

            # Find the guild voice client
            guild_vc: Optional[discord.VoiceClient] = None
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel) and channel.guild:
                guild_vc = channel.guild.voice_client  # type: ignore[assignment]

            if guild_vc and guild_vc.is_connected():
                # Step 1: Stop the looping music queue.
                # stop_playback() invalidates the session token BEFORE calling
                # voice_client.stop(), so the music _after callback sees the
                # mismatch and will NOT auto-advance to the next track.
                audio_player.stop_playback(guild_vc)

                # Step 2: Wait for FFmpeg to fully tear down before playing the ding.
                await asyncio.sleep(0.75)

                # Step 3: Play the session-end ding notification.
                from services.audio_player import SESSION_END_SOUND_URL
                audio_player.play_sound(guild_vc, SESSION_END_SOUND_URL)
                logger.info("Played session-end ding for user %d", user_id)

            if channel and isinstance(channel, discord.TextChannel):
                user = self.bot.get_user(user_id)
                mention = user.mention if user else f"<@{user_id}>"

                level_bonus = f"\n\n🌟 **CONGRATULATIONS! You reached Level {new_level}!**" if leveled_up else ""
                desc = (
                    f"🎉 **Ding! Your {minutes}-minute focus session is complete!**\n\n"
                    f"⚡ **XP Earned:** `+{xp_earned} XP`\n"
                    f"🔥 **Daily Streak:** `{streak} day(s)` in a row!"
                    f"{level_bonus}\n\n"
                    "Take a well-deserved short break before starting your next session! ☕"
                )
                embed = create_styled_embed(
                    title="🏆 Focus Session Completed!",
                    description=desc,
                    color=discord.Color.green(),
                    footer_text="AuraTunes • Focus Gamification",
                )
                await channel.send(content=f"🔔 {mention}", embed=embed)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Error in focus timer task: %s", exc)



    @app_commands.command(
        name="xp",
        description="View your level, total XP, focus statistics, and daily streak.",
    )
    @app_commands.describe(user="Optional user to inspect stats for")
    async def view_xp(self, interaction: discord.Interaction, user: Optional[discord.User] = None) -> None:
        """Renders comprehensive user level card and focus milestones."""
        target_user = user or interaction.user
        profile = xp_service.get_user_profile(target_user.id)

        level = profile["level"]
        xp = profile["xp"]
        progress_pct = profile["progress_pct"]
        bar = create_progress_bar(progress_pct, 100, bar_length=12)

        description = (
            f"### 🎖️ **Level {level} Focus Explorer**\n"
            f"**Total XP:** `{xp:,} XP`\n\n"
            f"**Level Progress ({progress_pct}%):**\n"
            f"{bar}\n"
            f"> `{profile['xp_in_level']:,} / {profile['xp_needed']:,} XP to Level {level + 1}`\n\n"
            f"**🧠 Focus Stats:**\n"
            f"• Total Focus Time: `{profile['focus_minutes']} minutes` (`{round(profile['focus_minutes'] / 60, 1)} hrs`)\n"
            f"• Sessions Completed: `{profile['focus_sessions']}`\n"
            f"• Daily Streak: `🔥 {profile['focus_streak']} day(s)`\n\n"
            f"**🎮 Wordle Stats:**\n"
            f"• Puzzles Solved: `{profile['wordle_wins']} / {profile['wordle_played']}`"
        )

        embed = create_styled_embed(
            title=f"⭐ {target_user.display_name}'s Profile & Rank",
            description=description,
            color=discord.Color.gold(),
            author=target_user,
            footer_text="AuraTunes • XP & Leveling Engine",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="leaderboard",
        description="View the server leaderboard for top XP earners and study champions.",
    )
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """Displays top 10 ranked users across the bot."""
        top_users = xp_service.get_top_users(limit=10)
        if not top_users:
            await interaction.response.send_message("📊 No study stats recorded yet. Be the first with `/focus`!", ephemeral=True)
            return

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = []

        for idx, (uid, data) in enumerate(top_users):
            medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
            xp = data.get("xp", 0)
            level = max(1, int((xp / 100) ** 0.5) + 1)
            mins = data.get("focus_minutes", 0)
            streak = data.get("focus_streak", 0)
            lines.append(
                f"{medal} <@{uid}>\n"
                f"> **Level {level}** • `{xp:,} XP` • `{mins}m focused` • `🔥 {streak}d streak`"
            )

        description = "\n\n".join(lines)

        embed = create_styled_embed(
            title="🏆 AuraTunes Focus & XP Leaderboard",
            description=description,
            color=discord.Color.gold(),
            footer_text="AuraTunes • Top Focus Champions",
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Standard extension setup hook required by discord.py."""
    await bot.add_cog(FocusCog(bot))
