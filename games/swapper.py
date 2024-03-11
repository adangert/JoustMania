from games.game import Game
import common
import logging

logger = logging.getLogger(__name__)

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive)

        # Only two teams
        self.num_teams = 2
        self.generate_teams(self.num_teams)

        self.last_move = None # The last move to die is the only loser

        self.revive.value = True # Enable reviving

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Handle swapping of teams
    def handle_status(self):
        for move_serial, dead in self.dead_moves.items():
            # If we just died (dead.value = 0), play the explosion sound
            if dead.value == common.Status.DIED.value:
                logger.debug("Move has died, swapping teams: {}".format(move_serial))
                self.num_dead += 1
                # Switch teams
                self.switch_teams(move_serial, (self.teams[move_serial] + 1) % self.num_teams)
                dead.value = common.Status.DEAD.value
                if self.play_audio:
                    self.play_death_sound(move_serial)
                self.last_move = move_serial
            elif dead.value == common.Status.REVIVED.value:
                logger.debug("Move has revived: {}".format(move_serial))
                dead.value = common.Status.ALIVE.value
                if self.play_audio:
                    self.revive_sound.start_effect()

    # @Override
    # Everyone wins except for the last one to die
    def check_end_game(self):
        super().check_end_game()

        if self.game_end:
            # Make sure the last move that died is not displayed as winning
            if self.last_move in self.winning_moves:
                self.winning_moves.remove(self.last_move)