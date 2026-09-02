import unittest
from unittest import mock

import system_power


class SystemPowerTest(unittest.TestCase):
    @mock.patch("system_power.subprocess.run")
    @mock.patch("system_power.time.sleep")
    def test_requests_nonblocking_poweroff(self, sleep, run):
        system_power.request_system_power("poweroff")

        sleep.assert_called_once_with(2)
        run.assert_called_once_with(
            ["sudo", "systemctl", "--no-block", "poweroff"],
            check=True,
        )

    @mock.patch("system_power.subprocess.run")
    @mock.patch("system_power.time.sleep")
    def test_requests_nonblocking_reboot(self, sleep, run):
        system_power.request_system_power("reboot")

        sleep.assert_called_once_with(2)
        run.assert_called_once_with(
            ["sudo", "systemctl", "--no-block", "reboot"],
            check=True,
        )

    @mock.patch("system_power.subprocess.run")
    @mock.patch("system_power.time.sleep")
    def test_rejects_unknown_action(self, sleep, run):
        with self.assertRaisesRegex(ValueError, "Unsupported system power action"):
            system_power.request_system_power("suspend")

        sleep.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
