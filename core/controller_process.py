from legacy.games_old import game, joust_non_stop, werewolf, zombie, commander, tournament, speed_bomb, fight_club
import common, piparty
import logging
import time
from controller_state import ControllerState

logger = logging.getLogger(__name__)

#this should all be refactored to use the same options per game
#this file is used for multiprocessing


def state_based_track_move(controller_state, move_serial, move_num, menu, restart, menu_opts, game_opts, force_color,
                           battery, dead_count, game_mode, team, team_color_enum, sensitivity, dead_move,
                           invincible_move, music_speed, show_team_colors, red_on_kill, revive, kill_proc):
    """
    State-based controller tracking with menu/game integration.

    This function:
    1. Continuously polls hardware and updates ControllerState (producer)
    2. Runs menu or game logic based on mode flag (consumer)
    3. Applies LED/rumble outputs to hardware

    Architecture:
        - Hardware polling at ~1000Hz for low latency
        - Menu/game logic runs at 60 FPS
        - Non-blocking state updates

    Args:
        controller_state: ControllerState instance for shared memory
        move_serial: Controller serial number
        move_num: Controller index
        menu: Menu mode flag (1 = menu, 0 = game)
        restart: Restart flag
        menu_opts: Menu options array
        game_opts: Game options array
        force_color: Forced color array
        battery: Battery display flag
        dead_count: Dead controller count
        game_mode: Current game mode
        team: Team assignment
        team_color_enum: Team color
        sensitivity: Movement sensitivity
        dead_move: Dead status flag
        invincible_move: Invincibility flag
        music_speed: Music speed value
        show_team_colors: Show team colors flag
        red_on_kill: Red on kill flag
        revive: Revive enabled flag
        kill_proc: Signal to terminate this process
    """
    logger.info(f"Starting state-based tracking for controller {move_serial}")

    # Get Move controller handle
    move = common.get_move(move_serial, move_num)
    if not move:
        logger.error(f"Failed to get move controller {move_serial}")
        return

    # Main tracking loop with mode dispatching
    while not kill_proc.value:
        move.set_rumble(0)
        controller_state.set_rumble(0)  # Reset rumble in state too

        if restart.value == 1:
            # Update hardware state but don't run menu/game logic
            controller_state.update(move)
            controller_state.apply_outputs(move)
            time.sleep(0.001)
        elif menu.value == 1:
            logger.debug("Tracking Move (Menu): {}".format(move_serial))
            # Menu mode - call state-based menu tracking
            piparty.track_move_state_based(
                move_serial, move_num, controller_state, move, menu_opts, force_color,
                battery, dead_count, restart, menu, kill_proc
            )
        else:
            # Game mode - use state-based game tracking
            logger.debug("Track Move ({}): {}".format(common.get_game_name(game_mode.value), move_serial))

            # Most game modes use the base Game.track_move_state_based
            # Some game modes have custom implementations that inherit from Game
            if game_mode.value == common.Games.Tournament.value:
                # Tournament inherits from base Game, so use base state-based tracking
                game.Game.track_move_state_based(
                    controller_state=controller_state, move=move, team=team, team_color_enum=team_color_enum,
                    dead_move=dead_move, invincible_move=invincible_move, force_color=force_color,
                    music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill,
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            elif game_mode.value == common.Games.Commander.value:
                # Commander has custom tracking, fallback to legacy for now
                # TODO: Migrate commander.Joust to state-based
                commander.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move,
                    invincible_move=invincible_move, force_color=force_color, music_speed=music_speed,
                    show_team_colors=show_team_colors, red_on_kill=red_on_kill, restart=restart,
                    menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            elif game_mode.value == common.Games.Zombies.value:
                # Zombie has custom tracking, fallback to legacy for now
                # TODO: Migrate zombie.Joust to state-based
                zombie.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move,
                    invincible_move=invincible_move, force_color=force_color, music_speed=music_speed,
                    show_team_colors=show_team_colors, red_on_kill=red_on_kill, restart=restart,
                    menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            elif game_mode.value == common.Games.Werewolf.value:
                # Werewolf has custom tracking, fallback to legacy for now
                # TODO: Migrate werewolf.Joust to state-based
                werewolf.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move,
                    invincible_move=invincible_move, force_color=force_color, music_speed=music_speed,
                    show_team_colors=show_team_colors, red_on_kill=red_on_kill, restart=restart,
                    menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            elif game_mode.value == common.Games.NonStop.value:
                # NonStop has custom tracking, fallback to legacy for now
                # TODO: Migrate joust_non_stop.Joust to state-based
                joust_non_stop.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move,
                    invincible_move=invincible_move, force_color=force_color, music_speed=music_speed,
                    show_team_colors=show_team_colors, red_on_kill=red_on_kill, restart=restart,
                    menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            elif game_mode.value == common.Games.Ninja.value:
                # Ninja (speed_bomb) has completely different tracking, use legacy
                # TODO: Migrate speed_bomb.Joust to state-based
                speed_bomb.Joust.track_move(
                    move=move, team=team, team_color_enum=team_color_enum, dead_move=dead_move,
                    invincible_move=invincible_move, force_color=force_color, music_speed=music_speed,
                    show_team_colors=show_team_colors, red_on_kill=red_on_kill, restart=restart,
                    menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )
            else:
                # Default: use base game state-based tracking (for most game modes)
                # This covers: JoustFFA, JoustTeams, JoustRandomTeams, Traitor, Swapper, FightClub, Random
                game.Game.track_move_state_based(
                    controller_state=controller_state, move=move, team=team, team_color_enum=team_color_enum,
                    dead_move=dead_move, invincible_move=invincible_move, force_color=force_color,
                    music_speed=music_speed, show_team_colors=show_team_colors, red_on_kill=red_on_kill,
                    restart=restart, menu=menu, sensitivity=sensitivity, revive=revive, opts=game_opts
                )

    logger.info(f"Stopped state-based tracking for controller {move_serial}")


def main_track_move(menu, restart, move_serial, move_num, menu_opts, game_opts, force_color, battery, dead_count, game_mode, \
                    team, team_color_enum, sensitivity, dead_move, invincible_move, music_speed, show_team_colors, red_on_kill,\
                    revive, kill_proc):

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