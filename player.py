import abc
import asyncio
import collections
import enum
import functools
import itertools
import math
import time
import typing

import psmove
import common
from numpy import linalg

NUM_WARNING_FLASHES=5
WARNING_FLASH_DURATION=0.1
RAINBOW_PHASE_DURATION=0.1

class EventType(enum.Flag):
    SENSOR = enum.auto()
    BUTTON_DOWN = enum.auto()
    BUTTON_UP = enum.auto()
    # TODO: Add trigger events

class ControllerEvent(abc.ABC):
    @abc.abstractproperty
    def type(self): raise NotImplemented()

class SensorEvent(ControllerEvent):
    """Base class for controller events."""
    def __init__(self, acceleration, jerk, gyroscope):
        self.acceleration = acceleration
        self.jerk = jerk
        self.gyroscope = gyroscope

    @property
    def type(self):
        return EventType.SENSOR

    @property
    def acceleration_magnitude(self):
        return linalg.norm(self.acceleration)

    @property
    def jerk_magnitude(self):
        return linalg.norm(self.jerk)

class ButtonDownEvent(ControllerEvent):
    """Sent when a player first presses a button."""
    def __init__(self, button: common.Button):
        self.button = button

    @property
    def type(self):
        return EventType.BUTTON_DOWN

class ButtonUpEvent(ControllerEvent):
    """Sent when a player first releases a button."""
    def __init__(self, player, button: common.Button):
        super().__init__(player)
        self.button = button

    @property
    def type(self):
        return EventType.BUTTON_UP


class ControllerState:
    """The state of inputs on a controller at one point in time."""
    def __init__(self, move):
        self.buttons = common.Button(move.get_buttons())
        self.trigger = move.get_trigger()
        self.acceleration = tuple(move.get_accelerometer_frame(psmove.Frame_SecondHalf))
        self.gyroscope = tuple(move.get_gyroscope_frame(psmove.Frame_SecondHalf))
        self.ts = time.time()

    @property
    def acceleration_magnitude(self):
        return math.sqrt(sum([ v*v for v in self.acceleration ]))

    def get_events_from_state_diff(self, prev_state):
        acc_diff = map(lambda a, b: a - b, self.acceleration, prev_state.acceleration)
        time_diff = self.ts - prev_state.ts
        jerk = tuple([ e / time_diff for e in acc_diff ])
        yield SensorEvent(self.acceleration, jerk, self.gyroscope)

        new_buttons = self.buttons & (~prev_state.buttons)
        for button in common.Button:
            if button in new_buttons:
                yield ButtonDownEvent(button)
        released_buttons = prev_state.buttons & (~self.buttons)
        for button in common.Button:
            if button in released_buttons:
                yield ButtonDownEvent(button)

# TODO: Break this out into a util library if it seems useful.
def with_lock(lock):
    """Decorator that makes a coroutine hold a lock during execution"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with lock:
                return await func(*args, **kwargs)
        return wrapper
    return decorator

class Player:
    def __init__(self, move):
        self.move_ = move
        self.color_ = common.Color.WHITE
        self.effect_lock_ = asyncio.Lock()
        self.warn_ = None
        self.effect_ = None
        self.previous_state_ = ControllerState(move)
        self.flush_events_()

    def flush_events_(self):
        while self.move_.poll(): pass

    def get_events(self) -> typing.Iterator[ControllerEvent]:
        """Returns an iterator over events currently pending on the controller."""
        self.flush_events_()
        state = ControllerState(self.move_)
        for ev in state.get_events_from_state_diff(self.previous_state_):
            ev.player = self
            yield ev
        self.previous_state_ = state
        # TODO: The moves need to be occasionally prodded to keep their leds lit.
        # If we make the piparty loop async, move this logic in there as a task.
        self.move_.update_leds()

    def set_player_color(self, color: common.Color):
        """Set's the player's color -- this is the default color we return to during play."""
        self.color_ = color
        self.set_color_(color)

    def set_color_(self, color: common.Color):
        """Changes the controller's indicator to the specified color."""
        self.move_.set_leds(*color.rgb_bytes())
        self.move_.update_leds()

    def set_rumble(self, value):
        self.move_.set_rumble(value)
        # This is apparently needed to flush the instruction out.
        self.move_.update_leds()

    def set_effect_(self, future):
        self.effect_ = asyncio.ensure_future(future)
        return self.effect_

    def cancel_effect(self):
        if self.effect_ and not self.effect_.done():
            self.effect_.cancel()

    def warn(self):
        """Issues a warning to the player."""
        if self.warn_:
            return

        @with_lock(self.effect_lock_)
        async def run():
            try:
                for i in range(NUM_WARNING_FLASHES):
                    self.set_color_(common.Color.BLACK)
                    self.set_rumble(90)
                    await asyncio.sleep(WARNING_FLASH_DURATION)
                    self.set_color_(self.color_)
                    self.set_rumble(0)
                    await asyncio.sleep(WARNING_FLASH_DURATION)
            finally:
                self.set_color_(self.color_)
                self.set_rumble(0)
                self.warn_ = None
        self.warn_ = self.set_effect_(run())

    def show_rainbow(self, duration_seconds: float):
        """Shows the victory rainbow."""
        if self.warn_:
            self.warn_.cancel()

        @with_lock(self.effect_lock_)
        async def cycle_colors():
            try:
                for color in itertools.cycle(common.PLAYER_COLORS):
                    self.set_color_(color)
                    await asyncio.sleep(RAINBOW_PHASE_DURATION)
            finally:
                self.set_color_(self.color_)
        async def run():
            try:
                await asyncio.wait_for(cycle_colors(), duration_seconds)
            except asyncio.TimeoutError:
                pass
        return self.set_effect_(run())

    def show_death(self):
        """Lets the player know they have died."""
        if self.warn_:
            self.warn_.cancel()

        @with_lock(self.effect_lock_)
        async def run():
            try:
                self.set_rumble(110)
                self.set_color_(common.Color.RED)
                await asyncio.sleep(3)
            finally:
                self.set_color_(common.Color.BLACK)
                self.set_rumble(0)
        self.set_effect_(run())

    def __str__(self):
        return '<Player %s %s>' % (self.move_, self.color_)

class PlayerCollection:
    """The set of players in a round of the game."""
    def __init__(self, players):
        self.players = players
        self.active_players = set(players)
    def kill_player(self, player: Player):
        self.active_players.remove(player)
        return player.show_death()
    def active_player_events(self, event_type: EventType):
        # consider randomizing this so players don't get an advantage by being first in the list.
        for player in list(self.active_players):
            yield from (e for e in player.get_events() if e.type in event_type)
    def cancel_effects(self):
        for player in self.players:
            player.cancel_effect()
