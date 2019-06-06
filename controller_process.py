from games import ffa, zombie, commander, swapper, tournament, speed_bomb, fight_club
import common, colors, joust, webui, piparty
#this should all be refactored to use the same options per game
def main_track_move(menu, restart, move_serial, move_num, move_opts, force_color, battery, dead_count, game_mode, \
                    team, team_color_enum, controller_sensitivity, dead_move, music_speed, werewolf_reveal, show_team_colors, red_on_kill, zombie_opt,\
                    commander_intro, commander_move_opt, commander_powers, commander_overdrive,five_controller_opt, swapper_team_colors,\
                    invincibility, fight_club_color, num_teams,bomb_color,game_start,false_color, faked, rumble, dead_invince, kill_proc):
    print("starting Controller Process")
    
    move = common.get_move(move_serial, move_num)
    while(not kill_proc.value):
        move.set_rumble(0)
        if(restart.value == 1):
            pass
        elif (menu.value == 1):
            piparty.track_move(move_serial, move_num, move, move_opts, force_color, battery, dead_count, restart, menu, kill_proc)
        elif(game_mode.value == common.Games.Zombies.value):
            zombie.track_controller(move, zombie_opt, restart, menu, controller_sensitivity)
        elif(game_mode.value == common.Games.Commander.value):
            commander.track_move(move, team.value, dead_move, force_color, music_speed, commander_intro, \
                                 commander_move_opt, commander_powers, commander_overdrive, restart, menu, controller_sensitivity)
        elif(game_mode.value == common.Games.Swapper.value):
            swapper.track_move(move, team, 2, swapper_team_colors, \
                               dead_move, force_color, music_speed, five_controller_opt, restart, menu, controller_sensitivity)
        elif(game_mode.value == common.Games.FightClub.value):
            fight_club.track_move(move, dead_move, force_color, music_speed, fight_club_color, invincibility, menu, restart, controller_sensitivity)
        elif(game_mode.value == common.Games.Tournament.value):
            tournament.track_move(move, team, num_teams.value, dead_move, force_color, music_speed, show_team_colors, invincibility, menu, restart, controller_sensitivity)
        elif(game_mode.value == common.Games.Ninja.value):
            speed_bomb.track_move(move, dead_move, force_color,bomb_color, five_controller_opt, game_start, false_color, faked, rumble, menu, restart)
        else:
            joust.track_move(move, game_mode.value, team.value, team_color_enum, dead_move, force_color, \
                             music_speed, werewolf_reveal, show_team_colors, red_on_kill, restart, menu, controller_sensitivity, dead_invince)
         
