"""Exercise real busctl JSON on a private test bus, never the machine's BlueZ."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

import proton_bluetooth_diagnostics as host


def serve(address):
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    DBusGMainLoop(set_as_default=True)
    bus = dbus.bus.BusConnection(address)
    name = dbus.service.BusName('org.bluez', bus)
    class ObjectManager(dbus.service.Object):
        @dbus.service.method('org.freedesktop.DBus.ObjectManager', in_signature='', out_signature='a{oa{sa{sv}}}')
        def GetManagedObjects(self):
            return {
                '/org/bluez/hci0': {'org.bluez.Adapter1': {
                    'Address': dbus.String('24:41:8C:C5:FA:E8'), 'Powered': dbus.Boolean(True)}},
                '/org/bluez/hci0/dev_test': {'org.bluez.Device1': {
                    'Address': dbus.String('00:06:F5:E1:2B:CA'), 'Connected': dbus.Boolean(True),
                    'Adapter': dbus.ObjectPath('/org/bluez/hci0'),
                    'Modalias': dbus.String('usb:v054Cp03D5d0100'),
                    'Paired': dbus.Boolean(True), 'Trusted': dbus.Boolean(True)}},
            }
    manager = ObjectManager(name, '/')
    GLib.MainLoop().run()


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('busctl') and shutil.which('dbus-daemon'),
                     'Requires Linux busctl and a private D-Bus test daemon')
class HostBusIntegrationTest(unittest.TestCase):
    def test_real_busctl_and_host_helper_json(self):
        try:
            import dbus
            from gi.repository import GLib
        except ImportError:
            self.skipTest('Python D-Bus and GLib are only required by the test service')
        daemon = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1', '--print-pid=1'],
                                capture_output=True, text=True, check=True, timeout=5)
        address, daemon_pid = daemon.stdout.strip().splitlines()
        self.addCleanup(os.kill, int(daemon_pid), signal.SIGTERM)
        environment = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=address)
        server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', address],
                                  env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def stop_server():
            server.terminate()
            server.communicate(timeout=5)
        self.addCleanup(stop_server)
        bus = dbus.bus.BusConnection(address)
        self.addCleanup(bus.close)
        deadline = time.monotonic() + 5
        while not bus.name_has_owner('org.bluez'):
            if server.poll() is not None:
                self.fail(server.stderr.read().decode())
            if time.monotonic() > deadline:
                self.fail('Test ObjectManager did not start')
            time.sleep(0.05)
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(host.bluetooth_diagnostics, 'get_adapter_identities', return_value=[]):
            state = host.snapshot()
        self.assertEqual(state['adapters'][0]['connections'], 1)
        self.assertEqual(state['controllers'][0]['adapter'], 'hci0')
        self.assertEqual(state['controllers'][0]['model'], 'ZCM1')
        self.assertTrue(state['controllers'][0]['trusted'])
        self.assertIsNone(state['adapters'][0]['rx_acl'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--serve':
        serve(sys.argv[2])
    else:
        unittest.main()
