from multiprocessing import Queue
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
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class SettingsForm(Form):
    move_admin = BooleanField('Allow Move to change settings')
    instructions = BooleanField('Play instructions before game start')
    audio = BooleanField('Play audio')
    sensitivity = SelectField('Move sensitivity',choices=[(0,'Slow'),(1,'Medium'),(2,'Fast')],coerce=int)
    random_modes = MultiCheckboxField('Random Modes',choices=[(s,s) for s in common.game_mode_names if s != "Random"])

class WebUI():
    def __init__(self, command_queue=Queue(), status_queue=Queue()):

        self.app = Flask(__name__)
        self.app.secret_key="MAGFest is a donut"
        self.commandQueue = command_queue
        self.statusQueue = status_queue

        self.app.add_url_rule('/','index',self.index)
        self.app.add_url_rule('/changemode','change_mode',self.change_mode)
        self.app.add_url_rule('/startgame','start_game',self.start_game)
        self.app.add_url_rule('/killgame','kill_game',self.kill_game)
        self.app.add_url_rule('/updateStatus','update',self.update)
        self.app.add_url_rule('/settings','settings',self.settings, methods=['GET','POST'])


    def web_loop(self):
        self.app.run(host='0.0.0.0', port=80, debug=False)

    #@app.route('/')
    def index(self):
        return render_template('joustmania.html')

    #@app.route('/changemode')
    def change_mode(self):
        self.commandQueue.put({'command': 'changemode'})
        return "{'status':'OK'}"

    #@app.route('/startgame')
    def start_game(self):
        self.commandQueue.put({'command': 'startgame'})
        return "{'status':'OK'}"

    #@app.route('/killgame')
    def kill_game(self):
        self.commandQueue.put({'command': 'killgame'})
        return "{'status':'OK'}"


    #@app.route('/settings')
    def settings(self):
        if request.method == 'POST':
            adminInfo = request.form
            self.commandQueue.put({'command': 'admin_update', 'admin_info': adminInfo})
            sleep(.5) #because it takes a short amount of time to settings to update in the main thread
            flash('Settings updated!')
            return redirect(url_for('settings'))
        else:
            updateInfo = self.statusQueue.get()
            while not(self.statusQueue.empty()):
                updateInfo = self.statusQueue.get()
            #print(updateInfo)
            updateInfo = json.loads(updateInfo)
            settingsForm = SettingsForm()
            settingsForm.sensitivity.default = updateInfo['sensitivity']
            settingsForm.process()
            return render_template('settings.html', form=settingsForm, settings=updateInfo)

    #@app.route('/updateStatus')
    def update(self):
        updateInfo = "{'status':'lol'}"
        while not(self.statusQueue.empty()):
            updateInfo = self.statusQueue.get()
        return updateInfo

if __name__ == '__main__':
    webui = WebUI()
    webui.web_loop()