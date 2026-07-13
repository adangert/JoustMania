import controller_manager
import colorsys
import time
from math import sqrt
from multiprocessing import Process, Queue
from time import sleep

connections = controller_manager.get_manager().connected_controllers()

colors = ['FF0000','FF8000','FFFF00','80FF00','00FF00','00FF80','00FFFF','0080FF','0000FF','8000FF','FF00FF','FF0080']

def colorhex(hex):
    r = int(hex[0:2],16)
    g = int(hex[2:4],16)
    b = int(hex[4:6],16)
    return (r,g,b)

colors = [colorhex(x) for x in colors]

def color_proc(q,):
    connections = controller_manager.get_manager().connected_controllers()
    while True:
        while not q.empty():
            colors = q.get()
        for connection, color in zip(connections, colors):
            connection.set_color(*color)
        sleep(.25)

q = Queue()
q.put(colors)
proc = Process(target=color_proc, args=(q,))
proc.start()
sleep(1)
while True:
    moveid = input("Enter move number: ")
    try:
        newcolor_string = input("Enter color hex: ")
        newcolor = colorhex(newcolor_string)
        colors[int(moveid)-1] = newcolor
    except:
        print('Error! Enter again.')
    q.put(colors)
    q.put(colors)
    for move,color in zip(moves,colors):
        print("MOVE ID: %s, COLOR %s" % (move.get_serial(),str(color)))
