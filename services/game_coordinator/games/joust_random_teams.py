from games.game import Game
from piaudio import Audio
import colors
import logging

logger = logging.getLogger(__name__)

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive)

        # Create randoms teams using the num teams from admin settings
        self.num_teams = self.ns.settings['random_team_size']
        self.team_colors = colors.generate_team_colors(self.num_teams,self.color_lock,self.color_lock_choices)
        self.generate_random_teams(self.num_teams)

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Form teams audio
    def init_audio(self):
        super().init_audio()

        if self.play_audio:
            self.teams_form = Audio('audio/Joust/sounds/teams_form.wav')

    # @Override
    # Show the team colors before the game begins to allow teams to group
    def before_game_loop(self):
        super().before_game_loop()

        self.show_team_colors.value = 1
        if self.play_audio:
            self.teams_form.start_effect_and_wait()
        self.show_team_colors.value = 0



                
                
        
        

            
        

            
