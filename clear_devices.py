import jm_dbus
import psmove_dbus


if __name__ == '__main__':
    hcis = jm_dbus.get_hci_dict().keys()
    removed = 0
    for hci in hcis:
        hci_proxy = jm_dbus.get_adapter_proxy(hci)
        devices = jm_dbus.get_node_child_names(hci_proxy)

        for dev in devices:
            proxy = jm_dbus.get_device_proxy(hci, dev)
            properties = jm_dbus.get_device_properties(proxy)
            if psmove_dbus.is_psmove_device(properties):
                address = str(jm_dbus.get_device_attrib(proxy, 'Address'))
                print('Removing PS Move {} from {}'.format(address, hci))
                jm_dbus.remove_device(hci, dev)
                removed += 1

    print('Removed {} PS Move controller registration(s)'.format(removed))
