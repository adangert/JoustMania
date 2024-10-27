from games import game, joust_non_stop, werewolf, zombie, commander, tournament, speed_bomb, fight_club
import common, piparty
import logging
import setproctitle

logger = logging.getLogger(__name__)

#this should all be refactored to use the same options per game
#this file is used for multiprocessing
def main_track_move(menu, restart, move_serial, move_num, menu_opts, game_opts, force_color, battery, dead_count, game_mode, \
                    team, team_color_enum, sensitivity, dead_move, invincible_move, music_speed, show_team_colors, red_on_kill,\
                    revive, kill_proc):

    # Set the process title
    setproctitle.setproctitle(f"JoustMania-main_track_move({move_serial})")

    move = common.get_move(move_serial, move_num)

    while not kill_proc.value:
        move.set_rumble(0)
        if restart.value == 1:
            pass
        elif menu.value == 1:
            logger.debug("Tracking Move (Menu): {}".format(move_serial))
            piparty.track_move(move_serial, move_num, move, menu_opts, force_color, battery, dead_count, restart, menu, kill_proc)
        else:
            logger.debug("Track Move ({}): {}".format(common.get_game_name(game_mode.value), move_serial))
            if game_mode.value == common.Games.Tournament.value:
                tournament.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Custom revive timing
            # Has a pre-game selection
            elif game_mode.value == common.Games.Commander.value:
                commander.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Has different speeds for zombies
            elif game_mode.value == common.Games.Zombies.value:
                zombie.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Has different speeds for werewolf
            elif game_mode.value == common.Games.Werewolf.value:
                werewolf.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Have to track deaths
            elif game_mode.value == common.Games.NonStop.value:
                joust_non_stop.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Completely different track_moves
            elif game_mode.value == common.Games.Ninja.value:
                speed_bomb.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            # Joust, Joust Teams, Joust Random Teams, Non-Stop Joust, Swapper, Traitor, Fight Club
            else:
                game.Game.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move, invincible_move=invincible_move, \
                    force_color=force_color, music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill, \
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
