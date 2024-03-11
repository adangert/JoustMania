from games.game import Game
from piaudio import Audio
from common import Status
import colors, common
from enum import Enum
import random, time
import logging

logger = logging.getLogger(__name__)

class Opts(Enum):
    HOLDING = 0
    SELECTION = 1
    HAS_BOMB = 2
    FAKED = 3
    LIVES = 4
    TRIGGER = 5
    BOMB_START_TIME = 6
    BOMB_END_TIME = 7

class Selection(Enum):
    NOTHING = 0
    NEXT_BUTTON = 1
    TRIGGER = 2
    COUNTER = 3

class Faked(Enum):
    NONE = 0
    ATTEMPT = 1
    FAKED = 2

TIME_OFFSET = time.time()

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive, opts=opts)

        self.bomb_generator = None
        self.bomb_length = 7.0
        self.bomb_time = None
        self.bomb_start_time = None
        self.bomb_serial = None
        self.current_rand_holder = None
        self.next_rand_holder = None
        self.prev_rand_holder = None
        self.holding = False

        # Everyone on their own team
        self.num_teams = len(moves)
        self.generate_teams(self.num_teams)

        self.game_loop()

    '''
    Override generic functions
    '''
    def init_audio(self):
        super().init_audio()
        self.faked_out = Audio('audio/Joust/vox/' + self.voice + '/Fakedout.wav')
        self.explosion40 = Audio('audio/Joust/sounds/Explosion40.wav')
        self.countered = Audio('audio/Joust/vox/' + self.voice + '/countered.wav')
        self.explosion_death = Audio('audio/Joust/vox/' + self.voice + '/explosiondeath.wav')

    # @Override
    # Set up lives (and turn to ON instead of ALIVE)
    def init_moves(self):
        super().init_moves()

        logger.debug("Init moves")
        for move_num, move_serial in enumerate(self.moves):
            self.dead_moves[move_serial].value = Status.ON.value # Aren't going to be using accelerometer
            self.opts[move_serial][Opts.LIVES.value] = 2 # Set number of lives

    # @Override
    def before_game_loop(self):
        super().before_game_loop()

        # self.rotate_colors() # TODO - is this needed?
        self.bomb_generator = self.get_next_bomb_holder()
        self.bomb_serial = next(self.bomb_generator)
        self.opts[self.bomb_serial][Opts.HAS_BOMB.value] = True
        logger.debug("Initial bomb serial: {}".format(self.bomb_serial))

        self.holding = True

        self.reset_bomb_time(False)

    # @Override
    def handle_status(self):
        for move_serial in self.moves:
            if self.dead_moves[move_serial].value == Status.DIED.value:
                logger.debug("Move is dead: {}, has bomb: {}".format(move_serial, self.opts[move_serial][Opts.HAS_BOMB.value]))
                self.dead_moves[move_serial].value = Status.OFF.value
                if self.opts[move_serial][Opts.HAS_BOMB.value]:
                    self.opts[move_serial][Opts.HAS_BOMB.value] = False
                    self.move_bomb()
                self.reset_bomb_time(True)

        if self.opts[self.bomb_serial][Opts.SELECTION.value] == Selection.NOTHING.value:
            self.holding = False
        elif self.opts[self.bomb_serial][Opts.SELECTION.value] == Selection.NEXT_BUTTON.value and not self.holding:
            self.reset_bomb_time(False)
            self.move_bomb()
            if self.play_audio:
                self.start_beep.start_effect()
            self.holding = True

        if time.time() > self.bomb_time:
            logger.debug("Bomb exploded: {}".format(time.time()))
            self.kill_player(self.bomb_serial)

            self.reset_bomb_time(True)

        self.check_faked_out()

    # @Override
    # Play generic congratulations as teams are not relevant
    def winning_team_sound(self):
        Audio('audio/Joust/vox/' + self.voice + '/congratulations.wav').start_effect()

    '''
    Game-specific functions
    '''
    def move_bomb(self):
        old_bomb_serial = self.bomb_serial
        self.opts[old_bomb_serial][Opts.HAS_BOMB.value] = False

        self.bomb_serial = next(self.bomb_generator)
        self.bomb_generator = self.get_next_bomb_holder()

        self.opts[self.bomb_serial][Opts.HAS_BOMB.value] = True
        self.opts[self.bomb_serial][Opts.BOMB_START_TIME.value] = self.opts[old_bomb_serial][Opts.BOMB_START_TIME.value]
        self.opts[self.bomb_serial][Opts.BOMB_END_TIME.value] = self.opts[old_bomb_serial][Opts.BOMB_END_TIME.value]

        logger.debug("Moving bomb to: {}".format(self.bomb_serial))

    def reset_bomb_length(self):
        self.bomb_length = 4.0

    def get_bomb_length(self):
        self.bomb_length -= 0.3
        if self.bomb_length < 1:
            self.bomb_length = 1
        logger.debug("New bomb length: {}".format(self.bomb_length))
        return self.bomb_length

    def check_faked_out(self):
        # Check for one controller left first
        for move_serial in self.moves:
            if self.dead_moves[move_serial].value == Status.ON.value:
                # If we faked play sound
                if self.opts[move_serial][Opts.SELECTION.value] == Selection.TRIGGER.value and \
                        not self.opts[move_serial][Opts.HOLDING.value]:
                    self.opts[move_serial][Opts.HOLDING.value] = True
                    victim = self.get_next_serial(move_serial)
                    logger.debug("{} is trying to fake out {}".format(move_serial, victim))
                    self.reset_bomb_time(True)
                    self.opts[victim][Opts.FAKED.value] = Faked.ATTEMPT.value
                    if self.play_audio:
                        self.start_beep.start_effect()

                # We are being faked out
                if self.opts[move_serial][Opts.FAKED.value] in [Faked.ATTEMPT.value, Faked.FAKED.value]:
                    faker = self.get_prev_serial(move_serial)
                    # Pushed triangle button, when faked
                    if self.opts[move_serial][Opts.FAKED.value] == Faked.FAKED.value:
                        if self.play_audio:
                            self.explosion40.start_effect()
                            self.faked_out.start_effect()
                        self.kill_player(move_serial)

                        logger.debug("Killed from fake bomb: {}".format(faker))

                        self.reset_bomb_time(True)
                        self.move_bomb()

                    elif self.opts[move_serial][Opts.FAKED.value] == Faked.ATTEMPT.value and \
                        self.opts[move_serial][Opts.SELECTION.value] == Selection.COUNTER.value:
                        if self.play_audio:
                            self.explosion40.start_effect()
                            self.countered.start_effect()
                        self.kill_player(faker)

                        logger.debug("Killed from from counter: {}".format(faker))

                        self.reset_bomb_time(True)
                        self.move_bomb()

    # TODO - Handle the deaths better - it's pausing right now
    def kill_player(self, dead_move):
        self.opts[dead_move][Opts.LIVES.value] -= 1
        logger.debug("Lost a life: {}, {} remaining".format(dead_move, self.opts[dead_move][Opts.LIVES.value]))
        end_time = time.time() + 5
        if self.play_audio:
            self.explosion_death.start_effect()
            self.explosion.start_effect()
            
        dead_color_array = self.force_move_colors[dead_move]


        for move_serial in self.moves:
            if move_serial == dead_move:
                colors.change_color(dead_color_array, 10, 200, 10)
                self.dead_moves[move_serial].value = Status.RUMBLE.value
            else:
                colors.change_color(self.force_move_colors[move_serial], 1, 1, 1)
        
        while time.time() < end_time:
            time.sleep(0.01)


        self.dead_moves[dead_move].value = Status.ON.value

        # Reset all opts (except lives)
        for move_serial in self.moves:
            if not self.dead_moves[move_serial].value == Status.OFF.value:
                self.opts[move_serial][Opts.HOLDING.value] = 0
                self.opts[move_serial][Opts.SELECTION.value] = 0
                self.opts[move_serial][Opts.FAKED.value] = 0
                self.opts[move_serial][Opts.TRIGGER.value] = 0
                self.opts[move_serial][Opts.BOMB_START_TIME.value] = 0
                self.opts[move_serial][Opts.BOMB_END_TIME.value] = 0

        self.change_all_move_colors(0, 0, 0)

        if self.opts[dead_move][Opts.LIVES.value] <= 0:
            self.dead_moves[dead_move].value = Status.DIED.value
        logger.debug("Done killing player: {}, has bomb: {}".format(dead_move, self.opts[dead_move][Opts.HAS_BOMB.value]))

    def get_next_serial(self, serial):
        return self.get_next_random_holder()

    def get_prev_serial(self, serial):
        self.get_next_random_holder()
        return self.get_prev_random_holder()

    def get_serial_pos(self, serial):
        for i, move_serial in enumerate(self.move_serials):
            if serial == move_serial:
                return i

    def get_prev_random_holder(self):
        return self.bomb_serial

    def get_next_bomb_holder(self):
        while True:
            yield self.get_next_random_holder()

    def get_next_random_holder(self):
        if self.next_rand_holder == self.bomb_serial:
            self.next_rand_holder = self.move_serials[random.choice(range(len(self.moves)))]
            while self.next_rand_holder == self.bomb_serial or not self.dead_moves[self.next_rand_holder].value == Status.ON.value:
                self.next_rand_holder = self.move_serials[random.choice(range(len(self.moves)))]
                self.current_rand_holder = self.bomb_serial
        return self.next_rand_holder

    def reset_bomb_time(self, reset_length):
        if reset_length:
            self.reset_bomb_length()

        self.bomb_start_time = time.time()
        self.bomb_time = time.time() + self.get_bomb_length()
        self.opts[self.bomb_serial][Opts.BOMB_START_TIME.value] = Joust.time_to_ms_int(self.bomb_start_time)
        self.opts[self.bomb_serial][Opts.BOMB_END_TIME.value] = Joust.time_to_ms_int(self.bomb_time)

    # TODO - Fix that the buttons are only being tracked during transitions between colors
    # def rotate_colors(self):
    #     in_cons = []
    #     while len(in_cons) != len(self.moves):
    #         for move_serial in self.moves:
    #             for move_serial_beg in self.moves:
    #                 if self.opts[move_serial_beg][Opts.SELECTION.value] == Selection.NEXT_BUTTON.value:
    #                     if move_serial_beg not in in_cons:
    #                         if self.play_audio:
    #                             self.start_beep.start_effect()
    #                         in_cons.append(move_serial_beg)
    #                 if move_serial_beg in in_cons:
    #                     colors.change_color(self.force_move_colors[move_serial_beg], 100, 100, 100)
    #             colors.change_color(self.force_move_colors[move_serial], 100, 0, 0)
    #             time.sleep(0.5)
    #             self.force_black(move_serial)
    #     for move_serial in self.move_serials:
    #         self.opts[move_serial][Opts.HAS_BOMB.value] = False

    '''
    Override track_move functions
    '''
    @classmethod
    def handle_team_color(cls, move, team, opts, team_color):
        fake_bomb_color = (0, 255, 0)
        if opts[Opts.LIVES.value] == 2:
            no_fake_bomb_color = (120, 255, 120)
        else:
            no_fake_bomb_color = (100, 100, 100)

        if opts[Opts.FAKED.value] == Faked.ATTEMPT.value:
            return 150, 20, 20

        if not opts[Opts.HAS_BOMB.value]:
            if opts[Opts.LIVES.value] == 2:
                return 150, 150, 150
            else:
                return 30, 30, 30
        else:
            if opts[Opts.SELECTION.value] == Selection.TRIGGER.value:
                # If held down, change color of bomb
                if opts[Opts.TRIGGER.value] <= 127:
                    return cls.calculate_bomb_color(fake_bomb_color, no_fake_bomb_color, opts[Opts.TRIGGER.value])
                if opts[Opts.TRIGGER.value] > 127:
                    return cls.calculate_bomb_color(no_fake_bomb_color, fake_bomb_color, opts[Opts.TRIGGER.value])
            else:
                if opts[Opts.BOMB_START_TIME.value] > 0:
                    time_ms = cls.time_to_ms_int(time.time())
                    percentage = 1-((opts[Opts.BOMB_END_TIME.value] - time_ms) / (opts[Opts.BOMB_END_TIME.value] - opts[Opts.BOMB_START_TIME.value]))
                else:
                    percentage = 1

                bomb_color = [0,0,0]
                #Currently flickering like this causes a build-up of buffering colors
                #so it can stall the game. Keeping it solid seems to work better!
                #if percentage > 0.8:
                #    bomb_color[0] = random.randrange(int(100+55*percentage), int(200+55*percentage))
                #else:
                bomb_color[0] = int(common.lerp(50, 255, percentage))
                bomb_color[1] = int(common.lerp(30, 0, percentage))
                bomb_color[2] = int(common.lerp(30, 0, percentage))
                return bomb_color

    @classmethod
    def handle_opts(cls, move, team, opts, dead_move=None):
        if move.poll():
            pressed, released = move.get_button_events()
            trigger = move.get_trigger()
            # If pressing a trigger or next button when being faked, kill the player
            if opts[Opts.FAKED.value] == Faked.ATTEMPT.value and not opts[Opts.HAS_BOMB.value] and \
                    (trigger > 50 or (pressed & common.Button.MIDDLE.value)):
                logger.debug("Faked out: {}".format(move.get_serial()))
                opts[Opts.FAKED.value] = Faked.FAKED.value
            # If pressing a trigger with bomb, start faking
            elif opts[Opts.HAS_BOMB.value] and trigger > 50:
                    opts[Opts.SELECTION.value] = Selection.TRIGGER.value
                    opts[Opts.TRIGGER.value] = trigger
            # If pressing counter while being faked, counter
            elif not opts[Opts.HAS_BOMB.value] and (pressed & common.Button.SQUARE.value or \
                    pressed & common.Button.TRIANGLE.value or \
                    pressed & common.Button.CIRCLE.value or \
                    pressed & common.Button.CROSS.value) and opts[Opts.FAKED.value] == Faked.ATTEMPT.value:
                logger.debug("Pressed Counter Button: {}".format(move.get_serial()))
                opts[Opts.SELECTION.value] = Selection.COUNTER.value
            # If pressing counter while NOT being faked, die
            elif not opts[Opts.FAKED.value] == Faked.ATTEMPT.value and not opts[Opts.HAS_BOMB.value] and (pressed & common.Button.SQUARE.value or \
                                                    pressed & common.Button.CIRCLE.value or \
                                                    pressed & common.Button.CROSS.value):
                logger.debug("Incorrectly pressed Counter Button: {}".format(move.get_serial()))
                opts[Opts.FAKED.value] = Faked.FAKED.value
            # If pressing next with bomb, move bomb
            elif pressed & common.Button.MIDDLE.value and opts[Opts.HAS_BOMB.value]:
                logger.debug("Pressed triangle button: {}".format(move.get_serial()))
                opts[Opts.SELECTION.value] = Selection.NEXT_BUTTON.value
            elif released & common.Button.MIDDLE.value and trigger < 50:
                logger.debug("Released button: {}".format(move.get_serial()))
                opts[Opts.SELECTION.value] = Selection.NOTHING.value
                opts[Opts.HOLDING.value] = False

        return opts

    @classmethod
    def calculate_bomb_color(cls, color_1, color_2, trigger):
        col1 = int(common.lerp(color_1[0], color_2[0], (trigger-50)/77))
        col2 = int(common.lerp(color_1[1], color_2[1], (trigger-50)/77))
        col3 = int(common.lerp(color_1[2], color_2[2], (trigger-50)/77))
        return col1, col2, col3

    @classmethod
    def time_to_ms_int(cls, time):
        return int(round((time - TIME_OFFSET) * 1000))
