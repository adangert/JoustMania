#This is testing joust controller latency and hz and frame buffer
#basic results:
#old psmove controller approx 88 hz for each recieved message
#two frames per message so approx 176 hz
#buffer of 64-65 new messages held when doing move.poll()

#new move controller!
#approx 790 hz! first and second frames are the same
#around 90 -160 held in buffer


import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'build'))

import psmove

if psmove.count_connected() < 1:
    print('No controller connected')
    sys.exit(1)
    
psmoves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
print(psmoves)
print(psmoves[0].get_serial())

move = psmoves[0]

#if move.connection_type != psmove.Conn_Bluetooth:
#    print('Please connect controller via Bluetooth')
#    sys.exit(1)

#assert move.has_calibration()
counter = 0
timer = time.time()
avger = []
while counter < 1000:
    a = move.poll()
    counter = 0
    while a:
	    time_since_last = time.time() - timer
	    avger.append(time_since_last)
	    timer = time.time()
	    print(time_since_last)
	    print(str(1/(sum(avger)/len(avger)))+" hz")
	    counter += 1
	    #print("got the poll")
	    print(a)
	    ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
	    gx, gy, gz = move.get_gyroscope_frame(psmove.Frame_SecondHalf)
	    ax2, ay2, az2 = move.get_accelerometer_frame(psmove.Frame_FirstHalf)
	    gx2, gy2, gz2 = move.get_gyroscope_frame(psmove.Frame_FirstHalf)
	    print( 'A: %5.2f %5.2f %5.2f ' % (ax, ay, az))
	    print('G: %6.2f %6.2f %6.2f ' % (gx, gy, gz))
	    print( 'A: %5.2f %5.2f %5.2f ' % (ax2, ay2, az2))
	    print('G: %6.2f %6.2f %6.2f ' % (gx2, gy2, gz2))
	    a = move.poll()
    #print("bloop")
    print(counter)
    #print("now to sleeeep\n\n\n")
    #time.sleep(0.75)
    time.sleep(4)
    
	    


