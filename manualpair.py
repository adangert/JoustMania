import controller_manager
import pair

pairObj = pair.Pair()

exit = False
while not exit:
	manager = controller_manager.get_manager()
	connected = manager.count_connected()
	input("Connect Moves via USB and press Enter.\nOr disconnect all USB Moves and press Enter to quit.")
	print("Moves connected: %d" % connected)
	connections = manager.connected_controllers()
	exit = True
	for connection in connections:
		print("Move %s connected via USB=%s Bluetooth=%s" %
			(connection.serial, connection.usb, connection.bluetooth))
		if connection.usb and not connection.bluetooth:
			pairObj.pair_move(connection)
			exit = False
