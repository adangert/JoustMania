import piparty
from multiprocessing import Process, Queue
from time import sleep
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    commandQueue.put('update')
    print('command sent')
    updateInfo = statusQueue.get()
    print(updateInfo)
    return render_template('joustmania.html', **updateInfo)

@app.route('/#secret')
def index2():
    print('oh noes!')
    commandQueue.put('update')
    print('command sent')
    updateInfo = statusQueue.get()
    print(updateInfo)
    return render_template('joustmania.html', **updateInfo)

if __name__ == '__main__':

    commandQueue = Queue()
    statusQueue = Queue()
    joustApp = piparty.Menu(commandQueue,statusQueue)
    joustProc = Process(target=joustApp.game_loop)
    joustProc.start()
    app.run(host='0.0.0.0', port=80)