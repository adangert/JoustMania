"""
This module handles interacting with Bluez over DBus for JoustMania
"""
import os
import dbus
from xml.etree import ElementTree

BUS = dbus.SystemBus()
ORG_BLUEZ = 'org.bluez'
ORG_BLUEZ_PATH = '/org/bluez'

def get_hci_dict():
    """Get dictionary mapping hci number to address"""
    proxy = get_root_proxy()
    hcis = get_node_child_names(proxy)
    hci_dict = {}

    for hci in hcis:
        proxy2 = get_adapter_proxy(hci)
        addr = get_adapter_attrib(proxy2, 'Address')
        hci_dict[hci] = str(addr)

    return hci_dict

def get_connected_addresses(hci):
    """Get the addresses of devices connected with hci"""
    proxy = get_adapter_proxy(hci)
    devices = get_node_child_names(proxy)

    connected_devices = []
    for dev in devices:
        proxy2 = get_device_proxy(hci, dev)

        dev_addr = str(get_device_attrib(proxy2, 'Address'))
        dev_connected = get_device_attrib(proxy2, 'Connected').real
        if dev_connected:
            connected_devices.append(dev_addr)

    return connected_devices

def get_bus():
    """Get DBus hook"""
    return BUS

def get_root_proxy():
    """Get root Bluez DBus node"""
    return BUS.get_object(ORG_BLUEZ, ORG_BLUEZ_PATH)

def start_discovery(hci):
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    return iface.StartDiscovery()

def stop_discovery(hci):
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    return iface.StopDiscovery()

def get_adapter_proxy(hci):
    """Abstract getting Bluez DBus adapter nodes"""
    hci_path = os.path.join(ORG_BLUEZ_PATH, hci)
    return BUS.get_object(ORG_BLUEZ, hci_path)

def get_device_proxy(hci, dev):
    """Abstract getting Bluez DBus device nodes"""
    device_path = os.path.join(ORG_BLUEZ_PATH, hci, dev)
    return BUS.get_object(ORG_BLUEZ, device_path)

def get_bluez_attrib(proxy, kind, attrib):
    """Abstract getting attributes from Bluez DBus Interfaces"""
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    return iface.Get('org.bluez.{0}'.format(kind), attrib)

def get_adapter_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Adapter1 Interfaces"""
    return get_bluez_attrib(proxy, 'Adapter1', attrib)

def get_device_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Device1 Interfaces"""
    return get_bluez_attrib(proxy, 'Device1', attrib)

def get_node_child_names(proxy):
    """Abstract finding child nodes of a DBus Node"""
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Introspectable')
    tree = ElementTree.fromstring(iface.Introspect())
    return [child.attrib['name'] for child in tree if child.tag == 'node']
