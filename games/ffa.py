import enum
import asyncio
import time

import common
from player import Player, PlayerCollection

# Hertz
UPDATE_FREQUENCY=30

# TODO: These are placeholder values.
# We can't take the values from joust.py, since those are compared to the sum of the
# three accelerometer dimensions, whereas we compute the magnitude of the acceleration
# vector.
DEATH_THRESHOLD=7
WARN_THRESHOLD=2

class FreeForAll:
    ## Note, the "Player" objects should probably get created (and assigned colors) by the core game code, not here.
    def __init__(self, controllers, music):
        players = [ Player(move) for move in controllers ]
        for player, color in zip(players, common.PLAYER_COLORS):
            player.set_player_color(color)
        self.players = PlayerCollection(players)
        self.music = music
        self.rainbow_duration_ = 6

    def has_winner_(self):
        if len(self.players.active_players) == 0:
            raise ValueError("Can't have zero players!")
        return len(self.players.active_players) == 1

    def game_tick_(self):
        """Implements a game tick.
           Polls controllers for input, and issues warnings/deaths to players."""
        # Make a copy of the active players, as we may modify it during iteration.
        for player, state in self.players.active_player_events():
            if state.acceleration_magnitude > DEATH_THRESHOLD:
                self.players.kill_player(player)

                # Cut out early if we have a winner, so we don't accidentally kill all remaining players.
                if self.has_winner_():
                    break
            elif state.acceleration_magnitude > WARN_THRESHOLD:
                player.warn()

    async def run(self):
        """Main loop for this game."""
        # TODO: Countdown/Intro.
        self.music.start_audio_loop()
        try:
            while not self.has_winner_():
                self.game_tick_()
                await asyncio.sleep(1 / UPDATE_FREQUENCY)
            # TODO: Play some kind of crash sound to let everyone know there is a winner.
            self.music.stop_audio()
            winner = list(self.players.active_players)[0]
            await winner.show_rainbow(self.rainbow_duration_)
        finally:
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

