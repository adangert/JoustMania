import multiprocessing
import unittest
from unittest import mock

import controller_manager
from common import Battery, Button


class ControllerManagerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = multiprocessing.Manager()

    @classmethod
    def tearDownClass(cls):
        cls.manager.shutdown()

    def setUp(self):
        self.controller_manager = controller_manager.ControllerManager(self.manager)
        self.serial = "00:11:22:33:44:55"
        self.controller_manager.serial_to_index[self.serial] = 0
        self.controller_manager.index_to_serial[0] = self.serial
        self.controller_manager.active[0] = 1
        self.controller_manager.bluetooth[0] = 1
        controller_manager.use_manager(self.controller_manager)
        self.controller = controller_manager.Controller(self.serial)

    def publish_report(self):
        self.controller_manager.state_sequence[0] += 1
        self.controller_manager.buttons[0] = Button.MIDDLE.value
        self.controller_manager.pressed[0] = Button.CROSS.value
        self.controller_manager.released[0] = Button.CIRCLE.value
        self.controller_manager.trigger[0] = 0.5
        self.controller_manager.accelerometer[0:3] = (1.0, 2.0, 3.0)
        self.controller_manager.gyroscope[0:3] = (4.0, 5.0, 6.0)
        self.controller_manager.battery[0] = Battery.PERCENT_80
        self.controller_manager.state_sequence[0] += 1

    def test_reads_one_complete_upstream_event(self):
        self.assertIsNone(self.controller.read_update())
        self.publish_report()
        state = self.controller.read_update()
        self.assertEqual(state.buttons, Button.MIDDLE.value)
        self.assertEqual(state.pressed, Button.CROSS.value)
        self.assertEqual(state.released, Button.CIRCLE.value)
        self.assertEqual(state.trigger, 128)
        self.assertEqual(state.acceleration, (1.0, 2.0, 3.0))
        self.assertEqual(state.gyroscope, (4.0, 5.0, 6.0))
        self.assertEqual(state.battery, Battery.PERCENT_80)
        self.assertIsNone(self.controller.read_update())

    def test_button_edges_are_consumed_with_the_event(self):
        self.publish_report()
        self.controller.read_update()
        self.assertEqual(self.controller_manager.pressed[0], 0)
        self.assertEqual(self.controller_manager.released[0], 0)

    def test_output_is_clamped_to_byte_range(self):
        self.controller.set_color(-10, 128.4, 999)
        self.controller.set_rumble(300)
        self.assertEqual(tuple(self.controller_manager.leds[0:3]), (0, 128, 255))
        self.assertEqual(self.controller_manager.rumble[0], 255)

    def test_connection_flags_are_published(self):
        self.controller_manager.usb[0] = 1
        self.assertTrue(self.controller.usb)
        self.assertTrue(self.controller.bluetooth)

    def test_worker_reuses_attached_manager(self):
        with mock.patch.object(
            controller_manager,
            "get_manager",
            side_effect=AssertionError("worker started another manager"),
        ):
            controller = controller_manager.Controller(self.serial)
        self.assertIs(controller.manager, self.controller_manager)

    def test_worker_cannot_stop_parent_manager(self):
        old_process = controller_manager._api_process
        old_owner = controller_manager._api_process_owner_pid
        controller_manager._api_process = object()
        controller_manager._api_process_owner_pid = 100
        self.controller_manager.stop_event.clear()
        try:
            with mock.patch.object(controller_manager.os, "getpid", return_value=200):
                self.assertIs(controller_manager.start_manager(), self.controller_manager)
                controller_manager.stop_manager()
            self.assertFalse(self.controller_manager.stop_event.is_set())
        finally:
            controller_manager._api_process = old_process
            controller_manager._api_process_owner_pid = old_owner


if __name__ == "__main__":
    unittest.main()
