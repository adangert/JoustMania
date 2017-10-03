from multiprocessing import Queue, Manager
from time import sleep
from flask import Flask, render_template, request, redirect, url_for, flash
from time import sleep
from wtforms import Form, SelectField, SelectMultipleField, BooleanField, widgets
import common
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
    sensitivity = SelectField('Move sensitivity',choices=[(0,'Slow'),(1,'Medium'),(2,'Fast')],coerce=int)
    mode_options = [ game for game in common.Games if game not in [common.Games.Random, common.Games.JoustTeams]]
    random_modes = MultiCheckboxField('Random Modes',choices=[(game.pretty_name, game.pretty_name) for game in mode_options])


class WebUI():
    def __init__(self, command_queue=Queue(), ns=None):

        self.app = Flask(__name__)
        self.app.secret_key="MAGFest is a donut"
        self.command_queue = command_queue
        if ns == None:

            self.ns = Manager().Namespace()
            self.ns.status = dict()
            self.ns.settings = dict()
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


    def web_loop(self):
        self.app.run(host='0.0.0.0', port=80, debug=False)

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

    #@app.route('/settings')
    def settings(self):
        if request.method == 'POST':
            self.web_settings_update(request.form)
            flash('Settings updated!')
            return redirect(url_for('settings'))
        else:
            settingsForm = SettingsForm()
            settingsForm.sensitivity.default = self.ns.settings['sensitivity']
            settingsForm.process()
            return render_template('settings.html', form=settingsForm, settings=self.ns.settings)

    def web_settings_update(self,web_settings):
        temp_settings = self.ns.settings

        temp_settings['move_can_be_admin'] = 'move_can_be_admin' in web_settings.keys()
        temp_settings['play_audio'] = 'play_audio' in web_settings.keys()
        temp_settings['play_instructions'] = 'play_instructions' in web_settings.keys()
        #secret setting, keep it True
        #temp_settings['enforce_minimum'] = 'enforce_minimum' in web_settings.keys()
        temp_settings['sensitivity'] = int(web_settings['sensitivity'])
        temp_settings['con_games'] = [int(x) for x in web_settings.getlist('con_games')]
        #print(self.con_games)
        if temp_settings['con_games'] == []:
            temp_settings['con_games'] = [common.Games.JoustFFA]

        self.ns.settings = temp_settings

        with open(common.SETTINGSFILE,'w') as yaml_file:
            yaml.dump(self.ns.settings,yaml_file)

def start_web(command_queue, ns):
    webui = WebUI(command_queue,ns)
    webui.web_loop()

if __name__ == '__main__':
    webui = WebUI()
    webui.web_loop()
