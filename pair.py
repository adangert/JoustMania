import controller_manager
import os

from sys import platform
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

        # Remove unplugged adapters as well as adding new ones. Otherwise a
        # hot-swap can leave pairing aimed at an address that no longer exists,
        # causing PSMoveAPI to fall back to its first enumerated adapter.
        self.bt_devices = {
            addr: self.bt_devices.get(addr, [])
            for addr in self.hci_dict.values()
        }

        self.pre_existing_devices()

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

    def pair_move(self, move_controller):
        if move_controller and move_controller.serial:
            if move_controller.usb and not move_controller.bluetooth:
                # Adapter dongles can be hot-swapped while JoustMania runs.
                # Refresh names and addresses immediately before choosing.
                self.update_adapters()
                # A saved BlueZ registration does not prove that the controller
                # still stores this Pi as its Bluetooth host. Pairing over USB
                # rewrites that address after use with another computer.
                host_address = self.get_lowest_bt_device()
                paired = controller_manager.pair_controller(host_address)
                if paired:
                    # BlueZ may need a few seconds to publish the registration.
                    # Reserve it immediately so another controller paired in
                    # that window is assigned to the next least-loaded adapter.
                    self.bt_devices.setdefault(host_address, [])
                    if move_controller.serial not in self.bt_devices[host_address]:
                        self.bt_devices[host_address].append(move_controller.serial)
                return paired
        return False
