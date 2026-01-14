import subprocess
from sys import platform

import psmove

if platform == "linux" or platform == "linux2":
    from services.controller_manager import bluetooth as jm_dbus
elif platform == "windows" or platform == "win32":
    # Windows pairing is handled by OS, not used here
    jm_dbus = None


class Pair:
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
            jm_dbus.get_node_child_names(proxy)

            self.bt_devices[addr] = jm_dbus.get_attached_addresses(hci)

    def update_adapters(self):
        """
        Rescan for bluetooth adapters that may not have existed on program launch
        """
        self.hci_dict = jm_dbus.get_hci_dict()

        for addr in self.hci_dict.values():
            if addr not in self.bt_devices:
                self.bt_devices[addr] = []

        self.pre_existing_devices()

    def check_if_not_paired(self, addr):
        return all(addr not in self.bt_devices[devs] for devs in self.bt_devices)

    def get_lowest_bt_device(self):
        num = 9999999
        print(self.bt_devices)
        for dev in self.bt_devices:
            if len(self.bt_devices[dev]) < num:
                num = len(self.bt_devices[dev])

        for dev in self.bt_devices:
            if len(self.bt_devices[dev]) == num:
                return dev
        return ""

    def pair_move(self, move):
        if move and move.get_serial() and move.connection_type == psmove.Conn_USB:
            self.pre_existing_devices()
            if self.check_if_not_paired(move.get_serial().upper()):
                move.pair_custom(self.get_lowest_bt_device())
            # Restart bluetooth service to recognize new controller
            self._restart_bluetooth()

    def _restart_bluetooth(self):
        """
        Restart bluetooth service - tries multiple methods.

        1. Unix socket (Docker -> host helper)
        2. systemctl (native Linux)
        """
        # Method 1: Try Unix socket (for Docker containers)
        socket_path = "/var/run/joustmania/bluetooth.sock"
        try:
            import socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(socket_path)
            sock.sendall(b"restart")
            sock.close()
            print("[PAIRING] Sent bluetooth restart request via socket")
            return
        except FileNotFoundError:
            pass  # Socket doesn't exist, try next method
        except Exception as e:
            print(f"[PAIRING] Socket failed: {e}")

        # Method 2: Try systemctl directly (native Linux)
        try:
            subprocess.run(["systemctl", "restart", "bluetooth"], check=False, timeout=5)
            print("[PAIRING] Restarted bluetooth via systemctl")
        except FileNotFoundError:
            print("[PAIRING] No systemctl available - restart bluetooth manually on host")
        except Exception:
            pass
