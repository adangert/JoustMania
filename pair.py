import controller_manager
import pairing_plan
import os
import logging

from sys import platform
if platform == "linux" or platform == "linux2":
    import jm_dbus
    from dbus import DBusException
elif platform == "windows" or platform == "win32":
    import win_jm_dbus as jm_dbus
    DBusException = OSError
    
import update

class Pair():
    """
    Manage paring move controllers to the server
    """
    def __init__(self, ns=None):
        """Use DBus to find bluetooth controllers"""
        self.ns = ns
        self.hci_dict = {}
        self.bt_devices = {}
        self.update_adapters()

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
        try:
            self.hci_dict = jm_dbus.get_hci_dict()
        except DBusException as error:
            logging.getLogger(__name__).warning("Bluetooth unavailable: %s", error)
            self.hci_dict = {}

        # Remove unplugged adapters as well as adding new ones. Otherwise a
        # hot-swap can leave pairing aimed at an address that no longer exists,
        # causing PSMoveAPI to fall back to its first enumerated adapter.
        self.bt_devices = {
            addr: self.bt_devices.get(addr, [])
            for addr in self.hci_dict.values()
        }

        try:
            self.pre_existing_devices()
        except DBusException:
            # An adapter can disappear between discovery and enumeration.
            self.hci_dict = {}
            self.bt_devices = {}

    def get_lowest_bt_device(self):
        # Compatibility path for callers without shared UI selection state.
        for address, devices in self.bt_devices.items():
            if len(devices) < 5:
                return address
        if not self.bt_devices:
            return ''
        return min(self.bt_devices, key=lambda address: len(self.bt_devices[address]))

    def pair_move(self, move_controller):
        if move_controller and move_controller.serial:
            if move_controller.usb and not move_controller.bluetooth:
                # Adapter dongles can be hot-swapped while JoustMania runs.
                # Refresh names and addresses immediately before choosing.
                self.update_adapters()
                # A saved BlueZ registration does not prove that the controller
                # still stores this Pi as its Bluetooth host. Pairing over USB
                # rewrites that address after use with another computer.
                ns = getattr(self, 'ns', None)
                host_address = pairing_plan.begin(ns, move_controller.serial) if ns is not None else self.get_lowest_bt_device()
                if not host_address:
                    return False
                paired = False
                try:
                    paired = controller_manager.pair_controller(host_address)
                finally:
                    if ns is not None:
                        pairing_plan.finish(ns, move_controller.serial, host_address, paired)
                if paired:
                    # BlueZ may need a few seconds to publish the registration.
                    # Reserve it immediately so another controller paired in
                    # that window is assigned to the next least-loaded adapter.
                    self.bt_devices.setdefault(host_address, [])
                    if move_controller.serial not in self.bt_devices[host_address]:
                        self.bt_devices[host_address].append(move_controller.serial)
                return paired
        return False
