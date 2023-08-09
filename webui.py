from multiprocessing import Queue, Manager, Process
from time import sleep
from flask import Flask, render_template, request, redirect, url_for, flash
from time import sleep
from wtforms import Form, SelectField, SelectMultipleField, BooleanField, widgets, FieldList
from os import system
import common, colors
import json
import yaml

class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """
    widget = widgets.ListWidget(prefix_label=True)
    option_widget = widgets.CheckboxInput()


class SettingsForm(Form):
    move_can_be_admin = BooleanField('Allow Move to change settings')
    play_instructions = BooleanField('Play instructions before game start')
    play_audio = BooleanField('Play audio')
    red_on_kill = SelectField('Kill notification',choices=[(True,'Red'),('','Dark')],coerce=bool)
    sensitivity = SelectField('Move sensitivity',choices=[(0,'Ultra High'),(1,'High'),(2,'Medium'),(3,'Low'),(4,'Ultra Low')],coerce=int)
    mode_options = [ game for game in common.Games if game not in [common.Games.Random, common.Games.JoustTeams]]
    random_modes = MultiCheckboxField('Random Modes',choices=[(game.name, game.pretty_name) for game in mode_options])
    color_lock = BooleanField('Lock team colors')
    color_choices = [(color.name,color.name) for color in colors.team_color_list]
    color_lock_choices = FieldList(SelectField('',choices=color_choices,coerce=str),min_entries=9)
    random_teams = BooleanField('Randomize teams each round')
    force_all_start = BooleanField('When force starting start with all or only those who pushed trigger')
    random_team_size = SelectField('size of random teams',choices=[(2,'2'),(3,'3'),(4,'4'),(5,'5'),(6,'6')],coerce=int)

class WebUI():
    def __init__(self, command_queue=Queue(), ns=None):

        self.app = Flask(__name__)
        self.app.secret_key="MAGFest is a donut"
        self.command_queue = command_queue
        if ns == None:

            self.ns = Manager().Namespace()
            self.ns.status = dict()
            self.ns.settings = {
                'sensitivity':1, 
                'red_on_kill':False,
                'random_team_size':3,
                'force_all_start':False,
                'color_lock_choices':{
                    2: ['Magenta','Green'],
                    3: ['Orange','Turquoise','Purple'],
                    4: ['Yellow','Green','Blue','Purple']
            }}
            self.ns.battery_status = dict()
        else:
            self.ns = ns

        self.app.add_url_rule('/','index',self.index)
        self.app.add_url_rule('/changemode','change_mode',self.change_mode)
        self.app.add_url_rule('/startgame','start_game',self.start_game)
        self.app.add_url_rule('/killgame','kill_game',self.kill_game)
        self.app.add_url_rule('/updateStatus','update',self.update)
        self.app.add_url_rule('/battery','battery_status',self.battery_status)
        self.app.add_url_rule('/settings','settings',self.settings, methods=['GET','POST'])
        self.app.add_url_rule('/rand<num_teams>','randomize',self.randomize_teams)
        self.app.add_url_rule('/power','power',self.power)
        self.app.add_url_rule('/reboot8675309','reboot',self.reboot)
        self.app.add_url_rule('/shutdown8675309','shutdown',self.shutdown)
        self.app.add_url_rule('/shutdown','shutdown_lastscreen',self.shutdown_lastscreen)


    def web_loop(self):
        self.app.run(host='0.0.0.0', port=80, debug=False)

    def web_loop_with_debug(self):
        self.app.run(host='0.0.0.0', port=80, debug=True)

    #@app.route('/')
    def index(self):
        return render_template('joustmania.html')

    #@app.route('/updateStatus')
    def update(self):
        return json.dumps(self.ns.status)

    #@app.route('/changemode')
    def change_mode(self):
        self.command_queue.put({'command': 'changemode'})
        return "{'status':'OK'}"

    #@app.route('/startgame')
    def start_game(self):
        self.command_queue.put({'command': 'startgame'})
        return "{'status':'OK'}"

    #@app.route('/killgame')
    def kill_game(self):
        self.command_queue.put({'command': 'killgame'})
        return "{'status':'OK'}"

    #@app.route('/battery')
    def battery_status(self):
        return render_template('battery.html',ns=self.ns,levels=common.battery_levels)

    #@app.route('/power')
    def power(self):
        return render_template('power.html')

    #@app.route('/shutdown8675309')
    def shutdown(self):
        Process(target=self.shutdown_proc).start()
        #use redirect to conceal the url for tripping the shutdown
        return redirect(url_for('shutdown_lastscreen'))

    def shutdown_proc(self):
        sleep(2)
        system("supervisorctl stop joustmania ; shutdown -H now ; kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}')")

    #@app.route('/shutdown_lastscreen')
    def shutdown_lastscreen(self):
        return render_template('shutdown.html')

    #@app.route('/reboot8675309')
    def reboot(self):
        Process(target=self.reboot_proc).start()
        return redirect(url_for('index'))

    def reboot_proc(self):
        sleep(2)
        system("supervisorctl stop joustmania ; reboot now ; kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}')")
        

    #@app.route('/settings')
    def settings(self):
        if request.method == 'POST':
            new_settings = SettingsForm(request.form).data
            self.web_settings_update(new_settings)
            return redirect(url_for('settings'))
        else:
            temp_colors = self.ns.settings['color_lock_choices']
            temp_colors = temp_colors[2] + temp_colors[3] + temp_colors[4]
            settingsForm = SettingsForm(
                sensitivity = self.ns.settings['sensitivity'],
                red_on_kill = self.ns.settings['red_on_kill'],
                random_team_size = self.ns.settings['random_team_size'],
                force_all_start = self.ns.settings['force_all_start'],
                color_lock_choices = temp_colors
            )
            return render_template('settings.html', form=settingsForm, settings=self.ns.settings)

    def web_settings_update(self,web_settings):
        colors_are_good = True
        temp_colors = {
            2: web_settings['color_lock_choices'][0:2],
            3: web_settings['color_lock_choices'][2:5],
            4: web_settings['color_lock_choices'][5:9],
        }
        for key in temp_colors.keys():
            colorset = temp_colors[key]
            if len(colorset) != len(set(colorset)):
                temp_colors[key] = self.ns.settings['color_lock_choices'][key]
                colors_are_good = False

        temp_settings = self.ns.settings
        temp_settings.update(web_settings)
        temp_settings['color_lock_choices'] = temp_colors

        #secret setting, keep it True
        #temp_settings['enforce_minimum'] = 'enforce_minimum' in web_settings.keys()
        if temp_settings['random_modes'] == []:
            temp_settings['random_modes'] = [common.Games.JoustFFA.name]

        self.ns.settings = temp_settings

        with open(common.SETTINGSFILE,'w') as yaml_file:
            yaml.dump(self.ns.settings,yaml_file)

        if colors_are_good:
            flash('Settings updated!')
        else:
            flash('Duplicate color lock colors! Other settings saved.')

    #@app.route('/rand<num_teams>')
    def randomize_teams(self,num_teams):
        if num_teams not in '234':
            return "what are you doing here?"
        else:
            num_teams = int(num_teams)
            team_colors = colors.generate_team_colors(num_teams)
            team_colors = [color.name for color in team_colors]
            return str(team_colors).replace("'",'"')#JSON is dumb and demands double quotes

def start_web(command_queue, ns):
    webui = WebUI(command_queue,ns)
    webui.web_loop()

if __name__ == '__main__':
    webui = WebUI()
    webui.web_loop_with_debug()
