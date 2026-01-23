"""LED control utilities for the Menu service."""

import asyncio
import logging

import grpc.aio

logger = logging.getLogger(__name__)


# Game mode lobby colors - each game mode has a distinct color
GAME_MODE_COLORS: dict[str, tuple[int, int, int]] = {
    "JoustFFA": (255, 140, 0),  # Orange - FFA
    "JoustTeams": (0, 100, 255),  # Blue - Team play
    "JoustRandomTeams": (0, 200, 255),  # Cyan - Random teams
    "Swapper": (255, 0, 255),  # Magenta - Team switching
    "Werewolf": (0, 255, 100),  # Green - Mysterious
    "Traitor": (128, 0, 128),  # Dark purple - Betrayal
    "Zombie": (100, 100, 100),  # Gray - Undead
    "Commander": (255, 0, 0),  # Red - Leadership
    "FightClub": (255, 255, 0),  # Yellow - Arena combat
    "Tournament": (150, 0, 255),  # Purple - Competitive
    "NonstopJoust": (255, 50, 120),  # Pink - Intense/energetic
    "SpeedBomb": (255, 100, 0),  # Orange-red - Explosive
}

# Default color when game mode not found
DEFAULT_COLOR: tuple[int, int, int] = (255, 140, 0)  # Orange

# Dim factor for connected (not ready) state
DIM_FACTOR: float = 0.3


class LedController:
    """
    Manages LED colors for controllers in the menu/lobby.

    Uses bidirectional button stream for fast updates with RPC fallback.
    """

    def __init__(self, controller_channel: grpc.aio.Channel):
        """
        Initialize LED controller.

        Args:
            controller_channel: gRPC channel to ControllerManager service
        """
        self.controller_channel = controller_channel

        # Button stream state (set externally when stream is established)
        self._stream_queue: asyncio.Queue | None = None
        self._stream_lock: asyncio.Lock = asyncio.Lock()

    def set_stream(self, queue: asyncio.Queue | None, lock: asyncio.Lock | None = None) -> None:
        """
        Set the button stream queue for fast LED updates.

        Called by MenuServicer when the bidirectional stream is established.

        Args:
            queue: asyncio.Queue for outbound stream messages, or None to disable
            lock: Lock for thread-safe queue access (uses internal lock if not provided)
        """
        self._stream_queue = queue
        if lock is not None:
            self._stream_lock = lock

    def get_game_color(self, game_mode: str) -> tuple[int, int, int]:
        """
        Get the LED color for a game mode.

        Args:
            game_mode: Name of the game mode

        Returns:
            RGB tuple for the game mode's color
        """
        return GAME_MODE_COLORS.get(game_mode, DEFAULT_COLOR)

    def dim_color(self, color: tuple[int, int, int], factor: float = DIM_FACTOR) -> tuple[int, int, int]:
        """
        Dim a color by a factor.

        Args:
            color: RGB tuple to dim
            factor: Brightness factor (0.0-1.0)

        Returns:
            Dimmed RGB tuple
        """
        return (
            int(color[0] * factor),
            int(color[1] * factor),
            int(color[2] * factor),
        )

    async def send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """
        Send base color via bidirectional button stream.

        Args:
            serial: Controller serial number
            color: RGB tuple (r, g, b)

        Returns:
            True if sent successfully, False if stream not available
        """
        from proto import controller_manager_pb2

        async with self._stream_lock:
            if self._stream_queue is None:
                return False

            try:
                msg = controller_manager_pb2.ButtonEventStreamControl(
                    base_color=controller_manager_pb2.ControllerColorConfig(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    )
                )
                self._stream_queue.put_nowait(msg)
                logger.debug(f"Sent base color for {serial}: {color}")
                return True
            except asyncio.QueueFull:
                logger.warning(f"Button stream queue full, could not send base color for {serial}")
                return False

    async def send_game_effect(self, serial: str, effect: int) -> bool:
        """
        Send game effect via bidirectional button stream.

        Args:
            serial: Controller serial number
            effect: GameEffect enum value

        Returns:
            True if sent successfully, False if stream not available
        """
        from proto import controller_manager_pb2

        async with self._stream_lock:
            if self._stream_queue is None:
                return False

            try:
                msg = controller_manager_pb2.ButtonEventStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=effect,
                    )
                )
                self._stream_queue.put_nowait(msg)
                logger.debug(f"Sent game effect for {serial}: {effect}")
                return True
            except asyncio.QueueFull:
                logger.warning(f"Button stream queue full, could not send game effect for {serial}")
                return False

    async def set_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """
        Set controller color via stream.

        Args:
            serial: Controller serial number
            color: RGB tuple (r, g, b)

        Returns:
            True if successful, False if stream not available
        """
        return await self.send_base_color(serial, color)

    async def set_connected_color(self, serial: str, game_mode: str) -> bool:
        """
        Set controller to dim (connected but not ready) color.

        Args:
            serial: Controller serial number
            game_mode: Current game mode name

        Returns:
            True if successful
        """
        base_color = self.get_game_color(game_mode)
        dim_color = self.dim_color(base_color)
        return await self.set_color(serial, dim_color)

    async def set_ready_color(self, serial: str, game_mode: str) -> bool:
        """
        Set controller to bright (ready) color.

        Args:
            serial: Controller serial number
            game_mode: Current game mode name

        Returns:
            True if successful
        """
        color = self.get_game_color(game_mode)
        return await self.set_color(serial, color)

    async def set_admin_color(self, serial: str) -> bool:
        """
        Set controller to admin mode color (white).

        Args:
            serial: Controller serial number

        Returns:
            True if successful
        """
        return await self.set_color(serial, (255, 255, 255))
