import sys
import os
import time
sys.path.insert(0, '/home/pi/psmoveapi/build/')
import psmove
import pair

pairObj = pair.Pair()

exit = False
while not exit:
	connected = psmove.count_connected()
	input("Connect Moves via USB and press Enter.\nOr disconnect all USB Moves and press Enter to quit.")
	print("Moves connected: %d" % connected)
	moves = [psmove.PSMove(x) for x in range(connected)]
	exit = True
	for move in moves:
		print("Move %s connected via %s" % (move.get_serial(), ['Bluetooth','USB'][move.connection_type]))
		move.poll()
		print("Temperature is %d" % move.get_temperature())
		if move.connection_type == psmove.Conn_USB:
			pairObj.pair_move(move)
			move.set_leds(100,100,100)
			exit = False
			move.update_leds()
