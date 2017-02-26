import piparty
from multiprocessing import Process, Queue
from time import sleep
from flask import Flask, render_template

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
    commandQueue.put('changemode')

@app.route('/startgame')
def start_game():
    commandQueue.put('startgame')

@app.route('/killgame')
def kill_game():
    commandQueue.put('killgame')


@app.route('/updateStatus')
def update():
    commandQueue.put('update')
    print('command sent')
    updateInfo = statusQueue.get()
    print(updateInfo)
    return updateInfo

if __name__ == '__main__':

    commandQueue = Queue()
    statusQueue = Queue()
    joustApp = piparty.Menu(commandQueue,statusQueue)
    joustProc = Process(target=joustApp.game_loop)
    joustProc.start()
    app.run(host='0.0.0.0', port=80)