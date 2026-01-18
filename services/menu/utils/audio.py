"""Audio utilities for the Menu service."""

import logging

import grpc.aio

from lib.types import Sound

logger = logging.getLogger(__name__)


# Game mode voice announcements
GAME_MODE_VOICE: dict[str, Sound] = {
    "JoustFFA": Sound.MENU_VOX_JOUST_FFA,
    "JoustTeams": Sound.MENU_VOX_JOUST_TEAMS,
    "JoustRandomTeams": Sound.MENU_VOX_RANDOM_TEAMS,
    "Swapper": Sound.MENU_VOX_SWAPPER,
    "Werewolf": Sound.MENU_VOX_WEREWOLVES,
    "Traitor": Sound.MENU_VOX_TRAITOR,
    "Zombie": Sound.MENU_VOX_ZOMBIES,
    "Commander": Sound.MENU_VOX_COMMANDER,
    "FightClub": Sound.MENU_VOX_FIGHT_CLUB,
    "Tournament": Sound.MENU_VOX_TOURNAMENT,
    "NonstopJoust": Sound.MENU_VOX_NONSTOP_JOUST,
    "SpeedBomb": Sound.MENU_VOX_NINJABOMB,
}


class AudioHelper:
    """
    Manages audio playback for the Menu service.

    Provides methods for playing sounds, voice announcements, and lobby music.
    """

    def __init__(self, audio_channel: grpc.aio.Channel):
        """
        Initialize audio helper.

        Args:
            audio_channel: gRPC channel to Audio service
        """
        self.audio_channel = audio_channel
        self.lobby_music_track_id: str | None = None

    async def play_sound(self, sound: str | Sound, volume: float = 0.8) -> None:
        """
        Play a sound effect via the audio service (fire-and-forget).

        Args:
            sound: Sound enum or relative path to audio file
            volume: Volume level 0.0-1.0
        """
        try:
            from proto import audio_pb2, audio_pb2_grpc

            # Convert Sound enum to string value if needed
            sound_name = sound.value if isinstance(sound, Sound) else sound

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)
            await stub.PlaySound(
                audio_pb2.PlaySoundRequest(
                    file_path=sound_name,
                    volume=volume,
                    priority=audio_pb2.AudioPriority.HIGH,
                )
            )
            logger.debug(f"Played sound: {sound_name}")
        except Exception as e:
            logger.debug(f"Could not play sound {sound}: {e}")

    async def play_voice(self, voice: str | Sound, volume: float = 0.9) -> None:
        """
        Play a voice announcement.

        Args:
            voice: Sound enum or voice file name (audio service resolves the path)
            volume: Volume level 0.0-1.0
        """
        await self.play_sound(voice, volume)

    async def play_game_mode_voice(self, game_mode: str) -> None:
        """
        Play the voice announcement for a game mode.

        Args:
            game_mode: Name of the game mode
        """
        voice = GAME_MODE_VOICE.get(game_mode)
        if voice:
            await self.play_voice(voice)

    async def start_lobby_music(self) -> None:
        """
        Start quiet background music for the lobby/menu.

        Uses a lower volume than game music for a relaxed atmosphere.
        """
        try:
            from proto import audio_pb2, audio_pb2_grpc

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)

            # Set lobby volume (quieter than game)
            await stub.SetVolume(audio_pb2.SetVolumeRequest(volume=0.4))

            # Start lobby music
            response = await stub.PlayMusic(
                audio_pb2.PlayMusicRequest(
                    file_pattern="Menu/music/*.wav",
                    loop=True,
                    tempo=1.0,
                    priority=audio_pb2.AudioPriority.LOW,
                )
            )

            if response.success:
                self.lobby_music_track_id = response.track_id
                logger.info(f"Lobby music started: {response.track_id}")
            else:
                logger.warning(f"Failed to start lobby music: {response.error}")

        except Exception as e:
            logger.debug(f"Could not start lobby music: {e}")

    async def stop_lobby_music(self) -> None:
        """Stop lobby music when game starts."""
        try:
            from proto import audio_pb2, audio_pb2_grpc

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)

            # Stop music (empty track_id stops any playing music)
            await stub.StopMusic(audio_pb2.StopMusicRequest(track_id=""))
            self.lobby_music_track_id = None
            logger.info("Lobby music stopped")

        except Exception as e:
            logger.debug(f"Could not stop lobby music: {e}")
