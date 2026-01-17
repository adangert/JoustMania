"""
JoustMania Core Types

Pure data types and enums used across the application.
No hardware dependencies.
"""

import asyncio
import functools
import traceback
from collections.abc import Callable, Coroutine
from enum import Enum, Flag
from typing import Any, TypeVar

SETTINGSFILE = "joustsettings.yaml"


def lerp(a: float, b: float, p: float) -> float:
    """Linear interpolation between a and b."""
    return a * (1 - p) + b * p


class Games(Enum):
    """Available game modes."""

    JoustFFA = (0, "Joust Free-for-All", 2)
    JoustTeams = (1, "Joust Teams", 3)
    JoustRandomTeams = (2, "Joust Random Teams", 3)
    Traitor = (3, "Traitors", 4)
    Werewolf = (4, "Werewolf", 3)
    Zombies = (5, "Zombies", 4)
    Commander = (6, "Commander", 4)
    Swapper = (7, "Swapper", 3)
    FightClub = (8, "Fight Club", 2)
    Tournament = (9, "Tournament", 3)
    NonStop = (10, "Non Stop Joust", 2)
    Ninja = (11, "Ninja Bomb", 2)
    Random = (12, "Random", 2)

    def __new__(cls, value: int, pretty_name: str, min_players: int) -> "Games":
        """This odd constructor lets us keep Foo.value as an integer, but also
        add some extra properties to each option."""
        obj = object.__new__(cls)
        obj._value_ = value
        obj.pretty_name = pretty_name
        obj.minimum_players = min_players
        return obj

    def next(self) -> "Games":
        """Return the next game mode after this one in the list. Wraps around after hitting bottom."""
        return Games((self.value + 1) % len(Games))

    def previous(self) -> "Games":
        """Return the previous game mode after this one in the list. Wraps around after hitting bottom."""
        return Games((self.value - 1) % len(Games))

    def find(self, str_name: str) -> "Games | None":
        """Find game by pretty name."""
        for game in Games:
            if game.pretty_name == str_name:
                return game
        return None


class Status(Enum):
    """Controller status states."""

    ALIVE = 0  # Tracking move and can be killed
    DIED = 1  # Just died, will move to dead
    DEAD = 2  # Dead, will revive if enabled
    REVIVED = 3  # Just revived and will play sound
    RUMBLE = 4  # Will rumble
    ON = 5  # Team color and not polling
    OFF = 6  # Black and not polling


class Opts(Enum):
    """Common options (0-5 for common, 6+ for custom)."""

    BUTTON = 0  # Buttons that are currently pressed TODO - Not being used
    HOLDING = 1  # Whether buttons are being held
    SELECTION = 2  # What those buttons represent for this game
    STATUS = 3  # Status of the move

    # Battery level constants for webui
    @staticmethod
    def battery_levels_dict() -> dict[int, str]:
        """Return battery levels without psmove dependency."""
        return {
            0: "Low",
            1: "20%",
            2: "40%",
            3: "60%",
            4: "80%",
            5: "100%",
            6: "Charging",
            7: "Charged",
        }


class Sensitivity(Enum):
    """Sensitivity levels."""

    ULTRA_SLOW = 0
    SLOW = 1
    MID = 2
    FAST = 3
    ULTRA_FAST = 4


class GameEvent(str, Enum):
    """
    Game lifecycle event types.

    Used by game coordinator to publish events and by menu/supervisor to subscribe.
    String enum for easy use in protobuf messages and logging.
    """

    # Game lifecycle - published by server/games
    GAME_START = "game_start"  # StartGame RPC received, before game setup
    GAME_STARTING = "game_starting"  # Game setup begins (pre-countdown)
    GAME_STARTED = "game_started"  # Game loop begins (post-countdown)
    GAME_ENDED = "game_ended"  # Game finished normally
    GAME_ERROR = "game_error"  # Game ended due to error

    # Player events - published by games
    PLAYER_DEATH = "player_death"
    PLAYER_REVIVE = "player_revive"
    PLAYER_OUT = "player_out"  # Player eliminated (no more lives)
    PLAYER_ANALYTICS = "player_analytics"  # Analytics summary for a player at game end

    # Game phase events
    COUNTDOWN_START = "countdown_start"
    COUNTDOWN_END = "countdown_end"
    PLAYERS_INITIALIZED = "players_initialized"

    # Scoring events
    SCORE_UPDATE = "score_update"
    GAME_WINNER = "game_winner"
    GAME_TIE = "game_tie"

    # Team events (for team games)
    TEAM_FORMATION_START = "team_formation_start"
    TEAM_FORMATION_END = "team_formation_end"
    TEAM_ELIMINATED = "team_eliminated"

    @classmethod
    def is_game_starting(cls, event_type: str) -> bool:
        """Check if event indicates game is starting (any start phase)."""
        return event_type in (cls.GAME_START, cls.GAME_STARTING, cls.GAME_STARTED)

    @classmethod
    def is_game_ending(cls, event_type: str) -> bool:
        """Check if event indicates game is ending."""
        return event_type in (cls.GAME_ENDED, cls.GAME_ERROR)


def get_game_name(value: int) -> str | None:
    """Get game name by value."""
    for game in Games:
        if game.value == value:
            return game.pretty_name
    return None


# Game name normalization mapping for display in UI and tracing
# Maps various input formats to canonical display names
GAME_DISPLAY_NAMES = {
    # FFA variants
    "ffa": "Free-For-All",
    "free-for-all": "Free-For-All",
    "joust free-for-all": "Free-For-All",
    # Teams variants
    "teams": "Teams",
    "joust teams": "Teams",
    # Random Teams variants
    "random teams": "Random Teams",
    "joust random teams": "Random Teams",
    "random_teams": "Random Teams",
    # Nonstop Joust variants
    "nonstop": "Nonstop Joust",
    "nonstop joust": "Nonstop Joust",
    "nonstopjoust": "Nonstop Joust",
    "non stop joust": "Nonstop Joust",
}


def get_game_display_name(game_name: str) -> str:
    """
    Get canonical display name for a game mode.

    Args:
        game_name: Game name in any format (case-insensitive)

    Returns:
        Canonical display name, or original name if not found

    Examples:
        >>> get_game_display_name("FFA")
        "Free-For-All"
        >>> get_game_display_name("joust teams")
        "Teams"
    """
    return GAME_DISPLAY_NAMES.get(game_name.lower(), game_name)


class Button(Flag):
    """Controller buttons (hardware-independent constants)."""

    NONE = 0

    # Shape buttons (values from psmove but defined here for independence)
    TRIANGLE = 0x10
    CIRCLE = 0x20
    CROSS = 0x40
    SQUARE = 0x80

    SELECT = 0x100
    START = 0x200

    SYNC = 0x10000  # PS button
    MIDDLE = 0x08  # Move button
    TRIGGER = 0x04  # Trigger

    SHAPES = TRIANGLE | CIRCLE | CROSS | SQUARE
    UPDATE = SELECT | START


all_shapes = [Button.TRIANGLE, Button.CIRCLE, Button.CROSS, Button.SQUARE]


class Color(Enum):
    """Common colors lifted from https://xkcd.com/color/rgb/."""

    BLACK = 0x000000
    WHITE = 0xFFFFFF
    RED = 0xFF0000

    GREEN = 0x00FF00
    BLUE = 0x0000FF
    YELLOW = 0xFFFF14
    PURPLE = 0x7E1E9C
    ORANGE = 0xF97306
    PINK = 0xFF81C0
    TURQUOISE = 0x06C2AC
    BROWN = 0x653700

    def rgb_bytes(self) -> tuple[int, int, int]:
        """Convert color to RGB byte tuple."""
        v = self.value
        return v >> 16, (v >> 8) & 0xFF, v & 0xFF


# Red is reserved for warnings/knockouts.
PLAYER_COLORS = [c for c in Color if c not in (Color.RED, Color.WHITE, Color.BLACK)]

# Type variable for async decorator
T = TypeVar("T")


def async_print_exceptions(
    f: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wraps a coroutine to print exceptions (other than cancellations)."""

    @functools.wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await f(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except:
            traceback.print_exc()
            raise

    return wrapper


class GamePace:
    """Represents a pace the game is played at."""

    __slots__ = ["tempo", "warn_threshold", "death_threshold"]

    def __init__(self, tempo: float, warn_threshold: float, death_threshold: float) -> None:
        self.tempo = tempo
        self.warn_threshold = warn_threshold
        self.death_threshold = death_threshold

    def __str__(self) -> str:
        return "<GamePace tempo=%s, warn=%s, death=%s>" % (
            self.tempo,
            self.warn_threshold,
            self.death_threshold,
        )


# TODO: These are placeholder values.
SLOW_PACE = GamePace(tempo=0.4, warn_threshold=2, death_threshold=4)
MEDIUM_PACE = GamePace(tempo=1.0, warn_threshold=3, death_threshold=5)
FAST_PACE = GamePace(tempo=1.5, warn_threshold=5, death_threshold=9)
FREEZE_PACE = GamePace(tempo=0, warn_threshold=1.1, death_threshold=1.2)


REQUIRED_SETTINGS = [
    "play_audio",
    "move_can_be_admin",
    "current_game",
    "enforce_minimum",
    "sensitivity",
    "play_instructions",
    "random_modes",
    "color_lock",
    "color_lock_choices",
    "red_on_kill",
    "random_teams",
    "menu_voice",
    "random_team_size",
    "force_all_start",
]
