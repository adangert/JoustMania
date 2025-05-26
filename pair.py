import psmove
import os

from sys import platform
print(platform)
if platform == "linux" or platform == "linux2":
    import jm_dbus
elif platform == "windows" or platform == "win32":
    import win_jm_dbus as jm_dbus
    
import update

class Pair():
    """
    Manage paring move controllers to the server
    """
    def __init__(self):
        """Use DBus to find bluetooth controllers"""
        self.hci_dict = jm_dbus.get_hci_dict()

        devices = self.hci_dict.values()
        self.bt_devices = {}
        for device in devices:
            self.bt_devices[device] = []

        self.pre_existing_devices()

    def pre_existing_devices(self):
        """
        Enumerate known devices

        For each device on each adapter, add the device's address to it's adapter's
        list of known devices
        """
        for hci, addr in self.hci_dict.items():
            proxy = jm_dbus.get_adapter_proxy(hci)
            devices = jm_dbus.get_node_child_names(proxy)

            self.bt_devices[addr] = jm_dbus.get_attached_addresses(hci)

    def update_adapters(self):
        """
        Rescan for bluetooth adapters that may not have existed on program launch
        """
        self.hci_dict = jm_dbus.get_hci_dict()

        for addr in self.hci_dict.values():
            if addr not in self.bt_devices.keys():
                self.bt_devices[addr] = []

        self.pre_existing_devices()

    def check_if_not_paired(self, addr):
        for devs in self.bt_devices.keys():
            if addr in self.bt_devices[devs]:
                return False
        return True

    def get_lowest_bt_device(self):
        num = 9999999
        print(self.bt_devices)
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
                #in order to add the new controller to the bluetooth service, restart
                #Otherwise it will not be recognized
                update.run_command("sudo systemctl restart bluetooth")
