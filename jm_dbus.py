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

def get_attached_addresses(hci):
    """Get the addresses of devices known by hci"""
    proxy = get_adapter_proxy(hci)
    devices = get_node_child_names(proxy)

    known_devices = []
    for dev in devices:
        proxy2 = get_device_proxy(hci, dev)

        dev_addr = str(get_device_attrib(proxy2, 'Address'))
        known_devices.append(dev_addr)

    return known_devices

def get_bus():
    """Get DBus hook"""
    return BUS

def get_root_proxy():
    """Get root Bluez DBus node"""
    return BUS.get_object(ORG_BLUEZ, ORG_BLUEZ_PATH)

def enable_pairable(hci):
    """Allow devices to pair with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if not iface.Get('org.bluez.Adapter1', 'Pairable'):
        iface.Set('org.bluez.Adapter1', 'Pairable', True)

def disable_pairable(hci):
    """Prevent devices from pairing with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Pairable'):
        iface.Set('org.bluez.Adapter1', 'Pairable', False)

def get_discovery_filters(hci):
    """Get information about discovery options"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    return iface.GetDiscoveryFilters()

def start_discovery(hci):
    """Start scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    if not get_adapter_attrib(proxy, 'Discovering').real:
        try:
            return iface.StartDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e

def stop_discovery(hci):
    """Stop scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    if get_adapter_attrib(proxy, 'Discovering').real:
        try:
            return iface.StopDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e

def remove_device(hci, dev):
    hci_proxy = get_adapter_proxy(hci)
    dev_proxy = get_device_proxy(hci, dev)
    iface = dbus.Interface(hci_proxy, 'org.bluez.Adapter1')
    return iface.RemoveDevice(dev_proxy)

def enable_adapter(hci):
    """Set the HCI's Powered attribute to true"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Powered').real:
        return False
    else:
        try:
            print('Enabling adapter')
            iface.Set('org.bluez.Adapter1', 'Powered', True)
            return True
        except dbus.exceptions.DBusException as e:
            if "rfkill" in str(e):
                rfkill_unblock(hci)
                # Recurse after unblocking the bluetooth adapter
                return enable_adapter(hci)
            else:
                raise e

def rfkill_unblock(hci):
    hci_id = os.popen('rfkill list | grep {0} | cut -d ":" -f 1'.format(hci)).read().split('\n')[0]
    os.popen('rfkill unblock {0}'.format(hci_id)).read()

def disable_adapter(hci):
    """Set the HCI's Powered attribute to false"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Powered').real:
        iface.Set('org.bluez.Adapter1', 'Powered', False)
        return True
    else:
        return False

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
