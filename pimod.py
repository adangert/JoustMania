#WATCH OUT THIS NO LONGER WORKS

import piparty
from multiprocessing import Queue, Process
from threading import Thread
from time import sleep
from flask import Flask, render_template, request
from time import sleep

app = Flask(__name__)

# @app.route('/')
# def index():
#     commandQueue.put('update')
#     print('command sent')
#     updateInfo = statusQueue.get()
#     print(updateInfo)
#     return render_template('joustmania.html', **updateInfo)

@app.route('/')
def index():
    return render_template('joustmania.html')

@app.route('/changemode')
def change_mode():
    commandQueue.put({'command': 'changemode'})
    return "{'status':'OK'}"

@app.route('/startgame')
def start_game():
    commandQueue.put({'command': 'startgame'})
    return "{'status':'OK'}"

@app.route('/killgame')
def kill_game():
    commandQueue.put({'command': 'killgame'})
    return "{'status':'OK'}"

@app.route('/admin_update', methods=['POST'])
def admin_update():
    print('lol')
    adminInfo = request.form
    for x in adminInfo.keys():
        print(x)
    commandQueue.put({'command': 'admin_update', 'admin_info': adminInfo})
    return "{'status':'OK'}"

updateInfo = {}
@app.route('/updateStatus')
def update():
    global updateInfo
    #commandQueue.put({'command': 'status'})
    #print('command sent')
    #sleep(0.1)
    while not(statusQueue.empty()):
        updateInfo = statusQueue.get()
        print('grabbed info')
    print(updateInfo)
    return updateInfo

if __name__ == '__main__':
    commandQueue = Queue()
    statusQueue = Queue()
    joustApp = piparty.Menu(commandQueue,statusQueue)
    joustProc = Process(target=joustApp.game_loop)
    joustProc.start()
    app.run(host='0.0.0.0', port=80, debug=False)