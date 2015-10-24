import psmove
import os

BT_DIR = '/var/lib/bluetooth/'

class Oustpair():
    def __init__(self):
        self.bt_devices = {}
        devices =  os.listdir(BT_DIR)
        for device in devices:
            self.bt_devices[device] = []
        self.pre_existing_devices()

    def pre_existing_devices(self):
        for device in self.bt_devices.keys():
            trust_file = os.path.join(BT_DIR , device, 'trusts')
            if os.path.exists(trust_file):
                file = open(trust_file, 'rb')
                dev_split = [dev.split(' ')[0] for dev in file.readlines()]
                self.bt_devices[device] = dev_split

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

    def equal_pair(self, move):
        if move and move.get_serial():
            if move.connection_type == psmove.Conn_USB:
                self.pre_existing_devices()
                if self.check_if_not_paired(move.get_serial().upper()):
                    move.pair_custom(self.get_lowest_bt_device())