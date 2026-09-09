import json
import unittest
from types import SimpleNamespace
from unittest import mock

import jm_dbus
import pair
import webui


class OptionalBluetoothTest(unittest.TestCase):
    @mock.patch.object(jm_dbus, 'ensure_process_bus')
    def test_absent_service_does_not_attempt_activation(self, connect):
        connect.return_value.name_has_owner.return_value = False
        self.assertEqual(jm_dbus.get_hci_dict(), {})
        connect.return_value.get_object.assert_not_called()

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict', return_value={})
    @mock.patch.object(pair.controller_manager, 'pair_controller')
    def test_no_adapter_skips_native_pairing(self, native_pair, discover):
        pairing = pair.Pair()
        controller = SimpleNamespace(serial='test', usb=True, bluetooth=False)
        self.assertFalse(pairing.pair_move(controller))
        native_pair.assert_not_called()

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict')
    def test_service_failure_does_not_prevent_initialization(self, discover):
        discover.side_effect = jm_dbus.dbus.DBusException('Service unavailable')
        self.assertEqual(pair.Pair().bt_devices, {})

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict')
    @mock.patch.object(pair.Pair, 'pre_existing_devices')
    def test_adapter_can_be_added_after_startup(self, enumerate_devices, discover):
        discover.side_effect = [{}, {'hci0': 'AA:BB:CC:DD:EE:FF'}]
        pairing = pair.Pair()
        pairing.update_adapters()
        self.assertEqual(pairing.get_lowest_bt_device(), 'AA:BB:CC:DD:EE:FF')

    @mock.patch.object(webui.jm_dbus, 'get_hci_dict')
    def test_web_warning_clears_when_adapter_returns(self, discover):
        ui = webui.WebUI.__new__(webui.WebUI)
        ui.ns = SimpleNamespace(status={'game_status': 'menu'})
        discover.side_effect = [{}, {'hci0': 'AA:BB:CC:DD:EE:FF'}]
        self.assertIn('No Bluetooth', json.loads(ui.update())['bluetooth_message'])
        self.assertEqual(json.loads(ui.update())['bluetooth_message'], '')
        self.assertEqual(ui.ns.status, {'game_status': 'menu'})

class RobotVoiceTest(unittest.TestCase):
    def test_real_espeak_generates_bounded_playable_audio(self):
        import os
        import shutil
        import piaudio
        if not (shutil.which('espeak') or shutil.which('espeak-ng')):
            self.skipTest('Speech engine not installed')
        with mock.patch.dict(os.environ, {'SDL_AUDIODRIVER': 'dummy'}):
            piaudio.InitAudio()
            try:
                sample = piaudio._robot_voice_sample('Robot voice regression test.')
                self.assertGreater(sample.get_length(), 0)
                self.assertLess(sample.get_length(), 10)
                samples = piaudio.pygame.sndarray.array(sample)
                rate = piaudio.pygame.mixer.get_init()[0]
                self.assertTrue(samples[:int(rate * 0.3)].any())
                self.assertFalse(samples[int(rate * 0.35):int(rate * 0.65)].any())
                self.assertTrue(samples[int(rate * 0.7):].any())
                self.assertIsNotNone(sample.play())
            finally:
                piaudio._robot_voice_sample.cache_clear()
                piaudio.pygame.mixer.quit()


if __name__ == '__main__':
    unittest.main()
