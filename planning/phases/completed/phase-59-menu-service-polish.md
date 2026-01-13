# Phase 59: Menu Service Polish

**Status:** ✅ COMPLETE
**Priority:** MEDIUM
**Estimated Effort:** Small-Medium (1 day)

## Goal

Address remaining implementation gaps, code quality issues, and test coverage in the menu service identified during post-Phase 58 review.

## Motivation

Phase 58 fixed critical bugs and added core reliability features. This phase focuses on polish:
- Code consistency (DRY principle)
- Feature completeness (force_all_start, web command parity)
- Visual feedback consistency (admin mode)
- Observability (StreamMenuEvents metrics)
- Test coverage

## Tasks

### Task 1: Extract GAME_MODES Constant

**Files:** `services/menu/server.py`

The game list appears in 3 places. Extract to a single class constant.

**Current (duplicated):**
```python
# Line 265 (ProcessInput)
games = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]

# Line 736 (_handle_select_press)
games = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]

# Lines 552-558 (GAME_MODE_COLORS keys)
GAME_MODE_COLORS = {
    "JoustFFA": ...,
    "JoustTeams": ...,
    ...
}
```

**Fixed:**
```python
class MenuServicer(menu_pb2_grpc.MenuServiceServicer):
    # Game modes available in the menu
    GAME_MODES = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]

    # Game mode lobby colors (Phase 39)
    GAME_MODE_COLORS = {
        "JoustFFA": (255, 140, 0),      # Orange - FFA
        "JoustTeams": (0, 100, 255),    # Blue - Team play
        "Tournament": (150, 0, 255),    # Purple - Competitive
        "Werewolf": (0, 255, 100),      # Green - Mysterious
        "NonstopJoust": (255, 50, 120), # Pink - Intense/energetic
    }
```

Then use `self.GAME_MODES` everywhere.

### Task 2: Implement force_all_start Setting

**Files:** `services/menu/server.py`

The auto-start logic should respect the `force_all_start` setting.

**Current (ignores setting):**
```python
# Line 640
if len(self.ready_controllers) >= 2 and len(self.ready_controllers) == len(self.connected_controllers):
    logger.info("All controllers ready - auto-starting game!")
    await self._handle_trigger_press(serial)
```

**Fixed:**
```python
# Check force_all_start setting
if len(self.ready_controllers) >= 2:
    should_auto_start = False

    if len(self.ready_controllers) == len(self.connected_controllers):
        # All controllers ready - always auto-start
        should_auto_start = True
    else:
        # Not all ready - check force_all_start setting
        try:
            from proto import settings_pb2, settings_pb2_grpc
            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            response = await stub.GetSetting(settings_pb2.GetSettingRequest(key="force_all_start"))
            force_all = response.value == "true"

            if not force_all:
                # Don't require all controllers - auto-start with 2+ ready
                should_auto_start = True
        except Exception as e:
            logger.warning(f"Could not check force_all_start setting: {e}")

    if should_auto_start:
        logger.info("Auto-starting game!")
        await self._handle_trigger_press(serial)
```

### Task 3: Web Selection Change Updates Lobby Colors

**Files:** `services/menu/server.py`

When game mode changes via web command, lobby colors should update.

**Add to ProcessInput, after handling web_command selection:**
```python
elif input_type == "web_command":
    command = data.get("command", "")
    span.set_attribute("command", command)

    if command == "start_game":
        self.state = menu_pb2.MenuState.GAME_STARTING
        await self._publish_event(
            "game_requested", {"game_name": self.current_selection, "source": "web"}
        )

    # Phase 59: Add select_game command for web UI
    elif command == "select_game":
        game_name = data.get("game_name", "")
        if game_name in self.GAME_MODES:
            self.current_selection = game_name
            await self._publish_event("selection_changed", {"game_name": game_name, "source": "web"})
            # Clear lobby state to trigger color update
            self.controller_lobby_state.clear()
            self.last_lobby_feedback_update.clear()
            logger.info(f"Game selected via web: {game_name}")
```

### Task 4: Restore White LED After Admin Option Cycle

**Files:** `services/menu/server.py`

After showing the option color, restore white LED.

**Current:**
```python
async def _handle_admin_cycle_option(self, serial: str):
    # ... shows option color for 1 second
    color_request = controller_manager_pb2.SetControllerColorRequest(
        serial=serial,
        color=controller_manager_pb2.RGB(r=option_color[0], g=option_color[1], b=option_color[2]),
        duration_ms=1000,
    )
    await stub.SetControllerColor(color_request)
```

**Fixed:**
```python
async def _handle_admin_cycle_option(self, serial: str):
    # ... shows option color for 1 second, then restore white
    color_request = controller_manager_pb2.SetControllerColorRequest(
        serial=serial,
        color=controller_manager_pb2.RGB(r=option_color[0], g=option_color[1], b=option_color[2]),
        duration_ms=1000,
    )
    await stub.SetControllerColor(color_request)

    # Schedule restore to white after 1 second
    async def restore_white():
        await asyncio.sleep(1.1)  # Wait for option color to finish
        if self.admin_mode_active and serial == self.admin_mode_controller:
            white_request = controller_manager_pb2.SetControllerColorRequest(
                serial=serial,
                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                duration_ms=0,
            )
            await stub.SetControllerColor(white_request)

    asyncio.create_task(restore_white())
```

### Task 5: Add StreamMenuEvents Metrics

**Files:** `services/menu/server.py`, `services/menu/metrics.py`

Add metrics for stream connections.

**In metrics.py:**
```python
# Stream metrics
stream_connections_active = Gauge(
    "menu_stream_connections_active",
    "Number of active StreamMenuEvents connections",
)

stream_events_published_total = Counter(
    "menu_stream_events_published_total",
    "Total events published to stream subscribers",
    ["event_type"],
)
```

**In server.py StreamMenuEvents:**
```python
async def StreamMenuEvents(self, request, context):
    subscriber_id = f"menu_events_{time.time()}"
    metrics.stream_connections_active.inc()  # Track active connections

    # ... existing code ...

    finally:
        metrics.stream_connections_active.dec()  # Decrement on disconnect
        # ... existing cleanup ...
```

**In _publish_event:**
```python
async def _publish_event(self, event_type: str, data: dict[str, str]):
    metrics.stream_events_published_total.labels(event_type=event_type).inc()
    # ... existing code ...
```

### Task 6: Graceful Shutdown for Background Tasks

**Files:** `services/menu/server.py`

Track and cancel background tasks on shutdown.

**In serve():**
```python
async def serve(port=50054, metrics_port=8000):
    # ... existing setup ...

    # Track background tasks for cleanup
    background_tasks = []

    metrics_task = asyncio.create_task(collect_system_metrics())
    background_tasks.append(metrics_task)

    # ... existing server setup ...

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Menu server...")

        # Cancel background tasks
        for task in background_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await menu_servicer.stop_button_monitor()
        await menu_servicer.shutdown()
        await server.stop(grace=5)
```

### Task 7: Clean Up Legacy Docstring

**Files:** `services/menu/server.py`

Update the module docstring.

**Current:**
```python
"""
Menu gRPC Server for JoustMania

Manages menu UI and user interactions as a gRPC service:
- Start/stop menu
- Process input (button presses, web commands)
- Track menu state
- Stream menu events

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""
```

**Fixed:**
```python
"""
Menu gRPC Server for JoustMania

Manages the game selection menu and lobby experience:
- Game mode selection and cycling
- Controller lobby state (connected/ready)
- LED feedback based on game mode and player state
- Admin mode for in-game configuration
- Real-time event streaming for UI updates

See services/menu/README.md for full documentation.
"""
```

### Task 8: Add Missing Unit Tests

**Files:** `services/menu/tests/test_menu_service.py` (new)

Add tests for untested functionality.

```python
"""
Unit tests for menu service (Phase 59).

Tests for:
- ProcessInput handling
- Game mode cycling
- Web commands
- Admin mode commands
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from proto import menu_pb2


class TestProcessInput:
    """Test ProcessInput RPC."""

    @pytest.mark.asyncio
    async def test_button_press_trigger_starts_game(self, menu_servicer):
        """Trigger button press should start game."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(
            input_type="button_press",
            data={"button": "trigger"}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.GAME_STARTING

    @pytest.mark.asyncio
    async def test_button_press_select_cycles_game(self, menu_servicer):
        """Select button press should cycle game mode."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(
            input_type="button_press",
            data={"button": "select"}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.current_selection == "JoustTeams"

    @pytest.mark.asyncio
    async def test_web_command_start_game(self, menu_servicer):
        """Web command should start game."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING

        request = menu_pb2.ProcessInputRequest(
            input_type="web_command",
            data={"command": "start_game"}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.GAME_STARTING

    @pytest.mark.asyncio
    async def test_reset_menu_cancels_game_start(self, menu_servicer):
        """Reset menu should cancel GAME_STARTING state."""
        menu_servicer.state = menu_pb2.MenuState.GAME_STARTING

        request = menu_pb2.ProcessInputRequest(
            input_type="reset_menu",
            data={}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.RUNNING


class TestGameModeCycling:
    """Test game mode cycling."""

    def test_game_modes_constant_exists(self, menu_servicer):
        """GAME_MODES constant should exist."""
        assert hasattr(menu_servicer, 'GAME_MODES')
        assert len(menu_servicer.GAME_MODES) == 5

    def test_all_game_modes_have_colors(self, menu_servicer):
        """All game modes should have colors defined."""
        for mode in menu_servicer.GAME_MODES:
            assert mode in menu_servicer.GAME_MODE_COLORS


class TestAdminModeTimeout:
    """Test admin mode timeout (Phase 58)."""

    @pytest.mark.asyncio
    async def test_admin_mode_times_out(self, menu_servicer):
        """Admin mode should exit after 60 seconds."""
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = "test_serial"
        menu_servicer.admin_mode_entry_time = 0  # Set to epoch (will be > 60s ago)

        # Create mock controller state
        controller = MagicMock()
        controller.serial = "test_serial"
        controller.trigger_pressed = False
        controller.move_pressed = False
        controller.cross_pressed = False
        controller.circle_pressed = False
        controller.square_pressed = False
        controller.triangle_pressed = False
        controller.ps_pressed = False

        menu_servicer.controller_button_states["test_serial"] = {
            "trigger": False, "move": False, "cross": False,
            "circle": False, "square": False, "triangle": False, "ps": False
        }

        await menu_servicer._process_button_state(controller)

        assert not menu_servicer.admin_mode_active
```

## Testing

### Manual Testing Checklist

- [ ] Game mode cycling uses constant (no duplication)
- [ ] Auto-start respects force_all_start=true (waits for all)
- [ ] Auto-start with force_all_start=false (starts with 2+)
- [ ] Web select_game command updates lobby colors
- [ ] Admin option cycling restores white LED
- [ ] StreamMenuEvents metrics appear in Prometheus
- [ ] Graceful shutdown cancels all background tasks

### Automated Tests

- [ ] Existing tests pass
- [ ] New ProcessInput tests pass
- [ ] Game mode constant tests pass
- [ ] Admin timeout test passes

## Success Criteria

- ✅ GAME_MODES constant used everywhere (DRY)
- ✅ force_all_start setting respected in auto-start
- ✅ Web commands update lobby colors
- ✅ Admin mode visual feedback consistent
- ✅ StreamMenuEvents has metrics
- ✅ Clean shutdown for all background tasks
- ✅ Docstring updated
- ✅ Test coverage improved

## Dependencies

- Phase 58 (Menu Service Improvements) - ✅ Complete

## Performance Impact

**Negligible:**
- GAME_MODES constant: No runtime impact
- force_all_start check: One gRPC call on ready state change
- Restore white LED: One async sleep + gRPC call
- Stream metrics: Counter increment per event

## Notes

- These are polish items, not critical fixes
- Maintains backward compatibility
- Improves code maintainability and test coverage

## Completion Summary

**Completed:** 2026-01-13

### Changes Made

1. **Extracted GAME_MODES constant** - Single source of truth for game mode list, used in ProcessInput, _handle_select_press, and validated against GAME_MODE_COLORS

2. **Implemented force_all_start setting** - Auto-start now checks the setting: if false, starts with 2+ ready controllers; if true, waits for all

3. **Added select_game web command** - Web UI can now directly select a game mode, and lobby colors update accordingly

4. **Restored white LED after admin option cycle** - Scheduled task restores white LED 1.1 seconds after showing option color

5. **Added StreamMenuEvents metrics** - `stream_connections_active` gauge and `stream_events_published_total` counter

6. **Added graceful shutdown** - Background tasks (metrics collection) are properly cancelled on shutdown

7. **Updated module docstring** - Removed legacy reference to Phase 8a, added reference to README

8. **Added unit tests** - TestProcessInput (6 tests), TestGameModesConstant (3 tests), TestAdminModeTimeout (1 test)

### Files Modified

- `services/menu/server.py` - All implementation changes
- `services/menu/metrics.py` - Stream metrics
- `services/menu/tests/test_lobby_feedback.py` - New test classes
