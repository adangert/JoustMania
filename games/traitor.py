from games.game import Game
from piaudio import Audio
from common import Status
import random, math, time, statistics
import logging

logger = logging.getLogger(__name__)

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive)

        if len(moves) < 9:
            self.num_teams = 2
        else: #12 or more
            self.num_teams = 3

        self.traitors = []
        self.generate_teams(num_teams=self.num_teams, num_moves=len(moves))

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Add additional werewolf sounds
    def init_audio(self):
        super().init_audio()

        if self.play_audio:
            self.traitor_intro = Audio('audio/Joust/vox/' + self.voice + '/traitor_intro.wav')

    # @Override
    # Create traitors depending on the number of players
    def generate_random_teams(self, num_teams, num_moves):
        super().generate_random_teams(num_teams, num_moves)

        # Traitor numbers:
        # < 4 can't play
        # 4-5 players - 1 traitor
        # 6-8 players - 2 traitors
        # 9-11 players - 3 traitors
        # 12+ players - 4 traitors
        # ...

        if 4 < num_moves <= 5:
            num_traitors = 1
        elif 5 < num_moves <= 8:
            num_traitors = 2
        elif 8 < num_moves <= 11:
            num_traitors = 3
        else:
            num_traitors = math.floor(num_moves / 3)
        logger.debug("Number of traitors: {}".format(num_traitors))

        # For each of the teams, swap a random person to the traitor team
        copy_serials = self.move_serials[:]
        copy_teams = list(self.teams.values())[:]
        while num_traitors > 0:
            team_choice = statistics.mode(copy_teams)
            serial = random.choice([serial for serial in copy_serials \
                                   if self.teams[serial] == team_choice])
            copy_serials.remove(serial)
            logger.debug("Teams list: {}".format(copy_teams))
            self.traitors.append(serial)
            # For Teams  0  1
            # Traitors  -2 -1
            # For Teams  0  1  2
            # Traitors  -3 -2 -1
            # Just need to subtract the num_teams
            self.teams[serial] = team_choice - num_teams
            copy_teams.remove(team_choice)
            num_traitors -= 1
            logger.debug("Traitor selected for team {}: {}".format(team_choice, serial))

        logger.debug("Final Teams list: {}".format(self.teams))

    # @Override
    # Handle traitor pre-game reveal
    def before_game_loop(self):
        super().before_game_loop()

        if self.play_audio:
            self.traitor_intro.start_effect_and_wait()

        self.start_timer = time.time()

        for move_serial, dead in self.dead_moves.items():
            logger.debug("Move {} on team {}: {}".format(move_serial, self.teams[move_serial], dead.value))

    def count_down(self):
        for move_serial in self.traitors:
            logger.debug("Setting to rumble: {}".format(move_serial))
            self.dead_moves[move_serial].value = Status.RUMBLE.value

        self.change_all_move_colors(80, 0, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(70, 100, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 70, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 0, 0)
        if self.play_audio:
            self.start_game.start_effect()

        for move_serial in self.traitors:
            logger.debug("Setting to alive: {}".format(move_serial))
            self.dead_moves[move_serial].value = Status.ALIVE.value

    # @Override
    # Play traitors win if they won
    def winning_team_sound(self):
        if self.winning_team == -1:
            Audio('audio/Joust/vox/' + self.voice + '/traitor win.wav').start_effect_and_wait()
        else:
            super().winning_team_sound()
        
        

            
        

            
