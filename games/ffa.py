import enum
import asyncio
import time

import common
import pacemanager
from player import Player, PlayerCollection, EventType

# Hertz
UPDATE_FREQUENCY=30

# Values are (weight, min_duration, max_duration)
PACE_TIMING = {
    common.MEDIUM_PACE: (1.0, 10, 23),
    common.FAST_PACE: (1.0, 5, 15),
}

INITIAL_PACE_DURATION=18

class FreeForAll:
    ## Note, the "Player" objects should probably get created (and assigned colors) by the core game code, not here.
    def __init__(self, controllers, music):
        players = [ Player(move) for move in controllers ]
        for player, color in zip(players, common.PLAYER_COLORS):
            player.set_player_color(color)
        self.players = PlayerCollection(players)
        self.music = music
        self.pace_ = common.MEDIUM_PACE
        self.rainbow_duration_ = 6

    def has_winner_(self):
        if len(self.players.active_players) == 0:
            raise ValueError("Can't have zero players!")
        return len(self.players.active_players) == 1

    def build_pace_manager_(self):
        pm = pacemanager.PaceManager(self.pace_change_callback_, self.pace_, INITIAL_PACE_DURATION)
        for pace, timing in PACE_TIMING.items():
            pm.add_or_update_pace(pace, *timing)
        return pm

    def pace_change_callback_(self, new_pace):
        @common.async_print_exceptions
        async def change_pace():
            print("Changing pace to %s..." % new_pace)
            transition_future = self.music.transition_ratio(new_pace.tempo)
            # If we're slowing down the pace, give players a grace period to respond.
            if new_pace.tempo < self.pace_.tempo:
                await transition_future
                await asyncio.sleep(0.5)
            self.pace_ = new_pace
            print(".... Done.")
        asyncio.ensure_future(change_pace())

    def game_tick_(self):
        """Implements a game tick.
           Polls controllers for input, and issues warnings/deaths to players."""
        # Make a copy of the active players, as we may modify it during iteration.
        pace = self.pace_
        for event in self.players.active_player_events(EventType.SENSOR):
            if event.acceleration_magnitude > pace.death_threshold:
                self.players.kill_player(event.player)

                # Cut out early if we have a winner, so we don't accidentally kill all remaining players.
                if self.has_winner_():
                    break
            elif event.acceleration_magnitude > pace.warn_threshold:
                event.player.warn()

    async def run(self):
        """Main loop for this game."""
        # TODO: Countdown/Intro.
        self.music.start_audio_loop()

        # TODO: Vary pace with player deaths.
        pm = self.build_pace_manager_()
        pm.start()
        try:
            while not self.has_winner_():
                self.game_tick_()
                await asyncio.sleep(1 / UPDATE_FREQUENCY)
            # TODO: Play some kind of crash sound to let everyone know there is a winner.
            self.music.stop_audio()
            winner = list(self.players.active_players)[0]
            await winner.show_rainbow(self.rainbow_duration_)
        finally:
            pm.stop()
            self.music.stop_audio()
            self.players.cancel_effects()

    # TODO: Ideally, the main game loop in piparty.py should handle setting up async.
    def run_loop(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.run_until_complete(self.run())
        # TODO: We should make sure all other scheduled tasks have completed.

    def set_rainbow_duration_for_testing(self, secs):
        self.rainbow_duration_ = secs

