from games.game import Game
from piaudio import Audio
from common import Status
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)

# Commander Opts
class Opts(Enum):
    DEATHS = 0

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive, opts=opts)

        # Everyone on their own team
        self.num_teams = len(moves)
        self.generate_teams(self.num_teams)

        # The amount of time the game will last (2.5 minutes)
        self.non_stop_time = time.time() + 150

        # Enable players reviving
        self.revive.value = True

        self.game_loop()

    '''
    Override joust functions
    '''
    # Add countdown sounds
    def init_audio(self):
        super().init_audio()

        if self.play_audio:
            self.one_minute = Audio('audio/Zombie/vox/' + self.voice + '/1 minute.wav')
            self.thirty_seconds = Audio('audio/Zombie/vox/' + self.voice + '/30 seconds.wav')

    def check_winner(self):
        if time.time() > self.non_stop_time:
            lowest_score = 100000
            for move_serial in self.moves:
                self.dead_moves[move_serial].value = Status.OFF.value # Turn off lights
                score = self.opts[move_serial][Opts.DEATHS.value]
                if score == lowest_score:
                    self.winning_moves.append(move_serial)
                if score < lowest_score:
                    lowest_score = score
                    self.winning_moves = []
                    self.winning_team = self.teams[move_serial]
                    self.winning_moves.append(move_serial)
            return True
        elif self.audio_cue == 1 and time.time() > self.non_stop_time - 30:
            self.thirty_seconds.start_effect()
            self.audio_cue += 1
        elif self.audio_cue == 0 and time.time() > self.non_stop_time - 60:
            self.one_minute.start_effect()
            self.audio_cue += 1
        return False

    def check_end_game(self):
        if self.check_winner():
            logger.debug("Game ended, winning players: {}".format(self.winning_moves))
            if len(self.winning_moves) > 1:
                self.update_status('ending', self.winning_team)
            self.end_game_sound()
            self.game_end = True

    def end_game_sound(self):
        # Don't set a winning team if two people won
        if len(self.winning_moves) > 1:
            self.winning_team = None

        super().end_game_sound()

    @classmethod
    def handle_opts(cls, move, team, opts, dead_move):
        if dead_move == Status.DIED.value:
            opts[Opts.DEATHS.value] = opts[Opts.DEATHS.value] + 1

        return opts



            
        

            
