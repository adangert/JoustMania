import psmove
import os
import dbus
from xml.etree import ElementTree

class Pair():
    """
    Manage paring move controllers to the server
    """
    def __init__(self):
        """Use DBus to find bluetooth controllers"""
        bus = dbus.SystemBus()
        proxy = bus.get_object('org.bluez', '/org/bluez')
        hcis = self.__get_node_child_names__(proxy)
        self.hci_dict = {}
        for hci in hcis:
            hci_path = os.path.join('/org/bluez', hci)
            proxy2 = bus.get_object('org.bluez', hci_path)
            addr = self.__get_adapter_attrib__(proxy2, 'Address')
            self.hci_dict[hci] = str(addr)

        devices = self.hci_dict.values()
        self.bt_devices = {}
        for device in devices:
            self.bt_devices[device] = []

        self.pre_existing_devices()

    def pre_existing_devices(self):
        """
        Enumerate paired devices
        
        For each device on each adapter, add the device's address to it's adapter's
        list of paired devices
        """
        bus = dbus.SystemBus()
        for hci, addr in self.hci_dict.items():
            hci_path = os.path.join('/org/bluez', hci)
            proxy = bus.get_object('org.bluez', hci_path)

            devices = self.__get_node_child_names__(proxy)

            for dev in devices:
                dev_path = os.path.join('/org/bluez', hci, dev)
                proxy2 = bus.get_object('org.bluez', dev_path)

                dev_addr = str(self.__get_device_attrib__(proxy2, 'Address'))
                dev_paired = self.__get_device_attrib__(proxy2, 'Paired').real
                if dev_paired:
                    self.bt_devices[addr].append(dev_addr)

    def __get_bluez_attrib__(self, proxy, kind, attrib):
        """Abstract getting attributes from Bluez DBus Interfaces"""
        iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
        return iface.Get('org.bluez.{0}'.format(kind), attrib)

    def __get_adapter_attrib__(self, proxy, attrib):
        """Abstract getting attributes from Bluez Adapter1 Interfaces"""
        return self.__get_bluez_attrib__(proxy, 'Adapter1', attrib)

    def __get_device_attrib__(self, proxy, attrib):
        """Abstract getting attributes from Bluez Device1 Interfaces"""
        return self.__get_bluez_attrib__(proxy, 'Device1', attrib)

    def __get_node_child_names__(self, proxy):
        """Abstract finding child nodes of a DBus Node"""
        iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Introspectable')
        tree = ElementTree.fromstring(iface.Introspect())
        return [child.attrib['name'] for child in tree if child.tag == 'node']


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
