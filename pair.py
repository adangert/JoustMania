import psmove
import os

BT_DIR = '/var/lib/bluetooth/'

class Pair():
    def __init__(self):
        self.bt_devices = {}
        devices = os.listdir(BT_DIR)
        for device in devices:
            self.bt_devices[device] = []
        self.pre_existing_devices()

    def pre_existing_devices(self):
        for device in self.bt_devices.keys():
            device_path = os.path.join(BT_DIR, device)
            print ('trust file is ' + str(device_path))
            if os.path.exists(device_path):
                self.bt_devices[device] = [bt for bt in os.listdir(device_path) if ':' in bt]
            else:
                print('the path doesnt exist! ' )

    def check_if_not_paired(self, addr):
        for devs in self.bt_devices.keys():
            if addr in self.bt_devices[devs]:
                return False
        return True 

    def get_lowest_bt_device(self):
        num = 9999999
        for dev in self.bt_devices.keys():
            if len(self.bt_devices[dev]) < num:
                num = len(self.bt_devices[dev])

        for dev in self.bt_devices.keys():
            if len(self.bt_devices[dev]) == num:
                return dev
        return ''

    def pair_move(self, move):
        if move and move.get_serial():
            if move.connection_type == psmove.Conn_USB:
                self.pre_existing_devices()
                if self.check_if_not_paired(move.get_serial().upper()):
                    move.pair_custom(self.get_lowest_bt_device())
