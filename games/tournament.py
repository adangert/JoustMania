from games.game import Game
from common import Status
from piaudio import Audio
import random, math, time
import logging

logger = logging.getLogger(__name__)

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive)

        # Everyone on their own team (so players can switch to a unique team)
        self.num_teams = len(moves)
        self.generate_teams(self.num_teams)

        self.invincible_duration = 4
        self.invincible_end = {}

        self.tourney_list = self.generate_tourney_list(len(moves))
        logger.debug("Bracket: {}".format(self.tourney_list))

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Set up initial moves
    def init_moves(self):
        super().init_moves()

        for move_serial in self.moves:
            self.set_invincible(move_serial)

    # @Override
    # Fix teams before game starts
    def before_game_loop(self):
        super().before_game_loop()
        self.check_matches()

    # @Override
    # Handle ending invincibility
    def handle_status(self):
        move_died = False
        for move_serial, dead in self.dead_moves.items():
            if dead.value == Status.DIED.value:
                move_died = True
                self.remove_dead_player(move_serial)
                dead.value = Status.DEAD.value
                self.play_death_sound(move_serial)
        if move_died:
            self.check_matches()

        for move_serial, end in self.invincible_end.items():
            if end is not None and time.time() > end:
                logger.debug("Removing invincibility from: {}".format(move_serial))
                self.invincible_moves[move_serial].value = False
                self.invincible_end[move_serial] = None
                self.play_revive_sound()

    # @Override
    # Game ends when only 1 move is left alive
    def check_winner(self):
        self.winning_moves = []
        for move_serial, dead in self.dead_moves.items():
            if dead.value in [Status.ALIVE.value, Status.ON.value]:
                self.winning_moves.append(move_serial)

        if len(self.winning_moves) > 1:
            return False
        else:
            return True

    # @Override
    # Play generic congratulations as teams are not relevant
    def winning_team_sound(self):
        Audio('audio/Joust/vox/' + self.voice + '/congratulations.wav').start_effect()

    def generate_tourney_list(self, player_num):
        def divide(arr, depth, m):
            if len(complements) <= depth:
                complements.append(2 ** (depth + 2) + 1)
            complement = complements[depth]
            for i in range(2):
                if complement - arr[i] <= m:
                    arr[i] = [arr[i], complement - arr[i]]
                    divide(arr[i], depth + 1, m)

        m = player_num

        arr = [1, 2]
        complements = []

        divide(arr, 0, m)
        dup_serials = self.move_serials[:]

        def insert_move(arr):
            for i in range(2):
                if type(arr[i]) is list:
                    insert_move(arr[i])
                else:
                    arr[i] = random.choice(dup_serials)
                    dup_serials.remove(arr[i])

        insert_move(arr)
        return arr

    '''
    Game-specific functions
    '''
    def check_matches(self):
        # Check when a controller dies, or at the beginning
        def check_moves(arr):
            # If there isn't a winner yet
            if len(arr) > 1:
                # If the arr[0] and arr[1] are not lists
                if type(arr[0]) is not list and type(arr[1]) is not list:
                    if self.teams[arr[1]] != -1:
                        logger.debug("Switching {} to team {}".format(arr[0], self.teams[arr[1]]))
                        self.switch_teams(arr[0], self.teams[arr[1]])
                    else:
                        logger.debug("Switching {} to team {}".format(arr[1], self.teams[arr[0]]))
                        self.switch_teams(arr[1], self.teams[arr[0]])
                    self.dead_moves[arr[0]].value = Status.ALIVE.value
                    self.dead_moves[arr[1]].value = Status.ALIVE.value
                elif type(arr[0]) is not list and type(arr[1]) is list:
                    logger.debug("Switching {} into waiting".format(arr[0]))
                    self.switch_teams(arr[0], -1)
                    self.dead_moves[arr[0]].value = Status.ON.value
                    check_moves(arr[1])
                elif type(arr[1]) is not list and type(arr[0]) is list:
                    logger.debug("Switching {} into waiting".format(arr[1]))
                    self.switch_teams(arr[1], -1)
                    self.dead_moves[arr[1]].value = Status.ON.value
                    check_moves(arr[0])
                elif type(arr[0]) is list and type(arr[1]) is list:
                    logger.debug("Checking next level")
                    check_moves(arr[0])
                    check_moves(arr[1])
        check_moves(self.tourney_list)

    def remove_dead_player(self, dead_serial):
        def remove_dead(arr):
            if type(arr) is list and dead_serial in arr:
                arr.remove(dead_serial)
            else:
                if type(arr[0]) is list:
                    remove_dead(arr[0])
                if type(arr[1]) is list:
                    remove_dead(arr[1])
        remove_dead(self.tourney_list)

        def move_up(arr):
            if type(arr) is list and len(arr) == 1:
                return arr[0]
            else:
                if type(arr[0]) is list and move_up(arr[0]):
                    arr[0] = move_up(arr[0])
                    if type(arr[1]) is not list:
                        self.switch_teams(arr[1], self.teams[arr[0]])
                        self.set_invincible(arr[0])
                        self.set_invincible(arr[1])
                    else:
                        self.switch_teams(arr[0], -1)
                        self.dead_moves[arr[0]].value = Status.ON.value
                elif type(arr[1]) is list and move_up(arr[1]):
                    arr[1] = move_up(arr[1])

                    if type(arr[0]) is not list:
                        self.switch_teams(arr[0], self.teams[arr[1]])
                        self.set_invincible(arr[0])
                        self.set_invincible(arr[1])
                    else:
                        self.switch_teams(arr[1], -1)
                        self.dead_moves[arr[1]].value = Status.ON.value
        move_up(self.tourney_list)

        logger.debug("Updated bracket: {}".format(self.tourney_list))

    def set_invincible(self, serial):
        self.invincible_moves[serial].value = True
        self.invincible_end[serial] = time.time() + self.invincible_duration

    # Return white for waiting players
    @classmethod
    def handle_team_color(cls, move, team, opts, team_color):
        if team == -1:
            return 100, 100, 100
        return team_color