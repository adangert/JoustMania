from multiprocessing import Queue, Manager
from time import sleep
from flask import Flask, render_template, request, redirect, url_for, flash
from time import sleep
from wtforms import Form, SelectField, SelectMultipleField, BooleanField, widgets
import common
import json

class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """
    widget = widgets.ListWidget(prefix_label=True)
    option_widget = widgets.CheckboxInput()


class SettingsForm(Form):
    move_admin = BooleanField('Allow Move to change settings')
    instructions = BooleanField('Play instructions before game start')
    audio = BooleanField('Play audio')
    sensitivity = SelectField('Move sensitivity',choices=[(0,'Slow'),(1,'Medium'),(2,'Fast')],coerce=int)

    mode_options = [ game for game in common.Games if game not in [common.Games.Random, common.Games.JoustTeams]]
    random_modes = MultiCheckboxField('Random Modes',choices=[(game.pretty_name, game.pretty_name) for game in mode_options])

class WebUI():
    def __init__(self, command_queue=Queue(), ns=Manager().Namespace()):

        self.app = Flask(__name__)
        self.app.secret_key="MAGFest is a donut"
        self.command_queue = command_queue
        self.status_ns = ns
        self.status_ns.status_dict = dict()

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
        return render_template('battery.html',ns=self.status_ns,levels=common.battery_levels)

    #@app.route('/settings')
    def settings(self):
        if request.method == 'POST':
            adminInfo = request.form
            self.command_queue.put({'command': 'admin_update', 'admin_info': adminInfo})
            sleep(.5) #because it takes a short amount of time to settings to update in the main thread
            flash('Settings updated!')
            return redirect(url_for('settings'))
        else:
            settingsForm = SettingsForm()
            settingsForm.sensitivity.default = self.status_ns.status_dict['sensitivity']
            settingsForm.process()
            return render_template('settings.html', form=settingsForm, settings=self.status_ns.status_dict)

    #@app.route('/updateStatus')
    def update(self):
        return json.dumps(self.status_ns.status_dict)

def start_web(command_queue, ns):
    webui = WebUI(command_queue,ns)
    webui.web_loop()

if __name__ == '__main__':
    webui = WebUI()
    webui.web_loop()
