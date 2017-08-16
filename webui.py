from multiprocessing import Queue
from time import sleep
from flask import Flask, render_template, request
from time import sleep
from wtforms import Form, SelectField, SelectMultipleField, BooleanField, widgets
import common

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
    sensitivity = SelectField('Move sensitivity',choices=[(0,'Slow'),(1,'Medium'),(2,'Fast')],coerce=int)
    #toggles = [('toggle %s' % s,s) for s in common.gameModeNames]
    random_modes = MultiCheckboxField('Random Modes',choices=[(s,s) for s in common.gameModeNames])

class WebUI():
    def __init__(self, command_queue=Queue(), status_queue=Queue()):

        self.app = Flask(__name__)
        self.commandQueue = command_queue
        self.statusQueue = status_queue

        self.app.add_url_rule('/','index',self.index)
        self.app.add_url_rule('/changemode','change_mode',self.change_mode)
        self.app.add_url_rule('/startgame','start_game',self.start_game)
        self.app.add_url_rule('/killgame','kill_game',self.kill_game)
        self.app.add_url_rule('/updateStatus','update',self.update)
        self.app.add_url_rule('/settings','settings',self.settings, methods=['GET','POST'])


    def web_loop(self):
        self.app.run(host='0.0.0.0', port=80, debug=True)

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
            print(adminInfo)
            #self.commandQueue.put({'command': 'admin_update', 'admin_info': adminInfo})
            return redirect(url_for('settings'))
        else:
            settingsForm = SettingsForm(request.form)
            #self.commandQueue.put({'command': 'getsettings'})
            return render_template('settings.html', form=settingsForm)

    #@app.route('/updateStatus')
    def update(self):
        updateInfo = "{'status':'lol'}"
        while not(self.statusQueue.empty()):
            updateInfo = self.statusQueue.get()
        return updateInfo

if __name__ == '__main__':
    webui = WebUI()
    webui.web_loop()