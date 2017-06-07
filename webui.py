from multiprocessing import Queue
from time import sleep
from flask import Flask, render_template, request
from time import sleep


class WebUI():
    def __init__(self, command_queue=Queue(), status_queue=Queue()):

        self.app = Flask(__name__)
        self.commandQueue = command_queue
        self.statusQueue = status_queue

        self.app.add_url_rule('/','index',self.index)
        self.app.add_url_rule('/changemode','change_mode',self.change_mode)
        self.app.add_url_rule('/startgame','start_game',self.start_game)
        self.app.add_url_rule('/killgame','kill_game',self.kill_game)
        self.app.add_url_rule('/admin_update','admin_update',self.admin_update,methods=['POST'])
        self.app.add_url_rule('/updateStatus','update',self.update)


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

    #@app.route('/admin_update', methods=['POST'])
    def admin_update(self):
        print('lol')
        adminInfo = request.form
        for x in adminInfo.keys():
            print(x)
        self.commandQueue.put({'command': 'admin_update', 'admin_info': adminInfo})
        return "{'status':'OK'}"

    #@app.route('/updateStatus')
    def update(self):
        while not(self.statusQueue.empty()):
            self.updateInfo = self.statusQueue.get()
        #    print('grabbed info')
        #print(self.updateInfo)
        return self.updateInfo
