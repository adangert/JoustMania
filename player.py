import asyncio
import collections
import functools
import itertools
import math
import typing

import psmove
import common

NUM_WARNING_FLASHES=5
WARNING_FLASH_DURATION=0.1
RAINBOW_PHASE_DURATION=0.1

class ControllerState:
    """The state of inputs on a controller at one point in time."""
    __slots__ = ['buttons', 'trigger', 'acceleration']

    def __init__(self, move):
        self.buttons = common.Button(move.get_buttons())
        self.trigger = move.get_trigger() / 100
        self.acceleration = move.get_accelerometer_frame(psmove.Frame_SecondHalf)

    @property
    def acceleration_magnitude(self):
        return math.sqrt(sum([ v*v for v in self.acceleration ]))

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

    def get_events(self) -> typing.Iterator[ControllerState]:
        """Returns an iterator over events currently pending on the controller."""
        while self.move_.poll():
            yield ControllerState(self.move_)
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
    def active_player_events(self):
        # consider randomizing this so players don't get an advantage by being first in the list.
        for player in list(self.active_players):
            for event in player.get_events():
                yield player, event
    def cancel_effects(self):
        for player in self.players:
            player.cancel_effect()
