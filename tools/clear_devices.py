import jm_dbus

if __name__ == '__main__':
    hcis = jm_dbus.get_hci_dict().keys()
    for hci in hcis:
        hci_proxy = jm_dbus.get_adapter_proxy(hci)
        devices = jm_dbus.get_node_child_names(hci_proxy)

        for dev in devices:
            jm_dbus.remove_device(hci, dev)
