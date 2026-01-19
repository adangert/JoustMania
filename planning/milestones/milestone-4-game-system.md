# Milestone 4: Game System

**Status:** Complete
**Phases:** 22, 36b, 61

## Summary

Game Coordinator architecture with abstract base class pattern supporting multiple game modes with consistent lifecycle management and per-player tracing.

## Background

JoustMania supports multiple game modes, each with unique rules but shared infrastructure:
- Player management
- Controller feedback
- Audio integration
- Win/loss detection

## Implementation

### BaseGameMode Abstract Class

Template Method pattern for consistent game lifecycle:

```python
class BaseGameMode(ABC):
    """Abstract base for all game modes."""

    async def run(self):
        """Main entry point (Template Method)."""
        await self._initialization_phase()
        await self._countdown_phase()
        await self._gameplay_phase()
        await self._teardown_phase()

    @abstractmethod
    async def _game_loop(self) -> None:
        """Subclass implements actual game logic."""
        ...

    @abstractmethod
    def get_game_name(self) -> str:
        """Return display name for tracing."""
        ...
```

### Game Lifecycle Phases

| Phase | Description | Span Name |
|-------|-------------|-----------|
| Initialization | Load settings, assign colors | `initialization_phase` |
| Countdown | 3-2-1 with audio/LED feedback | `countdown_phase` |
| Gameplay | Main game loop | `gameplay_phase` |
| Teardown | Announce winner, cleanup | `teardown_phase` |

### Supported Game Modes

| Mode | Description | Players |
|------|-------------|---------|
| **JoustFFA** | Free-for-all, last one standing | 2-10 |
| **JoustTeams** | Team-based elimination | 4-10 |
| **JoustRandomTeams** | Random team assignment | 4-10 |
| **NonStopJoust** | Continuous respawning | 2-10 |
| **Werewolf** | Hidden traitor mode | 4-10 |
| **Zombie** | Infection spreading | 3-10 |
| **Swapper** | Color-swapping chaos | 3-10 |
| **Traitor** | Secret betrayer | 4-10 |
| **Tournament** | Bracket elimination | 4-16 |

### Per-Player Tracing

Each player gets a lifecycle span tracking:
- Join time
- Warning events (near-death moments)
- Death event (with killer info if applicable)
- Survival/win status

```
gameplay_phase
├── player_mock_controller_0_lifecycle
│   ├── event: player_warning (accel=2.1)
│   └── event: player_death (accel=3.5)
├── player_mock_controller_1_lifecycle
│   └── event: player_survived
└── ...
```

## Files Changed

- `services/game_coordinator/games/base.py` - Abstract base class
- `services/game_coordinator/games/ffa.py` - Free-for-all
- `services/game_coordinator/games/teams.py` - Team modes
- `services/game_coordinator/games/nonstop_joust.py` - NonStop mode
- `services/game_coordinator/game_factory.py` - Mode instantiation

## Commits

See git history for complete list.

## Related Phases

- Phase 22: NonStop Joust game mode
- Phase 36b: Game base class (BaseGameMode)
- Phase 61: Game Coordinator refactoring
