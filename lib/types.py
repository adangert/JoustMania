"""
JoustMania Core Types

Pure data types and enums used across the application.
No hardware dependencies.
"""

from enum import Enum


class Games(Enum):
    """
    Available game modes.

    Each member has:
    - value: Integer ID for serialization
    - pretty_name: Human-readable display name
    - minimum_players: Minimum players required

    Use Games.from_name() to resolve any alias to a Games member.
    """

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

    @classmethod
    def from_name(cls, name: str) -> "Games | None":
        """
        Resolve any game name alias to a Games enum member.

        Supports various naming formats (case-insensitive):
        - Enum names: "JoustFFA", "NonStop"
        - Pretty names: "Joust Free-for-All", "Non Stop Joust"
        - Short names: "FFA", "Teams", "Nonstop"
        - Snake case: "fight_club", "random_teams"

        Args:
            name: Game name in any supported format

        Returns:
            Games enum member or None if not found

        Examples:
            >>> Games.from_name("FFA")
            Games.JoustFFA
            >>> Games.from_name("joust free-for-all")
            Games.JoustFFA
            >>> Games.from_name("NonStop")
            Games.NonStop
        """
        if not name:
            return None

        name_lower = name.lower()

        # Check each game mode for direct matches
        for game in cls:
            # Direct enum name match
            if name_lower == game.name.lower():
                return game
            # Pretty name match (exact)
            if name_lower == game.pretty_name.lower():
                return game

        # Normalize for alias lookup (underscores/dashes -> spaces)
        name_normalized = name_lower.replace("_", " ").replace("-", " ")

        # Check alias mappings
        return _GAME_ALIASES.get(name_normalized)

    @classmethod
    def is_valid(cls, name: str) -> bool:
        """Check if a game name is valid (resolves to a Games member)."""
        return cls.from_name(name) is not None

    @classmethod
    def all_names(cls) -> list[str]:
        """Get list of all enum member names."""
        return [game.name for game in cls]


# Alias mappings for Games.from_name() - maps lowercase aliases to Games members
# Built after class definition to reference enum members
_GAME_ALIASES: dict[str, "Games"] = {}


def _init_game_aliases() -> None:
    """Initialize game alias mappings."""
    aliases = {
        # FFA aliases
        "ffa": Games.JoustFFA,
        "free for all": Games.JoustFFA,
        "joust ffa": Games.JoustFFA,
        # Teams aliases
        "teams": Games.JoustTeams,
        "joust teams": Games.JoustTeams,
        # Random Teams aliases
        "random teams": Games.JoustRandomTeams,
        "joust random teams": Games.JoustRandomTeams,
        "randomteams": Games.JoustRandomTeams,
        # Traitor aliases
        "traitor": Games.Traitor,
        "traitors": Games.Traitor,
        # Werewolf aliases
        "werewolf": Games.Werewolf,
        "werewolves": Games.Werewolf,
        # Zombies aliases
        "zombie": Games.Zombies,
        "zombies": Games.Zombies,
        # Commander aliases
        "commander": Games.Commander,
        # Swapper aliases
        "swapper": Games.Swapper,
        # Fight Club aliases
        "fight club": Games.FightClub,
        "fightclub": Games.FightClub,
        "fight_club": Games.FightClub,
        # Tournament aliases
        "tournament": Games.Tournament,
        # NonStop aliases
        "nonstop": Games.NonStop,
        "nonstop joust": Games.NonStop,
        "nonstopjoust": Games.NonStop,
        "non stop joust": Games.NonStop,
        "non stop": Games.NonStop,
        # Ninja aliases
        "ninja": Games.Ninja,
        "ninja bomb": Games.Ninja,
        "ninjabomb": Games.Ninja,
        "speedbomb": Games.Ninja,
        # Random aliases
        "random": Games.Random,
    }
    _GAME_ALIASES.update(aliases)


_init_game_aliases()


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
    """Common options for controller state tracking."""

    # Note: Value 0 was previously BUTTON, removed as unused
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
    """
    Sensitivity levels for movement detection.

    Lower values = more sensitive (easier to die)
    Higher values = less sensitive (harder to die)

    Used as index into threshold arrays in game_coordinator/games/base.py.
    """

    ULTRA_SLOW = 0  # Most sensitive, tightest thresholds
    SLOW = 1  # High sensitivity
    MEDIUM = 2  # Default (balanced)
    FAST = 3  # Low sensitivity
    ULTRA_FAST = 4  # Least sensitive, loosest thresholds


class Sound(str, Enum):
    """
    Sound names for the audio service.

    Use these enums instead of string literals for type safety.
    The audio service resolves these to actual file paths, handling:
    - Voice selection (aaron/ivy) for VOX sounds
    - Directory lookup (sounds/ vs vox/) based on sound type

    Naming convention:
    - VOX_* for voice announcements (voice-dependent)
    - SFX_* for sound effects (not voice-dependent)
    """

    # Victory/End sounds (VOX)
    VOX_CONGRATULATIONS = "congratulations"
    VOX_GAME_OVER = "game_over"
    VOX_HUMAN_WIN = "human win"
    VOX_WEREWOLF_WIN = "werewolf win"
    VOX_TRAITOR_WIN = "traitor win"

    # Team win sounds (VOX)
    VOX_BLUE_TEAM_WIN = "blue team win"
    VOX_RED_TEAM_WIN = "red team win"
    VOX_GREEN_TEAM_WIN = "green team win"
    VOX_YELLOW_TEAM_WIN = "yellow team win"
    VOX_CYAN_TEAM_WIN = "cyan team win"
    VOX_MAGENTA_TEAM_WIN = "magenta team win"

    # Time announcements (VOX)
    VOX_1_MINUTE = "1 minute"
    VOX_3_MINUTES = "3 minutes"
    VOX_5_MINUTES = "5 minutes"

    # Werewolf announcements (VOX)
    VOX_10_WEREWOLF = "10 werewolf"
    VOX_30_WEREWOLF = "30 werewolf"
    VOX_WEREWOLF_INTRO = "werewolf intro"
    VOX_WEREWOLF_REVEAL = "werewolf reveal"

    # Other VOX sounds
    VOX_FAKEDOUT = "Fakedout"
    VOX_FAKEDOUT_COUNTER = "FakedoutCounter"
    VOX_COUNTERED = "countered"
    VOX_EXPLOSION_DEATH = "explosiondeath"

    # Sound effects (SFX)
    SFX_EXPLOSION = "Explosion34"
    SFX_EXPLOSION_22 = "Explosion22"
    SFX_BEEP = "beep_loud"  # No separate beep.wav exists, use beep_loud
    SFX_BEEP_LOUD = "beep_loud"
    SFX_START = "start"
    SFX_START3 = "start3"
    SFX_DEATH = "death"
    SFX_JOIN = "join"
    SFX_TEAMS_FORM = "teams_form"
    SFX_WOLFDOWN = "wolfdown"
    SFX_SHOTGUN_FOUND = "shotgun found"
    SFX_TRAITOR_INTRO = "traitor_intro"

    # Zombie game sounds (in Zombie/vox/)
    VOX_ZOMBIE_VICTORY = "zombie_victory"
    VOX_ZOMBIE_DEATH = "zombie_death"
    VOX_HUMAN_VICTORY = "human_victory"
    # Time announcements (in Zombie/vox/)
    VOX_ZOMBIE_ONE_MINUTE = "1 minute"
    VOX_ZOMBIE_THIRTY_SECONDS = "30 seconds"
    VOX_ZOMBIE_TEN_SECONDS = "10 seconds left"

    # Fight Club game sounds (in Fight_Club/vox/)
    VOX_FIGHT_CLUB_5_ROUNDS = "5_rounds"
    VOX_FIGHT_CLUB_LAST_ROUND = "last_round"
    VOX_FIGHT_CLUB_GAME_OVER = "game_over"
    VOX_FIGHT_CLUB_TIE_GAME = "tie_game"

    # Menu sensitivity sounds (in Menu/sounds/)
    # Only 3 audio files exist, so ultra levels map to slow/fast
    MENU_SFX_SENSITIVITY_SLOW = "slow_sensitivity"
    MENU_SFX_SENSITIVITY_MID = "mid_sensitivity"
    MENU_SFX_SENSITIVITY_FAST = "fast_sensitivity"

    # Menu voice announcements - game mode selection (in Menu/vox/)
    MENU_VOX_JOUST_FFA = "menu Joust FFA"
    MENU_VOX_JOUST_TEAMS = "menu Joust Teams"
    MENU_VOX_RANDOM_TEAMS = "menu Joust Random Teams"
    MENU_VOX_SWAPPER = "menu Swapper"
    MENU_VOX_WEREWOLVES = "menu Werewolves"
    MENU_VOX_TRAITOR = "menu Traitor"
    MENU_VOX_ZOMBIES = "menu Zombies"
    MENU_VOX_COMMANDER = "menu Commander"
    MENU_VOX_FIGHT_CLUB = "menu FightClub"
    MENU_VOX_TOURNAMENT = "menu Tournament"
    MENU_VOX_NONSTOP_JOUST = "menu NonStopJoust"
    MENU_VOX_NINJABOMB = "menu ninjabomb"
    MENU_VOX_RANDOM = "menu Random"

    # Menu voice announcements - instructions
    MENU_VOX_INSTRUCTIONS_ON = "instructions_on"
    MENU_VOX_INSTRUCTIONS_OFF = "instructions_off"

    # Menu voice announcements - game instructions
    MENU_VOX_FFA_INSTRUCTIONS = "FFA-instructions"
    MENU_VOX_TEAMS_INSTRUCTIONS = "Teams-instructions"
    MENU_VOX_SWAPPER_INSTRUCTIONS = "Swapper-instructions"
    MENU_VOX_TOURNAMENT_INSTRUCTIONS = "Tournament-instructions"
    MENU_VOX_TRAITOR_INSTRUCTIONS = "Traitor-instructions"
    MENU_VOX_WEREWOLF_INSTRUCTIONS = "werewolf-instructions"
    MENU_VOX_ZOMBIE_INSTRUCTIONS = "zombie-instructions"
    MENU_VOX_COMMANDER_INSTRUCTIONS = "commander-instructions"
    MENU_VOX_NINJABOMB_INSTRUCTIONS = "Ninjabomb-instructions"

    # Menu voice announcements - other
    MENU_VOX_NOT_ENOUGH_PLAYERS = "notenoughplayers"
    MENU_VOX_ADDED_RANDOM = "added_random"
    MENU_VOX_REMOVED_RANDOM = "removed_random"

    # Menu voice announcements - sensitivity levels (in Menu/vox/)
    # Note: "ultra_high" means ultra-high sensitivity (slow movement allowed)
    MENU_VOX_SENSITIVITY_ULTRA_HIGH = "ultra_high"
    MENU_VOX_SENSITIVITY_HIGH = "high"
    MENU_VOX_SENSITIVITY_MEDIUM = "medium"
    MENU_VOX_SENSITIVITY_LOW = "low"
    MENU_VOX_SENSITIVITY_ULTRA_LOW = "ultra_low"


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
    GAME_FORCE_ENDED = "game_force_ended"  # Game ended via ForceEndGame RPC
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
        return event_type in (cls.GAME_ENDED, cls.GAME_FORCE_ENDED, cls.GAME_ERROR)


def get_game_display_name(game_name: str) -> str:
    """
    Get display name for a game mode using the Games enum.

    Args:
        game_name: Game name in any format (case-insensitive)

    Returns:
        The game's pretty_name, or original name if not found

    Examples:
        >>> get_game_display_name("FFA")
        "Joust Free-for-All"
        >>> get_game_display_name("JoustTeams")
        "Joust Teams"
    """
    game = Games.from_name(game_name)
    return game.pretty_name if game else game_name
